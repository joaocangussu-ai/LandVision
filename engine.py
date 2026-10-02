"""LandVision V0.5 — index-specific, on-demand Earth Engine processing.

An anomaly is a within-field spatial Z-score for the selected index, not a
clinical/agronomic diagnosis. Five historical seasons are compared pixelwise.
"""
import calendar
import json
from datetime import date, timedelta

import ee
import streamlit as st

COLLECTION = 'COPERNICUS/S2_SR_HARMONIZED'
DETECTOR_BANDS = ('NDVI', 'NDRE', 'NDMI')
BANDS = ('NDVI', 'NDRE', 'NDMI', 'NDWI', 'EVI', 'SAVI', 'ARVI', 'DVI', 'NBR', 'NBR2', 'GNDVI')
MULTI = 'MULTIESPECTRAL'
EXCLUDED_SCL = (0, 1, 3, 8, 9, 10, 11)
MAX_REGIONS = 100
MAX_FIELD_HA = 2000
DEFAULT_DIRECTIONS = {name: 'Abaixo' for name in BANDS}
DEFAULT_DIRECTIONS.update({'NDWI': 'Acima', 'NBR2': 'Ambos'})


def connect():
    """Use Streamlit Secrets only; never expose private credentials in errors."""
    try:
        cfg = st.secrets['gee']
        project = str(cfg['project']).strip()
        if 'service_account_json' in cfg:
            info = json.loads(cfg['service_account_json'])
        else:
            info = {'type': 'service_account', 'project_id': project,
                    'private_key_id': cfg['private_key_id'],
                    'private_key': cfg['private_key'].replace('\\n', '\n'),
                    'client_email': cfg['service_account'],
                    'token_uri': 'https://oauth2.googleapis.com/token'}
        if info.get('type') != 'service_account' or not info.get('private_key') or not info.get('client_email'):
            return False, 'Formato da credencial inválido. Revise Secrets.'
        credentials = ee.ServiceAccountCredentials(info['client_email'], key_data=json.dumps(info))
        ee.Initialize(credentials, project=project)
        return True, None
    except (KeyError, FileNotFoundError):
        return False, 'Secrets ausentes ou incompletos.'
    except Exception as exc:
        return False, 'Falha na autenticação/inicialização (' + type(exc).__name__ + '). Revise projeto, API, IAM e Secrets.'


def connectivity_test():
    return ee.Number(1).getInfo() == 1


def clear_mask(im):
    scl = im.select('SCL')
    mask = scl.neq(EXCLUDED_SCL[0])
    for value in EXCLUDED_SCL[1:]:
        mask = mask.And(scl.neq(value))
    return mask


def indices(im, selected):
    """Calculate only the chosen index, or three bands in multiespectral mode."""
    im = im.updateMask(clear_mask(im)).divide(10000)
    n, r, g, b = (im.select(k) for k in ('B8', 'B4', 'B3', 'B2'))
    funcs = {
        'NDVI': lambda: im.normalizedDifference(['B8', 'B4']),
        'NDRE': lambda: im.normalizedDifference(['B8A', 'B5']),
        'NDMI': lambda: im.normalizedDifference(['B8', 'B11']),
        'NDWI': lambda: im.normalizedDifference(['B3', 'B8']),  # McFeeters surface water
        'EVI': lambda: im.expression('2.5*(n-r)/(n+6*r-7.5*b+1)', {'n': n, 'r': r, 'b': b}),
        'SAVI': lambda: im.expression('1.5*(n-r)/(n+r+0.5)', {'n': n, 'r': r}),
        'ARVI': lambda: im.expression('(n-(2*r-b))/(n+(2*r-b))', {'n': n, 'r': r, 'b': b}),
        'DVI': lambda: n.subtract(r),
        'NBR': lambda: im.normalizedDifference(['B8', 'B12']),
        'NBR2': lambda: im.normalizedDifference(['B11', 'B12']),
        'GNDVI': lambda: im.normalizedDifference(['B8', 'B3']),
    }
    names = DETECTOR_BANDS if selected == MULTI else (selected,)
    if any(k not in funcs for k in names):
        raise ValueError('Índice não reconhecido')
    return ee.Image.cat([funcs[k]().rename(k) for k in names]).copyProperties(im, ['system:time_start'])


def collection(geometry, start, end, selected, max_cloud=80):
    source = (ee.ImageCollection(COLLECTION).filterBounds(geometry).filterDate(start, end)
              .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', max_cloud)))
    return source.map(lambda im: indices(im, selected))


def date_window(year, m1, m2, mode, chosen):
    if mode == 'DATA ÚNICA':
        day = min(chosen.day, calendar.monthrange(year, chosen.month)[1])
        center = date(year, chosen.month, day)
        return (center - timedelta(days=10)).isoformat(), (center + timedelta(days=11)).isoformat()
    start = date(year, m1, 1)
    ey = year + (m2 < m1)
    end = date(ey + (m2 == 12), 1 if m2 == 12 else m2 + 1, 1)
    return start.isoformat(), end.isoformat()


def composite(geom, year, m1, m2, mode, chosen, selected, current=False):
    if current and mode == 'DATA ÚNICA':
        start, end = chosen.isoformat(), (chosen + timedelta(days=1)).isoformat()
    else:
        start, end = date_window(year, m1, m2, mode, chosen)
    col = collection(geom, start, end, selected)
    names = DETECTOR_BANDS if selected == MULTI else (selected,)
    empty = ee.Image.constant([0] * len(names)).rename(list(names)).updateMask(ee.Image(0))
    # For exact date, prefer the least cloudy granule in overlapping tile areas.
    layer = col.sort('CLOUDY_PIXEL_PERCENTAGE', False).mosaic() if current and mode == 'DATA ÚNICA' else col.median()
    im = ee.Image(ee.Algorithms.If(col.size().gt(0), layer, empty)).clip(geom)
    return im, col.size()


def spatial_anomaly(im, geom, selected, direction, threshold):
    """Return anomaly raster, 1=valid-pixel raster, and per-field selected mean.

    Single index: one reducer, one band. MULTI: 3 bands / 2-of-3 vote.
    'Acima' for NDWI flags relatively high water-index values, not crop stress.
    """
    names = DETECTOR_BANDS if selected == MULTI else (selected,)
    stats = im.select(list(names)).reduceRegion(
        reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geom, scale=20, maxPixels=1e8, bestEffort=False, tileScale=4)
    marks = []
    for band in names:
        avgval, sdval = stats.get(band + '_mean'), stats.get(band + '_stdDev')
        avg = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(avgval, None), 0, avgval))
        sd = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(sdval, None), 1, sdval)).max(0.0001)
        z = im.select(band).subtract(avg).divide(sd)
        if selected == MULTI:
            mark = z.abs().gt(threshold) if band == 'NDMI' else z.lt(-threshold)
        else:
            mark = z.lt(-threshold) if direction == 'Abaixo' else (z.gt(threshold) if direction == 'Acima' else z.abs().gt(threshold))
        marks.append(mark.toInt8())
    if selected == MULTI:
        score = marks[0].add(marks[1]).add(marks[2]).rename('SCORE')
        flagged = score.gte(2).rename('ANOMALY').toInt8()
        mean = None  # Score average is generated below only in multi mode.
        shown = score
    else:
        flagged = marks[0].rename('ANOMALY').toInt8()
        mean = stats.get(selected + '_mean')
        shown = im.select(selected)
    valid = ee.Image(1).updateMask(im.select(names[0]).mask()).rename('VALID').toInt8()
    return flagged.updateMask(valid.mask()), valid, mean, shown


def field_hectares(feature):
    return ee.Geometry(feature['geometry']).area(1).divide(10000).getInfo()


def analyze(feature, year, m1, m2, mode, chosen, min_hits, min_valid, min_ha, selected_index,
            direction='Abaixo', threshold=1.0):
    geom = ee.Geometry(feature['geometry'])
    historical, trend, yearly = [], [], []
    current = current_scenes = current_display = current_valid = None
    for y in range(year - 5, year + 1):
        is_current = (y == year)
        im, n = composite(geom, y, m1, m2, mode, chosen, selected_index, current=is_current)
        anomaly, valid, field_mean, display = spatial_anomaly(im, geom, selected_index, direction, threshold)
        if selected_index == MULTI:
            field_mean = display.reduceRegion(ee.Reducer.mean(), geom, scale=20, maxPixels=1e8,
                                              tileScale=4).get('SCORE')
        pct = anomaly.reduceRegion(ee.Reducer.mean(), geom, scale=20, maxPixels=1e8,
                                   tileScale=4).get('ANOMALY')
        trend.append(ee.Feature(None, {
            'year': y,
            'pct': ee.Algorithms.If(ee.Algorithms.IsEqual(pct, None), None, ee.Number(pct).multiply(100)),
            'mean_index': field_mean,
            'scenes': n,
        }))
        yearly.append({'year': y, 'display': display, 'anomaly': anomaly})
        if is_current:
            current, current_display, current_scenes = im, display, n
            current_valid = valid.reduceRegion(ee.Reducer.max(), geom, scale=20,
                                               maxPixels=1e8, tileScale=4).get('VALID')
        else:
            historical.append(ee.Image.cat([anomaly, valid]))
    hist = ee.ImageCollection(historical)
    valid_years = hist.select('VALID').map(lambda im: im.unmask(0)).sum().rename('VALID_YEARS')
    hit_years = hist.select('ANOMALY').map(lambda im: im.unmask(0)).sum().rename('HIT_YEARS')
    recurrence = (hit_years.divide(valid_years.max(1)).multiply(100).rename('RECURRENCE')
                  .updateMask(valid_years.gte(min_valid)))
    flagged = (hit_years.gte(min_hits).And(valid_years.gte(max(min_hits, min_valid)))
               .selfMask().rename('REGION').toInt8())
    regions = flagged.reduceToVectors(geometry=geom, scale=20, geometryType='polygon',
                                      eightConnected=True, labelProperty='flag', maxPixels=1e8, tileScale=4)
    regions = regions.map(lambda f: f.set('area_ha', f.geometry().area(1).divide(10000)))
    regions = regions.filter(ee.Filter.gte('area_ha', min_ha)).sort('area_ha', False).limit(MAX_REGIONS + 1)
    combined = ee.Image.cat([recurrence, hit_years])

    def decorate(f):
        coords = f.geometry().centroid(1).coordinates()
        values = combined.reduceRegion(
            ee.Reducer.mean().combine(reducer2=ee.Reducer.max(), sharedInputs=True),
            geometry=f.geometry(), scale=20, maxPixels=1e7, tileScale=4)
        return f.set({'latitude': coords.get(1), 'longitude': coords.get(0),
                      'recurrence_pct': values.get('RECURRENCE_mean'),
                      'max_hit_years': values.get('HIT_YEARS_max')})
    regions = regions.map(decorate)
    return {'current': current, 'current_display': current_display, 'current_scenes': current_scenes,
            'current_valid': current_valid, 'recurrence': recurrence, 'hits': hit_years,
            'valid': valid_years, 'regions': regions, 'trend': ee.FeatureCollection(trend),
            'yearly': yearly, 'geometry': geom, 'index': selected_index}


def region_series(yearly, feature_geometry):
    """On demand only: annual selected-index mean and anomalous fraction inside a region."""
    region = ee.Geometry(feature_geometry)
    items = []
    for record in yearly:
        display = record['display'].rename('VALUE')
        anomaly = record['anomaly'].rename('ANOMALY')
        stats = ee.Image.cat([display, anomaly]).reduceRegion(
            ee.Reducer.mean(), region, scale=20, maxPixels=1e7, tileScale=4)
        pct = stats.get('ANOMALY')
        items.append(ee.Feature(None, {
            'year': record['year'], 'mean_index': stats.get('VALUE'),
            'anomaly_pct': ee.Algorithms.If(ee.Algorithms.IsEqual(pct, None), None,
                                            ee.Number(pct).multiply(100)),
        }))
    return ee.FeatureCollection(items)


def best_dates(feature, year, max_cloud=25, limit=30):
    geom = ee.Geometry(feature['geometry'])
    images = (ee.ImageCollection(COLLECTION).filterBounds(geom)
              .filterDate(f'{year}-01-01', f'{year+1}-01-01')
              .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', max_cloud)))

    def decorate(im):
        cover = clear_mask(im).rename('CLEAR').reduceRegion(
            ee.Reducer.mean(), geom, scale=20, maxPixels=1e8, tileScale=4).get('CLEAR')
        coverage = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(cover, None), 0, cover)).multiply(100)
        clouds = ee.Number(im.get('CLOUDY_PIXEL_PERCENTAGE'))
        return im.set({'DAY': im.date().format('YYYY-MM-dd'), 'COVERAGE': coverage,
                       'CLOUDS': clouds, 'RANK': coverage.multiply(2).subtract(clouds)})
    found = images.map(decorate).sort('RANK', False).limit(100)
    info = ee.Dictionary({'day': found.aggregate_array('DAY'), 'cover': found.aggregate_array('COVERAGE'),
                          'cloud': found.aggregate_array('CLOUDS')}).getInfo()
    unique = {}
    for day, coverage, clouds in zip(info['day'], info['cover'], info['cloud']):
        if day not in unique:
            unique[day] = {'date': day, 'coverage': round(float(coverage), 1),
                           'clouds': round(float(clouds), 1)}
        if len(unique) >= limit:
            break
    return list(unique.values())


def tile_url(image, vis):
    return image.getMapId(vis)['tile_fetcher'].url_format

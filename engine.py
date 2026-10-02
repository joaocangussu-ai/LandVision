"""LandVision V0.4 — Earth Engine processing, lean historical graphs, no credentials in code."""
import json
import calendar
from datetime import date, timedelta

import ee
import streamlit as st

COLLECTION = 'COPERNICUS/S2_SR_HARMONIZED'
DETECTOR_BANDS = ('NDVI', 'NDRE', 'NDMI')
BANDS = ('NDVI', 'NDRE', 'NDMI', 'NDWI', 'EVI', 'SAVI', 'ARVI', 'DVI', 'NBR', 'NBR2', 'GNDVI')
EXCLUDED_SCL = (0, 1, 3, 8, 9, 10, 11)
MAX_REGIONS = 100
MAX_FIELD_HA = 2000  # Protective cap for a shared, interactive app; adjust after benchmarking.


def connect():
    """Initialize with the deployed app's private Streamlit Secrets, never GitHub.

    Supports a full JSON key in gee.service_account_json or the legacy V0.3 fields.
    Error returns never include the key or exception message.
    """
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
        return False, 'Falha na autenticação/initialização (' + type(exc).__name__ + '). Revise projeto, API, IAM e Secrets.'


def connectivity_test():
    """One small real server call to distinguish initialization from usable API access."""
    return ee.Number(1).getInfo() == 1


def clear_mask(im):
    scl = im.select('SCL')
    mask = scl.neq(EXCLUDED_SCL[0])
    for value in EXCLUDED_SCL[1:]:
        mask = mask.And(scl.neq(value))
    return mask


def indices(im, selected=None):
    """Always calculate the detector's three bands; only add the selected extra index.

    Historical scenes never calculate unrelated indices.
    """
    im = im.updateMask(clear_mask(im)).divide(10000)
    n, r, g, b = (im.select(name) for name in ('B8', 'B4', 'B3', 'B2'))
    output = [im.normalizedDifference(['B8', 'B4']).rename('NDVI'),
              im.normalizedDifference(['B8A', 'B5']).rename('NDRE'),
              im.normalizedDifference(['B8', 'B11']).rename('NDMI')]
    if selected and selected not in DETECTOR_BANDS:
        extras = {
            'NDWI': lambda: im.normalizedDifference(['B3', 'B8']),
            'EVI': lambda: im.expression('2.5*(n-r)/(n+6*r-7.5*b+1)', {'n': n, 'r': r, 'b': b}),
            'SAVI': lambda: im.expression('1.5*(n-r)/(n+r+0.5)', {'n': n, 'r': r}),
            'ARVI': lambda: im.expression('(n-(2*r-b))/(n+(2*r-b))', {'n': n, 'r': r, 'b': b}),
            'DVI': lambda: n.subtract(r),
            'NBR': lambda: im.normalizedDifference(['B8', 'B12']),
            'NBR2': lambda: im.normalizedDifference(['B11', 'B12']),
            'GNDVI': lambda: im.normalizedDifference(['B8', 'B3']),
        }
        if selected not in extras:
            raise ValueError('Índice não reconhecido')
        output.append(extras[selected]().rename(selected))
    return ee.Image.cat(output).copyProperties(im, ['system:time_start'])


def collection(geometry, start, end, max_cloud=80, selected=None):
    images = (ee.ImageCollection(COLLECTION).filterBounds(geometry).filterDate(start, end)
              .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', max_cloud)))
    return images.map(lambda im: indices(im, selected))


def date_window(year, m1, m2, mode, chosen):
    if mode == 'DATA ÚNICA':
        day = min(chosen.day, calendar.monthrange(year, chosen.month)[1])
        center = date(year, chosen.month, day)
        return (center - timedelta(days=10)).isoformat(), (center + timedelta(days=11)).isoformat()
    start = date(year, m1, 1)
    ey = year + (m2 < m1)
    end = date(ey + (m2 == 12), 1 if m2 == 12 else m2 + 1, 1)
    return start.isoformat(), end.isoformat()


def composite(geom, year, m1, m2, mode, chosen, current=False, selected=None):
    if current and mode == 'DATA ÚNICA':
        start, end = chosen.isoformat(), (chosen + timedelta(days=1)).isoformat()
    else:
        start, end = date_window(year, m1, m2, mode, chosen)
    col = collection(geom, start, end, selected=selected if current else None)
    names = list(DETECTOR_BANDS) + ([selected] if selected not in DETECTOR_BANDS and selected else [])
    empty = ee.Image.constant([0] * len(names)).rename(names).updateMask(ee.Image(0))
    layer = col.mosaic() if current and mode == 'DATA ÚNICA' else col.median()
    im = ee.Image(ee.Algorithms.If(col.size().gt(0), layer, empty)).clip(geom)
    return im, col.size()


def spatial_score(im, geom):
    # One three-band aggregation per year, rather than three separate reduceRegion operations.
    stats = im.select(list(DETECTOR_BANDS)).reduceRegion(
        reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geom, scale=20, maxPixels=1e8, bestEffort=False, tileScale=4)
    marks = []
    for band in DETECTOR_BANDS:
        avgval, sdval = stats.get(band + '_mean'), stats.get(band + '_stdDev')
        avg = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(avgval, None), 0, avgval))
        sd = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(sdval, None), 1, sdval)).max(0.0001)
        z = im.select(band).subtract(avg).divide(sd)
        marks.append((z.abs().gt(1) if band == 'NDMI' else z.lt(-1)).toInt8())
    score = marks[0].add(marks[1]).add(marks[2]).rename('SCORE')
    valid = ee.Image(1).updateMask(im.select('NDVI').mask()).rename('VALID')
    return ee.Image.cat([score, valid])


def field_hectares(feature):
    return ee.Geometry(feature['geometry']).area(1).divide(10000).getInfo()


def analyze(feature, year, m1, m2, mode, chosen, min_hits, min_valid, min_ha, selected_index):
    geom = ee.Geometry(feature['geometry'])
    historical, trend = [], []
    current, current_scenes = None, None
    for y in range(year - 5, year + 1):
        is_current = y == year
        im, size = composite(geom, y, m1, m2, mode, chosen, current=is_current,
                             selected=selected_index if is_current else None)
        spatial = spatial_score(im, geom)
        if is_current:
            current, current_scenes = im, size
        else:
            historical.append(spatial)
        est = spatial.select('SCORE').gte(2).rename('EST')
        pct = est.reduceRegion(ee.Reducer.mean(), geom, scale=20, maxPixels=1e8,
                               tileScale=4).get('EST')
        trend.append(ee.Feature(None, {'year': y, 'pct': ee.Algorithms.If(
            ee.Algorithms.IsEqual(pct, None), None, ee.Number(pct).multiply(100))}))
    hist = ee.ImageCollection(historical)
    valid = hist.select('VALID').map(lambda im: im.unmask(0)).sum().rename('VALID_YEARS')
    hits = hist.select('SCORE').map(lambda im: im.gte(2).unmask(0)).sum().rename('HIT_YEARS')
    recurrence = hits.divide(valid.max(1)).multiply(100).rename('RECURRENCE').updateMask(valid.gte(min_valid))
    flagged = hits.gte(min_hits).And(valid.gte(max(min_hits, min_valid))).selfMask().rename('REGION').toInt8()
    # Filter by polygon area BEFORE running costly per-region statistics; inspect only top 101.
    regions = flagged.reduceToVectors(geometry=geom, scale=20, geometryType='polygon',
                                      eightConnected=True, labelProperty='flag', maxPixels=1e8, tileScale=4)
    regions = regions.map(lambda f: f.set('area_ha', f.geometry().area(1).divide(10000)))
    regions = regions.filter(ee.Filter.gte('area_ha', min_ha)).sort('area_ha', False).limit(MAX_REGIONS + 1)
    combined = ee.Image.cat([recurrence, hits])

    def decorate(f):
        shape = f.geometry()
        coord = shape.centroid(1).coordinates()
        region_stats = combined.reduceRegion(
            reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.max(), sharedInputs=True),
            geometry=shape, scale=20, maxPixels=1e7, tileScale=4)
        return f.set({'latitude': coord.get(1), 'longitude': coord.get(0),
                      'recurrence_pct': region_stats.get('RECURRENCE_mean'),
                      'max_hit_years': region_stats.get('HIT_YEARS_max')})
    regions = regions.map(decorate)
    valid_now = current.select('NDVI').mask().reduceRegion(
        ee.Reducer.max(), geom, scale=20, maxPixels=1e8, tileScale=4).get('NDVI')
    return {'current': current, 'current_scenes': current_scenes, 'current_valid': valid_now,
            'recurrence': recurrence, 'hits': hits, 'valid': valid, 'regions': regions,
            'trend': ee.FeatureCollection(trend), 'geometry': geom, 'index': selected_index}


def best_dates(feature, year, max_cloud=25, limit=30):
    """One compact server response, not three repeated getInfo requests."""
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
    info = ee.Dictionary({'day': found.aggregate_array('DAY'),
                          'cover': found.aggregate_array('COVERAGE'),
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

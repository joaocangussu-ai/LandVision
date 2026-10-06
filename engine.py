"""LandVision V0.6 — index-specific recurrence + optional multi-index concordance.

Core V0.5 behaviour is preserved. Multi-index concordance runs only on demand.
Anomalies are within-field spatial Z-scores; they are exploratory indicators,
not diagnoses of disease, nematodes, compaction, fertility or water stress.
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

# Effective analysis scale. Mixed 10/20 m formulas remain limited by the
# coarsest source band, even if Earth Engine resamples for visualization.
INDEX_SCALE = {
    'NDVI': 10,
    'NDWI': 10,
    'EVI': 10,
    'SAVI': 10,
    'ARVI': 10,
    'DVI': 10,
    'GNDVI': 10,
    'NDRE': 20,
    'NDMI': 20,
    'NBR': 20,
    'NBR2': 20,
    MULTI: 20,
}

DEFAULT_DIRECTIONS = {name: 'Abaixo' for name in BANDS}
DEFAULT_DIRECTIONS.update({'NDWI': 'Acima', 'NBR2': 'Ambos'})


def analysis_scale(selected):
    """Return effective working scale (m) for one index or an iterable."""
    if isinstance(selected, str):
        return INDEX_SCALE.get(selected, 20)
    names = tuple(selected)
    return max((INDEX_SCALE.get(name, 20) for name in names), default=20)


def _names(selected):
    if selected == MULTI:
        return DETECTOR_BANDS
    if isinstance(selected, str):
        return (selected,)
    return tuple(dict.fromkeys(selected))


def connect():
    """Use Streamlit Secrets only; never expose private credentials in errors."""
    try:
        cfg = st.secrets['gee']
        project = str(cfg['project']).strip()
        if 'service_account_json' in cfg:
            info = json.loads(cfg['service_account_json'])
        else:
            info = {
                'type': 'service_account',
                'project_id': project,
                'private_key_id': cfg['private_key_id'],
                'private_key': cfg['private_key'].replace('\\n', '\n'),
                'client_email': cfg['service_account'],
                'token_uri': 'https://oauth2.googleapis.com/token',
            }
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
    """Calculate only the requested index bands in one pass per Sentinel image."""
    source = im
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
    names = _names(selected)
    if not names or any(k not in funcs for k in names):
        raise ValueError('Índice não reconhecido')
    return ee.Image.cat([funcs[k]().rename(k) for k in names]).copyProperties(
        source, ['system:time_start', 'CLOUDY_PIXEL_PERCENTAGE', 'PRODUCT_ID']
    )


def collection(geometry, start, end, selected, max_cloud=80):
    source = (
        ee.ImageCollection(COLLECTION)
        .filterBounds(geometry)
        .filterDate(start, end)
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', max_cloud))
    )
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
    names = _names(selected)
    empty = ee.Image.constant([0] * len(names)).rename(list(names)).updateMask(ee.Image(0))
    # In an exact-date mosaic, descending cloudiness puts the least-cloudy
    # granule last, which receives mosaic priority over overlapping tiles.
    layer = col.sort('CLOUDY_PIXEL_PERCENTAGE', False).mosaic() if current and mode == 'DATA ÚNICA' else col.median()
    im = ee.Image(ee.Algorithms.If(col.size().gt(0), layer, empty)).clip(geom)
    return im, col.size()


def _anomaly_from_z(z, direction, threshold):
    if direction == 'Abaixo':
        return z.lt(-threshold)
    if direction == 'Acima':
        return z.gt(threshold)
    return z.abs().gt(threshold)


def spatial_anomaly(im, geom, selected, direction, threshold):
    """Single-index / legacy multiespectral anomaly, preserving V0.5 logic."""
    names = _names(selected)
    scale = analysis_scale(selected)
    stats = im.select(list(names)).reduceRegion(
        reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geom,
        scale=scale,
        maxPixels=1e8,
        bestEffort=False,
        tileScale=4,
    )
    marks = []
    for band in names:
        avgval, sdval = stats.get(band + '_mean'), stats.get(band + '_stdDev')
        avg = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(avgval, None), 0, avgval))
        sd = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(sdval, None), 1, sdval)).max(0.0001)
        z = im.select(band).subtract(avg).divide(sd)
        if selected == MULTI:
            mark = z.abs().gt(threshold) if band == 'NDMI' else z.lt(-threshold)
        else:
            mark = _anomaly_from_z(z, direction, threshold)
        marks.append(mark.toInt8())

    if selected == MULTI:
        score = marks[0].add(marks[1]).add(marks[2]).rename('SCORE')
        flagged = score.gte(2).rename('ANOMALY').toInt8()
        mean = None
        shown = score
    else:
        flagged = marks[0].rename('ANOMALY').toInt8()
        mean = stats.get(selected + '_mean')
        shown = im.select(selected)

    valid = ee.Image(1).updateMask(im.select(names[0]).mask()).rename('VALID').toInt8()
    return flagged.updateMask(valid.mask()), valid, mean, shown


def spatial_anomalies_many(im, geom, selected_indices, directions, threshold):
    """Create one anomaly band per selected index and their same-pixel count.

    All statistics are reduced at a common grid scale: 10 m only when every
    selected index is effectively 10 m; otherwise 20 m. Index calculation is
    still performed once per Sentinel image, minimizing duplicated work.
    """
    names = tuple(dict.fromkeys(selected_indices))
    if len(names) < 2:
        raise ValueError('Selecione pelo menos dois índices para concordância.')
    scale = analysis_scale(names)
    stats = im.select(list(names)).reduceRegion(
        reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geom,
        scale=scale,
        maxPixels=1e8,
        bestEffort=False,
        tileScale=4,
    )

    # Intersection of valid masks prevents a missing index from being counted as
    # a normal observation in the concordance calculation.
    valid_mask = im.select(list(names)).mask().reduce(ee.Reducer.min())
    anomaly_bands = []
    for band in names:
        avgval, sdval = stats.get(band + '_mean'), stats.get(band + '_stdDev')
        avg = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(avgval, None), 0, avgval))
        sd = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(sdval, None), 1, sdval)).max(0.0001)
        z = im.select(band).subtract(avg).divide(sd)
        direction = directions.get(band, DEFAULT_DIRECTIONS.get(band, 'Abaixo'))
        anomaly_bands.append(_anomaly_from_z(z, direction, threshold).toInt8().rename(band).updateMask(valid_mask))

    # Put a 20 m index first whenever a 20 m common scale is needed. This keeps
    # binary image arithmetic anchored to the coarser effective grid.
    anomaly_bands.sort(key=lambda img: 0)  # Python list kept explicit for ee.Image.cat below.
    anomalies = ee.Image.cat(anomaly_bands)
    ordered_names = sorted(names, key=lambda name: INDEX_SCALE.get(name, 20), reverse=True)
    count = anomalies.select(ordered_names[0]).rename('INDEX_COUNT')
    for band in ordered_names[1:]:
        count = count.add(anomalies.select(band))
    count = count.rename('INDEX_COUNT').toInt8().updateMask(valid_mask)
    valid = ee.Image(1).updateMask(valid_mask).rename('VALID').toInt8()
    return anomalies, count, valid, scale


def field_hectares(feature):
    return ee.Geometry(feature['geometry']).area(1).divide(10000).getInfo()


def analyze(feature, year, m1, m2, mode, chosen, min_hits, min_valid, min_ha, selected_index,
            direction='Abaixo', threshold=1.0):
    """V0.5 index-specific recurrence, now at the effective index scale."""
    geom = ee.Geometry(feature['geometry'])
    scale = analysis_scale(selected_index)
    historical, trend, yearly = [], [], []
    current = current_scenes = current_display = current_valid = None

    for y in range(year - 5, year + 1):
        is_current = y == year
        im, n = composite(geom, y, m1, m2, mode, chosen, selected_index, current=is_current)
        anomaly, valid, field_mean, display = spatial_anomaly(im, geom, selected_index, direction, threshold)
        if selected_index == MULTI:
            field_mean = display.reduceRegion(
                ee.Reducer.mean(), geom, scale=scale, maxPixels=1e8, tileScale=4
            ).get('SCORE')
        pct = anomaly.reduceRegion(
            ee.Reducer.mean(), geom, scale=scale, maxPixels=1e8, tileScale=4
        ).get('ANOMALY')
        trend.append(ee.Feature(None, {
            'year': y,
            'pct': ee.Algorithms.If(ee.Algorithms.IsEqual(pct, None), None, ee.Number(pct).multiply(100)),
            'mean_index': field_mean,
            'scenes': n,
        }))
        yearly.append({'year': y, 'display': display, 'anomaly': anomaly, 'scale': scale})
        if is_current:
            current, current_display, current_scenes = im, display, n
            current_valid = valid.reduceRegion(
                ee.Reducer.max(), geom, scale=scale, maxPixels=1e8, tileScale=4
            ).get('VALID')
        else:
            historical.append(ee.Image.cat([anomaly, valid]))

    hist = ee.ImageCollection(historical)
    valid_years = hist.select('VALID').map(lambda im: im.unmask(0)).sum().rename('VALID_YEARS')
    hit_years = hist.select('ANOMALY').map(lambda im: im.unmask(0)).sum().rename('HIT_YEARS')
    recurrence = (
        hit_years.divide(valid_years.max(1)).multiply(100).rename('RECURRENCE')
        .updateMask(valid_years.gte(min_valid))
    )
    flagged = (
        hit_years.gte(min_hits).And(valid_years.gte(max(min_hits, min_valid)))
        .selfMask().rename('REGION').toInt8()
    )
    regions = flagged.reduceToVectors(
        geometry=geom,
        scale=scale,
        geometryType='polygon',
        eightConnected=True,
        labelProperty='flag',
        maxPixels=1e8,
        tileScale=4,
    )
    regions = regions.map(lambda f: f.set('area_ha', f.geometry().area(1).divide(10000)))
    regions = regions.filter(ee.Filter.gte('area_ha', min_ha)).sort('area_ha', False).limit(MAX_REGIONS + 1)
    combined = ee.Image.cat([recurrence, hit_years])

    def decorate(f):
        coords = f.geometry().centroid(1).coordinates()
        values = combined.reduceRegion(
            ee.Reducer.mean().combine(reducer2=ee.Reducer.max(), sharedInputs=True),
            geometry=f.geometry(),
            scale=scale,
            maxPixels=1e7,
            tileScale=4,
        )
        return f.set({
            'latitude': coords.get(1),
            'longitude': coords.get(0),
            'recurrence_pct': values.get('RECURRENCE_mean'),
            'max_hit_years': values.get('HIT_YEARS_max'),
        })

    regions = regions.map(decorate)
    return {
        'current': current,
        'current_display': current_display,
        'current_scenes': current_scenes,
        'current_valid': current_valid,
        'recurrence': recurrence,
        'hits': hit_years,
        'valid': valid_years,
        'regions': regions,
        'trend': ee.FeatureCollection(trend),
        'yearly': yearly,
        'geometry': geom,
        'index': selected_index,
        'scale': scale,
    }


def region_series(yearly, feature_geometry):
    """On demand: annual selected-index mean and anomalous fraction in a region."""
    region = ee.Geometry(feature_geometry)
    items = []
    for record in yearly:
        scale = record.get('scale', 20)
        display = record['display'].rename('VALUE')
        anomaly = record['anomaly'].rename('ANOMALY')
        stats = ee.Image.cat([display, anomaly]).reduceRegion(
            ee.Reducer.mean(), region, scale=scale, maxPixels=1e7, tileScale=4
        )
        pct = stats.get('ANOMALY')
        items.append(ee.Feature(None, {
            'year': record['year'],
            'mean_index': stats.get('VALUE'),
            'anomaly_pct': ee.Algorithms.If(
                ee.Algorithms.IsEqual(pct, None), None, ee.Number(pct).multiply(100)
            ),
        }))
    return ee.FeatureCollection(items)


def concordance_analyze(feature, year, m1, m2, mode, chosen, selected_indices,
                        min_indices, min_years, min_valid, min_ha,
                        directions=None, threshold=1.0):
    """Optional same-location concordance among selected spectral indices.

    For each year, an index contributes 1 when its spatial Z-score meets its
    configured anomaly direction. A pixel is concordant when at least
    `min_indices` indices are anomalous at that same pixel in that year.
    Historical recurrence is then computed over the five previous years.
    """
    names = tuple(dict.fromkeys(selected_indices))
    if len(names) < 2:
        raise ValueError('Selecione pelo menos dois índices para concordância.')
    if min_indices < 2 or min_indices > len(names):
        raise ValueError('Número mínimo de índices concordantes inválido.')

    geom = ee.Geometry(feature['geometry'])
    directions = {**DEFAULT_DIRECTIONS, **(directions or {})}
    common_scale = analysis_scale(names)
    historical, trend, yearly = [], [], []
    current_count = current_scenes = current_valid = None
    historical_counts = []

    for y in range(year - 5, year + 1):
        is_current = y == year
        im, n = composite(geom, y, m1, m2, mode, chosen, names, current=is_current)
        anomalies, count, valid, scale = spatial_anomalies_many(
            im, geom, names, directions, threshold
        )
        concord = count.gte(min_indices).rename('CONCORD').toInt8().updateMask(valid.mask())
        concord_pct = concord.reduceRegion(
            ee.Reducer.mean(), geom, scale=scale, maxPixels=1e8, tileScale=4
        ).get('CONCORD')
        mean_count = count.reduceRegion(
            ee.Reducer.mean(), geom, scale=scale, maxPixels=1e8, tileScale=4
        ).get('INDEX_COUNT')
        trend.append(ee.Feature(None, {
            'year': y,
            'concordance_pct': ee.Algorithms.If(
                ee.Algorithms.IsEqual(concord_pct, None), None,
                ee.Number(concord_pct).multiply(100)
            ),
            'mean_index_count': mean_count,
            'scenes': n,
        }))
        yearly.append({
            'year': y,
            'anomalies': anomalies,
            'count': count,
            'concord': concord,
            'scale': scale,
        })
        if is_current:
            current_count = count
            current_scenes = n
            current_valid = valid.reduceRegion(
                ee.Reducer.max(), geom, scale=scale, maxPixels=1e8, tileScale=4
            ).get('VALID')
        else:
            historical.append(ee.Image.cat([concord, valid]))
            historical_counts.append(count)

    hist = ee.ImageCollection(historical)
    valid_years = hist.select('VALID').map(lambda im: im.unmask(0)).sum().rename('VALID_YEARS')
    concord_years = hist.select('CONCORD').map(lambda im: im.unmask(0)).sum().rename('CONCORD_YEARS')
    recurrence = (
        concord_years.divide(valid_years.max(1)).multiply(100).rename('CONCORD_RECURRENCE')
        .updateMask(valid_years.gte(min_valid))
    )
    flagged = (
        concord_years.gte(min_years).And(valid_years.gte(max(min_years, min_valid)))
        .selfMask().rename('REGION').toInt8()
    )
    regions = flagged.reduceToVectors(
        geometry=geom,
        scale=common_scale,
        geometryType='polygon',
        eightConnected=True,
        labelProperty='flag',
        maxPixels=1e8,
        tileScale=4,
    )
    regions = regions.map(lambda f: f.set('area_ha', f.geometry().area(1).divide(10000)))
    regions = regions.filter(ee.Filter.gte('area_ha', min_ha)).sort('area_ha', False).limit(MAX_REGIONS + 1)

    max_indices = ee.ImageCollection(historical_counts).max().rename('MAX_INDICES')
    combined = ee.Image.cat([recurrence, concord_years, max_indices])

    def decorate(f):
        coords = f.geometry().centroid(1).coordinates()
        values = combined.reduceRegion(
            ee.Reducer.mean().combine(reducer2=ee.Reducer.max(), sharedInputs=True),
            geometry=f.geometry(),
            scale=common_scale,
            maxPixels=1e7,
            tileScale=4,
        )
        return f.set({
            'latitude': coords.get(1),
            'longitude': coords.get(0),
            'recurrence_pct': values.get('CONCORD_RECURRENCE_mean'),
            'max_concord_years': values.get('CONCORD_YEARS_max'),
            'max_indices_same_year': values.get('MAX_INDICES_max'),
        })

    regions = regions.map(decorate)
    return {
        'current_count': current_count,
        'current_scenes': current_scenes,
        'current_valid': current_valid,
        'recurrence': recurrence,
        'concord_years': concord_years,
        'valid_years': valid_years,
        'regions': regions,
        'trend': ee.FeatureCollection(trend),
        'yearly': yearly,
        'geometry': geom,
        'indices': names,
        'scale': common_scale,
        'min_indices': min_indices,
    }


def concordance_region_series(yearly, feature_geometry, selected_indices):
    """On demand detail for a concordance region.

    Returns both area fractions and the anomaly state at the region centroid,
    allowing an index × year matrix for the same approximate location.
    """
    names = tuple(dict.fromkeys(selected_indices))
    region = ee.Geometry(feature_geometry)
    point = region.centroid(1)
    items = []
    for record in yearly:
        scale = record.get('scale', analysis_scale(names))
        anomalies = record['anomalies'].select(list(names))
        area_stats = anomalies.reduceRegion(
            ee.Reducer.mean(), region, scale=scale, maxPixels=1e7, tileScale=4
        )
        point_stats = anomalies.reduceRegion(
            ee.Reducer.first(), point, scale=scale, maxPixels=1e5, tileScale=2
        )
        count_mean = record['count'].reduceRegion(
            ee.Reducer.mean(), region, scale=scale, maxPixels=1e7, tileScale=4
        ).get('INDEX_COUNT')
        concord_pct = record['concord'].reduceRegion(
            ee.Reducer.mean(), region, scale=scale, maxPixels=1e7, tileScale=4
        ).get('CONCORD')
        props = {
            'year': record['year'],
            'mean_index_count': count_mean,
            'concordance_pct': ee.Algorithms.If(
                ee.Algorithms.IsEqual(concord_pct, None), None,
                ee.Number(concord_pct).multiply(100)
            ),
        }
        for name in names:
            area_value = area_stats.get(name)
            props[name + '_pct'] = ee.Algorithms.If(
                ee.Algorithms.IsEqual(area_value, None), None,
                ee.Number(area_value).multiply(100)
            )
            props[name + '_center'] = point_stats.get(name)
        items.append(ee.Feature(None, props))
    return ee.FeatureCollection(items)


def best_dates(feature, year, max_cloud=25, limit=30):
    geom = ee.Geometry(feature['geometry'])
    images = (
        ee.ImageCollection(COLLECTION)
        .filterBounds(geom)
        .filterDate(f'{year}-01-01', f'{year+1}-01-01')
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', max_cloud))
    )

    def decorate(im):
        # SCL is natively 20 m, so 20 m is appropriate for clear-pixel coverage.
        cover = clear_mask(im).rename('CLEAR').reduceRegion(
            ee.Reducer.mean(), geom, scale=20, maxPixels=1e8, tileScale=4
        ).get('CLEAR')
        coverage = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(cover, None), 0, cover)).multiply(100)
        clouds = ee.Number(im.get('CLOUDY_PIXEL_PERCENTAGE'))
        return im.set({
            'DAY': im.date().format('YYYY-MM-dd'),
            'COVERAGE': coverage,
            'CLOUDS': clouds,
            'RANK': coverage.multiply(2).subtract(clouds),
        })

    found = images.map(decorate).sort('RANK', False).limit(100)
    info = ee.Dictionary({
        'day': found.aggregate_array('DAY'),
        'cover': found.aggregate_array('COVERAGE'),
        'cloud': found.aggregate_array('CLOUDS'),
    }).getInfo()
    unique = {}
    for day, coverage, clouds in zip(info['day'], info['cover'], info['cloud']):
        if day not in unique:
            unique[day] = {
                'date': day,
                'coverage': round(float(coverage), 1),
                'clouds': round(float(clouds), 1),
            }
        if len(unique) >= limit:
            break
    return list(unique.values())


def tile_url(image, vis):
    return image.getMapId(vis)['tile_fetcher'].url_format

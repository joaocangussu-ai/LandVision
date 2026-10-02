"""LandVision: Sentinel-2 Earth Engine computations. No secrets in source control."""
import json
from datetime import date, timedelta
import ee
import streamlit as st

COLLECTION = 'COPERNICUS/S2_SR_HARMONIZED'
BANDS = ['NDVI','NDRE','NDMI','NDWI','EVI','SAVI','ARVI','DVI','NBR','NBR2','GNDVI']
EXCLUDED_SCL = (0,1,3,8,9,10,11)


def connect():
    """Authenticate privately using the TOML in Streamlit Secrets."""
    try:
        cfg = st.secrets['gee']
        info = {'type':'service_account','project_id':cfg['project'],
                'private_key_id':cfg['private_key_id'],
                'private_key':cfg['private_key'].replace('\\n','\n'),
                'client_email':cfg['service_account'],
                'token_uri':'https://oauth2.googleapis.com/token'}
        credentials = ee.ServiceAccountCredentials(cfg['service_account'], key_data=json.dumps(info))
        ee.Initialize(credentials,project=cfg['project'])
        return True, None
    except Exception as exc:
        return False, str(exc)


def clear_mask(im):
    scl=im.select('SCL'); mask=scl.neq(EXCLUDED_SCL[0])
    for value in EXCLUDED_SCL[1:]:mask=mask.And(scl.neq(value))
    return mask


def indices(im):
    im=im.updateMask(clear_mask(im)).divide(10000)
    n=im.select('B8'); r=im.select('B4'); g=im.select('B3'); b=im.select('B2'); s1=im.select('B11'); s2=im.select('B12')
    arr=[im.normalizedDifference(['B8','B4']).rename('NDVI'),
         im.normalizedDifference(['B8A','B5']).rename('NDRE'),
         im.normalizedDifference(['B8','B11']).rename('NDMI'),
         im.normalizedDifference(['B3','B8']).rename('NDWI'),
         im.expression('2.5*(n-r)/(n+6*r-7.5*b+1)',{'n':n,'r':r,'b':b}).rename('EVI'),
         im.expression('1.5*(n-r)/(n+r+0.5)',{'n':n,'r':r}).rename('SAVI'),
         im.expression('(n-(2*r-b))/(n+(2*r-b))',{'n':n,'r':r,'b':b}).rename('ARVI'),
         n.subtract(r).rename('DVI'),
         im.normalizedDifference(['B8','B12']).rename('NBR'),
         im.normalizedDifference(['B11','B12']).rename('NBR2'),
         im.normalizedDifference(['B8','B3']).rename('GNDVI')]
    return ee.Image.cat(arr).copyProperties(im,['system:time_start'])


def collection(geometry,start,end,max_cloud=80):
    return (ee.ImageCollection(COLLECTION).filterBounds(geometry).filterDate(start,end)
            .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE',max_cloud)).map(indices))


def date_window(year,m1,m2,mode,chosen):
    if mode=='DATA ÚNICA':
        day=min(chosen.day,28) if chosen.month==2 else chosen.day
        center=date(year,chosen.month,day)
        return (center-timedelta(days=10)).isoformat(),(center+timedelta(days=11)).isoformat()
    start=date(year,m1,1)
    ey=year+(m2<m1); end=date(ey+(m2==12),1 if m2==12 else m2+1,1)
    return start.isoformat(),end.isoformat()


def composite(geom,year,m1,m2,mode,chosen,current=False):
    if current and mode=='DATA ÚNICA':
        start=chosen.isoformat(); end=(chosen+timedelta(days=1)).isoformat()
    else:start,end=date_window(year,m1,m2,mode,chosen)
    col=collection(geom,start,end)
    empty=ee.Image.constant([0]*len(BANDS)).rename(BANDS).updateMask(ee.Image(0))
    # For exact date, mosaic all matching tiles; for periods, take median.
    im=ee.Image(ee.Algorithms.If(col.size().gt(0),col.mosaic() if (current and mode=='DATA ÚNICA') else col.median(),empty)).clip(geom)
    return im,col.size()


def spatial_score(im,geom):
    out=[]
    for band in ('NDVI','NDRE','NDMI'):
        stats=im.select(band).reduceRegion(reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(),sharedInputs=True),geometry=geom,scale=20,maxPixels=1e8,bestEffort=True)
        avg=ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(stats.get(band+'_mean'),None),0,stats.get(band+'_mean')))
        sd=ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(stats.get(band+'_stdDev'),None),1,stats.get(band+'_stdDev'))).max(.0001)
        z=im.select(band).subtract(avg).divide(sd)
        out.append((z.abs().gt(1) if band=='NDMI' else z.lt(-1)).toInt8())
    score=out[0].add(out[1]).add(out[2]).rename('SCORE')
    valid=ee.Image(1).updateMask(im.select('NDVI').mask()).rename('VALID')
    return ee.Image.cat([score,valid])


def analyze(feature,year,m1,m2,mode,chosen,min_hits,min_valid,min_ha,selected_index):
    geom=ee.Geometry(feature['geometry'])
    current,current_scenes=composite(geom,year,m1,m2,mode,chosen,True)
    historic=[]; trend=[]
    for y in range(year-5,year+1):
        im,_=composite(geom,y,m1,m2,mode,chosen,current=(y==year))
        spatial=spatial_score(im,geom)
        if y<year:historic.append(spatial)
        est=spatial.select('SCORE').gte(2).rename('EST')
        pct=est.reduceRegion(ee.Reducer.mean(),geom,scale=20,maxPixels=1e8,bestEffort=True).get('EST')
        trend.append(ee.Feature(None,{'year':y,'pct':ee.Algorithms.If(ee.Algorithms.IsEqual(pct,None),None,ee.Number(pct).multiply(100))}))
    hist=ee.ImageCollection(historic)
    valid=hist.select('VALID').map(lambda im:im.unmask(0)).sum().rename('VALID_YEARS')
    hits=hist.select('SCORE').map(lambda im:im.gte(2).unmask(0)).sum().rename('HIT_YEARS')
    recurrence=hits.divide(valid.max(1)).multiply(100).rename('RECURRENCE').updateMask(valid.gte(min_valid))
    flagged=hits.gte(min_hits).And(valid.gte(min_valid)).selfMask().rename('REGION').toInt8()
    # Limit vectorization to marked pixels, with a configurable minimum region area.
    regions=flagged.reduceToVectors(geometry=geom,scale=20,geometryType='polygon',eightConnected=True,labelProperty='flag',maxPixels=1e8,bestEffort=True)
    def decorate(f):
        shape=f.geometry(); center=shape.centroid(1).coordinates()
        rec=recurrence.reduceRegion(ee.Reducer.mean(),shape,20,maxPixels=1e7,bestEffort=True).get('RECURRENCE')
        n=hits.reduceRegion(ee.Reducer.max(),shape,20,maxPixels=1e7,bestEffort=True).get('HIT_YEARS')
        return f.set({'area_ha':shape.area(1).divide(10000),'latitude':center.get(1),'longitude':center.get(0),'recurrence_pct':rec,'max_hit_years':n})
    regions=regions.map(decorate).filter(ee.Filter.gte('area_ha',min_ha)).sort('area_ha',False)
    # Checking valid pixels, not merely image count, avoids treating fully cloudy scenes as usable.
    valid_now=current.select('NDVI').mask().reduceRegion(ee.Reducer.max(),geom,scale=20,maxPixels=1e8,bestEffort=True).get('NDVI')
    return {'current':current,'current_scenes':current_scenes,'current_valid':valid_now,'recurrence':recurrence,'hits':hits,'valid':valid,'regions':regions,'trend':ee.FeatureCollection(trend),'geometry':geom,'index':selected_index}


def best_dates(feature,year,max_cloud=25,limit=30):
    """Evaluate scene-level clouds and clear SCL coverage within the field; at most 30 unique dates."""
    geom=ee.Geometry(feature['geometry'])
    images=(ee.ImageCollection(COLLECTION).filterBounds(geom).filterDate(f'{year}-01-01',f'{year+1}-01-01')
            .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE',max_cloud)))
    def decorate(im):
        pct=clear_mask(im).rename('CLEAR').reduceRegion(ee.Reducer.mean(),geom,scale=20,maxPixels=1e8,bestEffort=True).get('CLEAR')
        coverage=ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(pct,None),0,pct)).multiply(100)
        clouds=ee.Number(im.get('CLOUDY_PIXEL_PERCENTAGE'))
        return im.set({'DAY':im.date().format('YYYY-MM-dd'),'COVERAGE':coverage,'CLOUDS':clouds,'RANK':coverage.multiply(2).subtract(clouds)})
    found=images.map(decorate).sort('RANK',False).limit(100)
    days=found.aggregate_array('DAY').getInfo(); coverage=found.aggregate_array('COVERAGE').getInfo(); clouds=found.aggregate_array('CLOUDS').getInfo()
    unique={}
    for d,c,n in zip(days,coverage,clouds):
        if d not in unique:unique[d]={'date':d,'coverage':round(float(c),1),'clouds':round(float(n),1)}
        if len(unique)>=limit:break
    return list(unique.values())


def tile_url(image,vis):
    return image.getMapId(vis)['tile_fetcher'].url_format

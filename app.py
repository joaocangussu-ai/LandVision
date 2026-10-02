"""LandVision V0.4.1 — diagnostic update; no private credentials in the code."""
import csv
import io
import json
import logging
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape
import folium
import pandas as pd
import streamlit as st
from folium.plugins import Draw, Fullscreen, MiniMap
from streamlit_folium import st_folium
from engine import connect, connectivity_test, field_hectares, MAX_FIELD_HA, analyze, best_dates, tile_url

ROOT = Path(__file__).parent
SYMBOL = ROOT/'assets'/'simbolo_enviado.png'
st.set_page_config(page_title='LandVision | Field Intelligence',page_icon=str(SYMBOL),layout='wide',initial_sidebar_state='expanded')
NAVY='#0C243A'; GREEN='#95A237'; DARK='#2C3D20'; GREY='#919CA8'
st.markdown('''<style>
.stApp{background:#F1F1F1;color:#0C243A}
[data-testid="stSidebar"]{background:#0C243A}
[data-testid="stSidebar"] label,[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,[data-testid="stSidebar"] h4,[data-testid="stSidebar"] p,[data-testid="stSidebar"] [data-testid="stCaptionContainer"], [data-testid="stSidebar"] .stMarkdown{color:#F1F1F1!important}
.hero{background:linear-gradient(105deg,#0C243A,#2C3D20);border-radius:15px;padding:25px 29px;color:#fff;margin-bottom:13px}
.hero h1{color:#fff;margin:0;font-size:2.1rem;letter-spacing:.05em}
.hero p{color:#f1f1f1;margin:7px 0 0}
.stButton>button[kind="primary"]{background:#95A237;color:#0C243A;border:1px solid #95A237;font-weight:700}
.stButton>button[kind="primary"]:hover{background:#a9b65c;border-color:#95A237;color:#0C243A}
[data-testid="stMetric"]{background:white;border:1px solid #e0e4e8;border-radius:12px;padding:13px}
.stDownloadButton button{border-color:#95A237}
</style>''',unsafe_allow_html=True)

INDEX_DESC={
 'NDVI':'Vigor e cobertura vegetal (NIR e vermelho)',
 'NDRE':'Sensível à resposta red-edge / clorofila',
 'NDMI':'Umidade relativa do dossel (NIR e SWIR1)',
 'NDWI':'Água superficial — fórmula verde/NIR (McFeeters)',
 'EVI':'Vegetação com correção de fundo e efeitos atmosféricos',
 'SAVI':'Índice ajustado ao efeito do solo',
 'ARVI':'Índice de vegetação resistente a efeitos atmosféricos',
 'DVI':'Diferença entre refletância NIR e vermelha',
 'NBR':'Resposta NIR/SWIR2 — não diagnostica incêndios ou doenças',
 'NBR2':'Comparação SWIR1 e SWIR2',
 'GNDVI':'Vigor relacionado à resposta do verde e NIR'}
PALETTE=['8c510a','d8b365','f6e8c3','c7eae5','5ab4ac','01665e']
VIS={name: {'min': (-.2 if name not in ('DVI','EVI','ARVI','NDWI','NBR2') else (-.3 if name in ('ARVI','NDWI','NBR2') else (-.2 if name=='EVI' else -.1))),
            'max': (.9 if name not in ('DVI','EVI','ARVI','NDWI','NBR2') else (.65 if name=='DVI' else 1)), 'palette':PALETTE}
     for name in INDEX_DESC}
MONTHS=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
INITIAL={'geometry':None,'center':(-15.25,-40.25),'zoom':12,'result':None,'points':[], 'trend':[], 'field_name':'Talhão 01','dates':[], 'date_selection':None,'query_year':None,'analysis_signature':None}
for k,v in INITIAL.items():st.session_state.setdefault(k,v)

def normalize(obj):
    if obj.get('type')=='FeatureCollection':
        for f in obj.get('features',[]):
            p=normalize(f)
            if p:return p
        return None
    geom=obj.get('geometry') if obj.get('type')=='Feature' else obj
    if not isinstance(geom,dict) or geom.get('type') not in ('Polygon','MultiPolygon') or not geom.get('coordinates'):return None
    return {'type':'Feature','properties':{},'geometry':geom}

def center(feature):
    coords=[]
    def walk(obj):
        if isinstance(obj,(list,tuple)) and len(obj)>=2 and all(isinstance(x,(float,int)) for x in obj[:2]):coords.append(obj[:2])
        elif isinstance(obj,(list,tuple)):
            for x in obj:walk(x)
    walk(feature['geometry']['coordinates'])
    return ((min(c[1] for c in coords)+max(c[1] for c in coords))/2,(min(c[0] for c in coords)+max(c[0] for c in coords))/2)

def clear_results():
    st.session_state.result=None;st.session_state.points=[];st.session_state.trend=[];st.session_state.analysis_signature=None

def make_map(feature,base,overlay=None,points=None,draw=False):
    m=folium.Map(location=st.session_state.center,zoom_start=st.session_state.zoom,tiles=None,control_scale=True,prefer_canvas=True)
    folium.TileLayer('OpenStreetMap',name='Ruas',show=(base=='Ruas')).add_to(m)
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',attr='Tiles © Esri',name='Satélite',show=(base=='Satélite')).add_to(m)
    if overlay:folium.TileLayer(tiles=overlay,name='Resultado Sentinel-2',attr='Copernicus Sentinel / Google Earth Engine',overlay=True,opacity=.85).add_to(m)
    if feature:folium.GeoJson(feature,name='Talhão',style_function=lambda _:dict(color=GREEN,weight=3,fillOpacity=.035)).add_to(m)
    for p in points or []:
        folium.Marker([p['latitude'],p['longitude']],tooltip=f"Investigação {p['id']}",popup=folium.Popup(f"<b>Ponto {p['id']}</b><br>Área: {p['area_ha']:.2f} ha<br>Máximo: {p['max_hit_years']} de 5 anos",max_width=280),icon=folium.Icon(color='red',icon='info-sign')).add_to(m)
    if draw:Draw(export=False,draw_options={'polyline':False,'rectangle':False,'circle':False,'circlemarker':False,'marker':False,'polygon':True},edit_options={'edit':False,'remove':True}).add_to(m)
    Fullscreen().add_to(m);folium.LayerControl(collapsed=True).add_to(m)
    return m

def kml_points(points):
    parts=['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>']
    for p in points:parts.append(f"<Placemark><name>{escape('Ponto '+str(p['id']))}</name><description>{escape(str(p['max_hit_years'])+' de 5 anos; '+str(p['area_ha'])+' ha')}</description><Point><coordinates>{p['longitude']},{p['latitude']},0</coordinates></Point></Placemark>")
    return ''.join(parts)+'</Document></kml>'

with st.sidebar:
    col_logo,col_title=st.columns([1,3],vertical_alignment='center')
    col_logo.image(str(SYMBOL),use_container_width=True)
    col_title.markdown('### LANDVISION')
    st.caption('SOYBEAN FIELD INTELLIGENCE · V0.4.1')
    st.divider()
    st.markdown('#### 01 · Área de estudo')
    field=st.text_input('Nome do talhão',key='field_name')
    lat=st.number_input('Latitude',-90.0,90.0,float(st.session_state.center[0]),format='%.6f')
    lon=st.number_input('Longitude',-180.0,180.0,float(st.session_state.center[1]),format='%.6f')
    if st.button('Ir para coordenadas',use_container_width=True):
        st.session_state.center=(lat,lon);st.session_state.zoom=15;st.rerun()
    upload=st.file_uploader('Importar polígono (GeoJSON)',type=['geojson','json'])
    if upload and st.button('Usar polígono importado',use_container_width=True):
        try:
            geom=normalize(json.load(upload))
            if geom is None:st.error('Informe um GeoJSON Polygon ou MultiPolygon válido.')
            else:
                st.session_state.geometry=geom;st.session_state.center=center(geom);st.session_state.zoom=15;clear_results();st.session_state.dates=[];st.rerun()
        except (ValueError,TypeError) as e:st.error('Arquivo inválido: '+str(e))
    if st.button('Limpar talhão',use_container_width=True):
        st.session_state.geometry=None;clear_results();st.session_state.dates=[];st.rerun()
    st.caption('Ou desenhe o polígono diretamente no Mapa 1.')
    st.divider()
    st.markdown('#### 02 · Período e índice')
    mode=st.radio('Modo de análise',['PERÍODO','DATA ÚNICA'],horizontal=True)
    chosen=date.today();year=date.today().year;m1=6;m2=9
    if mode=='DATA ÚNICA':
        chosen=st.date_input('Data da cena',value=date(2025,7,15),min_value=date(2019,1,1),max_value=date.today())
        year=chosen.year
    else:
        years=list(range(date.today().year,2022,-1))
        year=st.selectbox('Ano de referência',years,index=min(1,len(years)-1))
        m1=st.selectbox('Mês inicial',range(1,13),index=5,format_func=lambda x:MONTHS[x-1])
        m2=st.selectbox('Mês final',range(1,13),index=8,format_func=lambda x:MONTHS[x-1])
    idx=st.selectbox('Índice do mapa atual',list(INDEX_DESC))
    st.caption(INDEX_DESC[idx])
    base=st.radio('Mapa-base',['Satélite','Ruas'],horizontal=True)
    st.divider()
    st.markdown('#### 03 · Detector de recorrência')
    min_hits=st.slider('Anomalia em pelo menos X dos 5 anos anteriores',3,5,4)
    min_valid=st.slider('Mínimo de anos com pixels válidos',3,5,3)
    min_ha=st.number_input('Área mínima das regiões (ha)',.04,100.,.20,step=.10)
    st.caption('O detector usa NDVI + NDRE + NDMI (score espacial ≥ 2); o seletor acima controla só a camada do Mapa 1.')
    run=st.button('Executar análise',type='primary',use_container_width=True)
    st.divider()
    search=st.button('Buscar melhores datas (até 30)',use_container_width=True)
    st.caption('Busca cenas do ano escolhido com até 25% de nuvens e prioriza cobertura dentro do talhão.')
    test_conn=st.button('Testar conexão Earth Engine',use_container_width=True)
    st.caption('O teste faz uma consulta mínima, sem executar a análise histórica.')

st.markdown('<div class="hero"><h1>LANDVISION</h1><p>Monitoramento multitemporal · Índices espectrais · Pontos de investigação</p></div>',unsafe_allow_html=True)
st.caption('Processamento real sob demanda: somente após conectar o Earth Engine e clicar em Executar análise.')
if test_conn:
    ok, err=connect()
    if not ok: st.error(err)
    else:
        try:
            if connectivity_test(): st.success('Conexão ativa: Earth Engine respondeu à consulta de teste.')
            else: st.warning('A conexão inicializou, mas o teste não retornou o resultado esperado.')
        except Exception as exc:
            st.error('A inicialização ocorreu, mas a consulta falhou ('+type(exc).__name__+'). Confira API habilitada e permissões IAM; não compartilhe suas credenciais.')

if search:
    if not st.session_state.geometry:st.warning('Desenhe ou importe um talhão antes de pesquisar datas.')
    else:
        ok,err=connect()
        if not ok:st.error('Conexão Earth Engine: '+err)
        else:
            with st.spinner('Avaliando cobertura válida do talhão no Sentinel-2...'):
                try:
                    st.session_state.dates=best_dates(st.session_state.geometry,year)
                    st.session_state.query_year=year
                except Exception as exc:st.error('Falha na busca de datas ('+type(exc).__name__+'). Confira área, período e cotas no Earth Engine.')
if st.session_state.dates and st.session_state.query_year==year:
    date_options={f"{d['date']} | cobertura {d['coverage']:.1f}% | nuvens da cena {d['clouds']:.1f}%":d['date'] for d in st.session_state.dates}
    choice=st.selectbox('Melhores datas Sentinel-2 para o talhão',list(date_options))
    st.caption('No modo DATA ÚNICA, escolha no calendário da barra lateral a data sugerida acima. A busca não altera a análise automaticamente.')
    st.code(date_options[choice],language=None)

metrics=st.columns(4)
metrics[0].metric('Talhão',field)
metrics[1].metric('Visualização',idx)
metrics[2].metric('Histórico','5 anos')
metrics[3].metric('Limite de recorrência',f'{min_hits}/5')
signature=json.dumps({'geometry':st.session_state.geometry,'year':year,'m1':m1,'m2':m2,'mode':mode,'date':chosen.isoformat(),'index':idx,'hits':min_hits,'valid':min_valid,'ha':min_ha},sort_keys=True)
if st.session_state.result and signature!=st.session_state.analysis_signature:
    st.info('Os parâmetros foram alterados. Clique em Executar análise para atualizar os resultados; os mapas anteriores não serão apresentados como atuais.')
    clear_results()

if run:
    if not st.session_state.geometry:st.warning('Desenhe ou importe um talhão antes da análise.')
    else:
        ok,err=connect()
        if not ok:st.error('Earth Engine não conectado. '+err+' Veja o README.')
        else:
            with st.spinner('Processando a imagem atual e a recorrência histórica. Aguarde...'):
                try:
                    stage='Medir a área do talhão'
                    # Enforce a conservative area cap before submitting multi-year reductions.
                    hectares=field_hectares(st.session_state.geometry)
                    if hectares > MAX_FIELD_HA:
                        st.warning(f'Área de {hectares:,.1f} ha excede o limite de {MAX_FIELD_HA:,} ha desta versão. Divida o talhão ou reduza a área para preservar a velocidade e as cotas.')
                        st.stop()
                    stage='Preparar análise histórica'
                    out=analyze(st.session_state.geometry,year,m1,m2,mode,chosen,min_hits,min_valid,min_ha,idx)
                    stage='Consultar cenas e pixels válidos da imagem atual'
                    # One server response for two scalar checks.
                    from ee import Dictionary
                    scalars=Dictionary({'scenes':out['current_scenes'],'valid':out['current_valid']}).getInfo()
                    scenes=scalars['scenes'];valid=scalars['valid']
                    if not scenes or valid is None or not valid:
                        clear_results();st.warning('Sem pixels válidos no talhão para essa data/período. Escolha outra data ou janela.')
                    else:
                        stage='Extrair regiões de recorrência'
                        raw=out['regions'].limit(101).getInfo()['features']
                        capped=len(raw)>100;raw=raw[:100]
                        points=[]
                        for i,feat in enumerate(raw,1):
                            p=feat['properties'];points.append({'id':i,'latitude':float(p['latitude']),'longitude':float(p['longitude']),'area_ha':round(float(p['area_ha']),3),'recurrence_pct':round(float(p['recurrence_pct']),1) if p.get('recurrence_pct') is not None else None,'max_hit_years':int(p['max_hit_years']) if p.get('max_hit_years') is not None else 0})
                        stage='Criar camada histórica do mapa'
                        history=tile_url(out['recurrence'],{'min':0,'max':100,'palette':['006837','ffffbf','fdae61','d73027']})
                        stage='Criar camada atual do mapa'
                        current=tile_url(out['current'].select(idx),VIS[idx])
                        stage='Consultar série temporal do gráfico'
                        trend_raw=out['trend'].getInfo()['features']
                        trend=[f['properties'] for f in trend_raw]
                        st.session_state.result={'current':current,'history':history,'regions':{'type':'FeatureCollection','features':raw},'scenes':scenes,'capped':capped,'index':idx}
                        st.session_state.points=points;st.session_state.trend=trend;st.session_state.analysis_signature=signature
                        st.success(f'Análise concluída: {scenes} cenas elegíveis na janela atual; {len(points)} regiões exibidas.'+(' Existem mais de 100 regiões; ajuste os filtros para refinar.' if capped else ''))
                except Exception as exc:
                    clear_results()
                    # Error details stay in the owner-only deployment logs; do not paste Secrets in chat.
                    logging.exception('LandVision processing failed; stage=%s', stage)
                    st.error('Falha na etapa: '+stage+' ('+type(exc).__name__+'). Abra Manage app e consulte o final dos registros privados; não compartilhe chaves ou tokens.')

result=st.session_state.result;points=st.session_state.points
left,right=st.columns(2,gap='medium')
with left:
    st.markdown(f'#### MAPA 1 · {idx} atual')
    st.caption('Desenhe um polígono pelo ícone do mapa. Clique no primeiro vértice para concluir.')
    feedback=st_folium(make_map(st.session_state.geometry,base,overlay=result['current'] if result else None,draw=True),height=510,use_container_width=True,key='landvision_map_drawing',returned_objects=['all_drawings'])
    drawings=(feedback or {}).get('all_drawings') or []
    if drawings:
        candidate=normalize(drawings[-1])
        if candidate and candidate!=st.session_state.geometry:
            st.session_state.geometry=candidate;st.session_state.center=center(candidate);st.session_state.zoom=15;clear_results();st.session_state.dates=[];st.rerun()
with right:
    st.markdown('#### MAPA 2 · Recorrência histórica')
    st.caption('Percentual de anos válidos com score NDVI + NDRE + NDMI ≥ 2.')
    st_folium(make_map(st.session_state.geometry,base,overlay=result['history'] if result else None,points=points),height=510,use_container_width=True,key='landvision_map_history',returned_objects=[])
    st.caption('LEGENDA · Verde: baixa recorrência | Amarelo: intermediária | Vermelho: alta | Transparente: sem dados válidos suficientes ou fora do talhão. O marcador indica o centroide da região.')

if st.session_state.geometry:
    st.download_button('Exportar talhão · GeoJSON',json.dumps(st.session_state.geometry,ensure_ascii=False,indent=2),'landvision_talhao.geojson','application/geo+json')
if result:
    st.markdown('### Série histórica de anomalia espectral')
    st.caption('Percentual de pixels válidos do talhão com score espacial ≥ 2, por ano, na janela sazonal escolhida. Anos sem dados não são interpretados como zero.')
    trend=st.session_state.trend
    df=pd.DataFrame(trend).rename(columns={'year':'Ano','pct':'Área com anomalia (%)'}).sort_values('Ano')
    if not df.empty and df['Área com anomalia (%)'].notna().any():
        st.bar_chart(df.set_index('Ano')['Área com anomalia (%)'],y_label='% dos pixels válidos',x_label='Ano')
        st.dataframe(df,use_container_width=True,hide_index=True)
    else:st.warning('Dados insuficientes para representar a série histórica.')
    st.markdown('### Pontos de investigação')
    if points:
        st.dataframe(pd.DataFrame(points),use_container_width=True,hide_index=True)
        out=io.StringIO();writer=csv.DictWriter(out,fieldnames=points[0].keys());writer.writeheader();writer.writerows(points)
        d1,d2,d3=st.columns(3)
        d1.download_button('Coordenadas CSV',out.getvalue().encode('utf-8-sig'),'landvision_pontos.csv','text/csv',use_container_width=True)
        d2.download_button('Regiões GeoJSON',json.dumps(result['regions'],ensure_ascii=False),'landvision_regioes.geojson','application/geo+json',use_container_width=True)
        d3.download_button('Pontos KML',kml_points(points),'landvision_pontos.kml','application/vnd.google-earth.kml+xml',use_container_width=True)
        if result['capped']:st.warning('Exibição/exportação limitada a 100 regiões; refina os limiares antes de exportar resultados completos.')
    else:st.info('Nenhuma região atendeu aos filtros escolhidos. Isso não demonstra ausência de problemas em campo.')
    st.caption('Coordenadas representam centroides estimados de regiões raster a 20 m. Use os polígonos exportados e confira as condições em campo.')
else:
    st.info('Importe/desenhe o talhão e execute a análise. O mapa-base não é um resultado de NDVI ou de estresse.')
st.divider()
st.caption('LandVision V0.4 · Paleta informada pelo usuário e símbolo enviado · Dados: Sentinel-2 SR Harmonized / Google Earth Engine. Anomalia espectral é um indicador exploratório, não um diagnóstico de nematoides, doença, compactação ou deficiência. Considere cobertura de nuvens, culturas, época de plantio e estádio fenológico. Uso do símbolo deve respeitar as autorizações aplicáveis.')

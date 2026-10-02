"""LandVision v0.1 — interface first; no Earth Engine processing yet."""
import json
from datetime import date
from pathlib import Path

import folium
import streamlit as st
from folium.plugins import Draw, Fullscreen, MeasureControl, MiniMap
from streamlit_folium import st_folium

st.set_page_config(page_title="LandVision | Soybean Field Intelligence", page_icon="🌱", layout="wide", initial_sidebar_state="expanded")

NAVY = "#0C243A"
OLIVE = "#95A237"
st.markdown("""
<style>
.stApp {background: #f4f6f5; color: #0C243A;}
[data-testid="stSidebar"] {background:#0C243A;}
[data-testid="stSidebar"] * {color:#f5f7f8 !important;}
[data-testid="stSidebar"] input {color:#0C243A !important;}
[data-testid="stSidebar"] [data-baseweb="select"] * {color:#0C243A !important;}
.hero {padding:20px 24px; border-radius:15px; background:linear-gradient(115deg,#0C243A,#244153);color:white; margin-bottom:17px;}
.hero h1 {margin:0;font-size:2.1rem;color:white;letter-spacing:.07em;}
.hero p {margin:5px 0 0;color:#e1e9e9;}
.tag {display:inline-block; border:1px solid #9aaa54;border-radius:30px;padding:3px 11px;color:#dce8ab;font-size:.8rem;}
.map-title {font-weight:750;color:#0C243A;font-size:1.08rem;margin:10px 0 5px;}
.note {padding:12px 15px;border-left:4px solid #95A237;background:white;border-radius:6px;color:#394b50;}
[data-testid="stMetric"] {background:white;border-radius:12px;padding:11px 14px;border:1px solid #e4e8e5;}
</style>
""", unsafe_allow_html=True)

for key, default in {"geometry":None,"field_name":"Talhão 01","center":(-15.25,-40.25),"zoom":12,"analysis_requested":False}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def normalize_geojson(obj):
    """Return a polygon GeoJSON Feature or None; first polygon from FeatureCollection."""
    if not isinstance(obj, dict):
        return None
    typ = obj.get("type")
    if typ == "FeatureCollection":
        for feat in obj.get("features", []):
            result = normalize_geojson(feat)
            if result:
                return result
        return None
    if typ == "Feature":
        geom = obj.get("geometry") or {}
        props = obj.get("properties") or {}
    else:
        geom = obj
        props = {}
    if geom.get("type") not in ("Polygon", "MultiPolygon") or not geom.get("coordinates"):
        return None
    return {"type":"Feature","properties":props,"geometry":geom}


def centroid_bbox(feature):
    def flatten(node):
        if isinstance(node, list) and len(node)>=2 and all(isinstance(v,(float,int)) for v in node[:2]):
            yield node[:2]
        elif isinstance(node,list):
            for sub in node:
                yield from flatten(sub)
    points=list(flatten(feature["geometry"]["coordinates"]))
    if not points:
        return None
    lons=[p[0] for p in points]; lats=[p[1] for p in points]
    return ((min(lats)+max(lats))/2,(min(lons)+max(lons))/2), [[min(lats),min(lons)],[max(lats),max(lons)]]


def map_view(title, polygon, center, zoom, draw=False, base="Esri World Imagery"):
    m=folium.Map(location=center, zoom_start=zoom, tiles=None, control_scale=True, prefer_canvas=True)
    folium.TileLayer("OpenStreetMap",name="Mapa de ruas",show=(base=="Mapa de ruas")).add_to(m)
    folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",attr="Tiles © Esri",name="Esri World Imagery",show=(base=="Esri World Imagery")).add_to(m)
    if polygon:
        folium.GeoJson(polygon,name="Talhão selecionado",style_function=lambda _: {"color":"#95A237","weight":3,"fillColor":"#95A237","fillOpacity":.16}).add_to(m)
        cb=centroid_bbox(polygon)
        if cb: m.fit_bounds(cb[1],padding=(18,18))
    if draw:
        Draw(export=False, draw_options={"polyline":False,"rectangle":False,"circle":False,"circlemarker":False,"marker":False,"polygon":True}, edit_options={"edit":False,"remove":True}).add_to(m)
        st.caption("No mapa esquerdo, use o ícone de polígono para desenhar um talhão. Finalize clicando no primeiro vértice.")
    Fullscreen().add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m

with st.sidebar:
    st.markdown("## 🌱 LANDVISION")
    st.caption("SOYBEAN FIELD INTELLIGENCE · v0.1")
    st.divider()
    st.markdown("#### 01 · Localização")
    st.session_state.field_name = st.text_input("Nome do talhão",value=st.session_state.field_name)
    lat=st.number_input("Latitude",min_value=-90.0,max_value=90.0,value=float(st.session_state.center[0]),format="%.6f")
    lon=st.number_input("Longitude",min_value=-180.0,max_value=180.0,value=float(st.session_state.center[1]),format="%.6f")
    if st.button("Ir para coordenadas",use_container_width=True):
        st.session_state.center=(lat,lon)
        st.session_state.zoom=15
        st.rerun()
    uploaded=st.file_uploader("Importar GeoJSON (Polygon/MultiPolygon)",type=["geojson","json"])
    if uploaded is not None and st.button("Usar arquivo importado",use_container_width=True):
        try:
            candidate=normalize_geojson(json.load(uploaded))
            if not candidate: st.error("Não foi encontrado um Polygon ou MultiPolygon válido.")
            else:
                st.session_state.geometry=candidate
                cb=centroid_bbox(candidate)
                if cb: st.session_state.center=cb[0]
                st.session_state.zoom=15
                st.success("Talhão importado.")
        except (ValueError,UnicodeDecodeError,TypeError) as exc:
            st.error(f"Não foi possível ler o arquivo: {exc}")
    if st.button("Limpar talhão",use_container_width=True):
        st.session_state.geometry=None
        st.session_state.analysis_requested=False
        st.rerun()
    st.divider()
    st.markdown("#### 02 · Análise")
    mode=st.radio("Modo",["DATA ÚNICA","PERÍODO"],horizontal=True)
    view=st.selectbox("Visualização",["NDVI","SUSPEITA DE ESTRESSE","NDRE","NDMI"])
    if mode=="DATA ÚNICA":
        selected_date=st.date_input("Data exata",value=date(2026,7,15),format="YYYY-MM-DD")
        period_label=selected_date.isoformat()
    else:
        year=st.selectbox("Ano",list(range(2026,2016,-1)))
        months=["01 · Janeiro","02 · Fevereiro","03 · Março","04 · Abril","05 · Maio","06 · Junho","07 · Julho","08 · Agosto","09 · Setembro","10 · Outubro","11 · Novembro","12 · Dezembro"]
        m1=st.selectbox("Mês inicial",months,index=5)
        m2=st.selectbox("Mês final",months,index=8)
        period_label=f"{year} · {m1} → {m2}"
    st.divider()
    st.markdown("#### 03 · Camadas")
    basemap=st.radio("Mapa-base",["Esri World Imagery","Mapa de ruas"])
    if st.button("Atualizar análise",type="primary",use_container_width=True):
        st.session_state.analysis_requested=True
    st.caption("Etapa 1: interface e gestão de polígonos. O processamento Sentinel-2 será integrado na etapa 2.")

st.markdown('<div class="hero"><span class="tag">INTERFACE INICIAL · V0.1</span><h1>LANDVISION</h1><p>Monitoramento multitemporal e apoio à tomada de decisão para áreas agrícolas.</p></div>',unsafe_allow_html=True)

c1,c2,c3,c4=st.columns(4)
c1.metric("Área ativa",st.session_state.field_name)
c2.metric("Modo",mode)
c3.metric("Índice",view)
c4.metric("Histórico previsto","5 anos")
st.markdown(f"**Referência:** {period_label} · **Fonte planejada:** Sentinel-2 SR Harmonized")
if st.session_state.analysis_requested:
    st.info("A interface recebeu sua seleção. Os resultados reais de NDVI, NDRE, NDMI e recorrência serão habilitados após integrar o motor GEE da V20.2. Nenhuma análise foi simulada.")

left,right=st.columns(2,gap="medium")
with left:
    st.markdown('<div class="map-title">MAPA 1 · Situação atual</div>',unsafe_allow_html=True)
    result=st_folium(map_view("Atual",st.session_state.geometry,st.session_state.center,st.session_state.zoom,draw=True,base=basemap),height=470,use_container_width=True,key="map_current",returned_objects=["all_drawings"])
    drawings=(result or {}).get("all_drawings") or []
    # Persist the last polygon submitted via the map drawing tool.
    if drawings:
        candidate=normalize_geojson(drawings[-1])
        if candidate and candidate != st.session_state.geometry:
            st.session_state.geometry=candidate
            cb=centroid_bbox(candidate)
            if cb: st.session_state.center=cb[0]
            st.rerun()
    st.caption("Selecione um polígono; dados espectrais ainda não conectados.")
with right:
    st.markdown('<div class="map-title">MAPA 2 · Recorrência histórica</div>',unsafe_allow_html=True)
    st_folium(map_view("Histórico",st.session_state.geometry,st.session_state.center,st.session_state.zoom,base=basemap),height=470,use_container_width=True,key="map_history",returned_objects=[])
    st.caption("Área vinculada ao mapa 1. Camada histórica real entrará na etapa 2.")

st.markdown("### Evolução temporal")
st.markdown('<div class="note">O gráfico de percentual do talhão com suspeita de estresse será calculado somente após a conexão com o Google Earth Engine. Critério previsto: mesmo período em cada um dos cinco anos anteriores, com tratamento de anos sem dados.</div>',unsafe_allow_html=True)
if st.session_state.geometry:
    st.download_button("⬇ Exportar talhão GeoJSON",data=json.dumps(st.session_state.geometry,ensure_ascii=False,indent=2),file_name="landvision_talhao.geojson",mime="application/geo+json")
else:
    st.info("Desenhe um talhão no primeiro mapa ou importe um GeoJSON para habilitar a exportação.")
st.caption("LandVision v0.1 · Protótipo de interface · Suspeita de estresse não constitui diagnóstico de doença.")

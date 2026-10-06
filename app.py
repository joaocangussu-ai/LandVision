"""LandVision V0.7 — Professional UI over the validated V0.6.1 analytical core."""
import base64
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
from folium.plugins import Draw, Fullscreen
from streamlit_folium import st_folium

from engine import (
    BANDS,
    DEFAULT_DIRECTIONS,
    MAX_FIELD_HA,
    MULTI,
    analysis_scale,
    analyze,
    best_dates,
    concordance_analyze,
    concordance_region_series,
    connect,
    connectivity_test,
    field_hectares,
    region_series,
    tile_url,
)

ROOT = Path(__file__).parent
SYMBOL = ROOT / 'assets' / 'simbolo_enviado.png'
LOGO_URI = 'data:image/png;base64,' + base64.b64encode(SYMBOL.read_bytes()).decode('ascii')
st.set_page_config(
    page_title='LandVision | Field Intelligence',
    page_icon=str(SYMBOL),
    layout='wide',
    initial_sidebar_state='expanded',
)

NAVY = '#0C243A'
GREEN = '#95A237'
DARK = '#2C3D20'
GREY = '#919CA8'

st.markdown(
    '''<style>
    :root{
      --lv-navy:#0C243A;--lv-navy-2:#15374E;--lv-dark:#2C3D20;--lv-green:#95A237;
      --lv-green-2:#B1BD55;--lv-muted:#71808D;--lv-bg:#F4F6F3;--lv-card:#FFFFFF;
      --lv-border:rgba(12,36,58,.10);--lv-shadow:0 14px 34px rgba(12,36,58,.08);
    }
    html,body,[class*="css"]{font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .stApp{
      color:var(--lv-navy);
      background:
        radial-gradient(circle at 6% -4%, rgba(149,162,55,.17) 0, transparent 28rem),
        radial-gradient(circle at 100% 4%, rgba(12,36,58,.10) 0, transparent 34rem),
        linear-gradient(180deg,#F9FAF8 0%,#F3F5F2 48%,#EEF2EF 100%);
      background-attachment:fixed;
    }
    [data-testid="stAppViewContainer"]>.main{background:transparent}
    .block-container{max-width:1500px;padding-top:1.35rem;padding-bottom:3rem}
    [data-testid="stSidebar"]{
      background:
        radial-gradient(rgba(255,255,255,.055) 1px,transparent 1px),
        linear-gradient(180deg,#0B263D 0%,#0C243A 58%,#122E43 100%);
      background-size:22px 22px,auto;
      border-right:1px solid rgba(255,255,255,.07);
    }
    [data-testid="stSidebar"]>div:first-child{padding-top:1rem}
    [data-testid="stSidebar"] label,[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,[data-testid="stSidebar"] h4,[data-testid="stSidebar"] p,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"], [data-testid="stSidebar"] .stMarkdown{
      color:#F5F7F2!important
    }
    [data-testid="stSidebar"] .stTextInput input,[data-testid="stSidebar"] .stNumberInput input,
    [data-testid="stSidebar"] [data-baseweb="select"]>div{
      background:rgba(255,255,255,.96);border-radius:10px;border-color:rgba(255,255,255,.18)
    }
    .brand-shell{display:flex;align-items:center;gap:13px;padding:12px 11px 15px;margin:0 0 6px;border-bottom:1px solid rgba(255,255,255,.10)}
    .brand-logo{width:58px;height:58px;object-fit:contain;background:white;border-radius:14px;padding:5px;box-shadow:0 8px 24px rgba(0,0,0,.18)}
    .brand-name{font-size:1.12rem;font-weight:800;letter-spacing:.08em;color:#fff;line-height:1.1}
    .brand-sub{font-size:.68rem;letter-spacing:.10em;color:#BFC8CF;margin-top:5px;text-transform:uppercase}
    .side-version{display:inline-block;margin-top:7px;padding:3px 8px;border-radius:999px;background:rgba(149,162,55,.16);color:#DCE7A1;font-size:.69rem;font-weight:700}
    .hero-professional{
      position:relative;overflow:hidden;border-radius:24px;padding:31px 34px;margin-bottom:14px;
      background:linear-gradient(120deg,#071D30 0%,#0C243A 48%,#263B22 100%);
      box-shadow:0 22px 55px rgba(12,36,58,.16);border:1px solid rgba(255,255,255,.10)
    }
    .hero-professional:before{content:"";position:absolute;width:420px;height:420px;border-radius:50%;right:-135px;top:-220px;border:1px solid rgba(177,189,85,.22);box-shadow:0 0 0 55px rgba(177,189,85,.045),0 0 0 110px rgba(177,189,85,.03)}
    .hero-professional:after{content:"";position:absolute;inset:0;background:linear-gradient(135deg,transparent 55%,rgba(149,162,55,.08));pointer-events:none}
    .hero-inner{position:relative;z-index:1;display:flex;align-items:center;gap:23px}
    .hero-logo-wrap{width:92px;height:92px;min-width:92px;border-radius:22px;background:rgba(255,255,255,.96);display:flex;align-items:center;justify-content:center;box-shadow:0 12px 26px rgba(0,0,0,.18)}
    .hero-logo{width:78px;height:78px;object-fit:contain}
    .hero-eyebrow{font-size:.72rem;color:#D4DF8F;letter-spacing:.16em;font-weight:800;text-transform:uppercase;margin-bottom:6px}
    .hero-title{font-size:2.42rem;line-height:1.03;color:#fff;font-weight:850;letter-spacing:.055em;margin:0}
    .hero-copy{font-size:1rem;color:#DDE5E8;margin-top:9px;max-width:820px}
    .hero-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
    .hero-chip{font-size:.76rem;font-weight:700;color:#EFF3F5;background:rgba(255,255,255,.075);border:1px solid rgba(255,255,255,.12);padding:6px 10px;border-radius:999px}
    .hero-chip.accent{color:#EFF4CA;border-color:rgba(177,189,85,.32);background:rgba(149,162,55,.12)}
    .info-bar{display:flex;justify-content:space-between;gap:14px;align-items:center;background:rgba(255,255,255,.72);border:1px solid var(--lv-border);box-shadow:0 8px 24px rgba(12,36,58,.04);backdrop-filter:blur(8px);border-radius:14px;padding:10px 14px;margin:0 0 16px;color:#536573;font-size:.84rem}
    .status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#95A237;box-shadow:0 0 0 4px rgba(149,162,55,.13);margin-right:8px}
    [data-testid="stMetric"]{background:rgba(255,255,255,.92);border:1px solid var(--lv-border);border-radius:16px;padding:15px 16px;box-shadow:0 10px 28px rgba(12,36,58,.055)}
    [data-testid="stMetricLabel"]{color:#697985}
    [data-testid="stMetricValue"]{color:#0C243A;font-weight:740}
    .section-banner{margin:26px 0 11px;padding:0 0 10px;border-bottom:1px solid rgba(12,36,58,.10)}
    .section-kicker{font-size:.69rem;letter-spacing:.13em;font-weight:800;color:#95A237;text-transform:uppercase}
    .section-title{font-size:1.45rem;font-weight:800;color:#0C243A;margin-top:2px}
    .section-copy{font-size:.88rem;color:#6F7E89;margin-top:3px;max-width:950px}
    .region-summary{background:linear-gradient(135deg,#FFFFFF 0%,#F7F9F2 100%);border:1px solid rgba(149,162,55,.28);border-left:6px solid #95A237;border-radius:16px;padding:19px 21px;margin:10px 0 14px;box-shadow:0 12px 30px rgba(12,36,58,.055)}
    .region-summary h4{margin:0 0 8px;color:#0C243A}.region-summary p{margin:6px 0;color:#344957}
    .summary-callout{background:linear-gradient(115deg,rgba(12,36,58,.97),rgba(44,61,32,.96));border-radius:16px;padding:16px 18px;color:white;margin:10px 0 14px;box-shadow:0 14px 30px rgba(12,36,58,.12)}
    .summary-callout b{color:#E8F0B2}.summary-callout small{color:#CBD5DA}
    iframe{border-radius:16px!important}
    [data-testid="stDataFrame"]{border-radius:14px;overflow:hidden;border:1px solid rgba(12,36,58,.08)}
    .stButton>button,.stDownloadButton>button{border-radius:11px;min-height:2.65rem;font-weight:680;transition:.16s ease;border-color:rgba(12,36,58,.16)}
    .stButton>button:hover,.stDownloadButton>button:hover{transform:translateY(-1px);box-shadow:0 8px 18px rgba(12,36,58,.09);border-color:#95A237;color:#0C243A}
    .stButton>button[kind="primary"]{background:linear-gradient(135deg,#A7B444,#95A237);color:#0C243A;border:none;box-shadow:0 9px 22px rgba(149,162,55,.22)}
    .stButton>button[kind="primary"]:hover{background:linear-gradient(135deg,#B5C15A,#9EAA3D);color:#0C243A}
    [data-testid="stExpander"]{background:rgba(255,255,255,.72);border-radius:12px;border-color:rgba(12,36,58,.08)}
    hr{border-color:rgba(12,36,58,.09)!important}
    @media(max-width:800px){.hero-professional{padding:23px 20px}.hero-logo-wrap{width:70px;height:70px;min-width:70px}.hero-logo{width:58px;height:58px}.hero-title{font-size:1.75rem}.hero-inner{gap:14px}.info-bar{display:block}}
    </style>''',
    unsafe_allow_html=True,
)

INDEX_DESC = {
    'NDVI': 'Vigor e cobertura vegetal (NIR e vermelho)',
    'NDRE': 'Sensível à resposta red-edge / clorofila',
    'NDMI': 'Umidade relativa do dossel (NIR e SWIR1)',
    'NDWI': 'Água superficial — fórmula verde/NIR (McFeeters)',
    'EVI': 'Vegetação com correção de fundo e efeitos atmosféricos',
    'SAVI': 'Índice ajustado ao efeito do solo',
    'ARVI': 'Índice de vegetação resistente a efeitos atmosféricos',
    'DVI': 'Diferença entre refletância NIR e vermelha',
    'NBR': 'Resposta NIR/SWIR2 — não diagnostica incêndios ou doenças',
    'NBR2': 'Comparação SWIR1 e SWIR2',
    'GNDVI': 'Vigor relacionado à resposta do verde e NIR',
    MULTI: 'Detector original NDVI + NDRE + NDMI (2 de 3 sinais)',
}

PALETTE = ['8c510a', 'd8b365', 'f6e8c3', 'c7eae5', '5ab4ac', '01665e']
VIS = {
    name: {
        'min': (-.2 if name not in ('DVI', 'EVI', 'ARVI', 'NDWI', 'NBR2') else
                (-.3 if name in ('ARVI', 'NDWI', 'NBR2') else (-.2 if name == 'EVI' else -.1))),
        'max': (.9 if name not in ('DVI', 'EVI', 'ARVI', 'NDWI', 'NBR2') else
                (.65 if name == 'DVI' else 1)),
        'palette': PALETTE,
    }
    for name in INDEX_DESC
}
VIS[MULTI] = {'min': 0, 'max': 3, 'palette': ['0b7d20', '9bd770', 'fff176', 'ef5350']}
RECURRENCE_VIS = {'min': 0, 'max': 100, 'palette': ['006837', 'ffffbf', 'fdae61', 'd73027']}
CONCORD_PALETTE = ['006837', 'a6d96a', 'ffffbf', 'fdae61', 'f46d43', 'd73027', '7f0000']
MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

INITIAL = {
    'geometry': None,
    'center': (-15.25, -40.25),
    'zoom': 12,
    'result': None,
    'points': [],
    'trend': [],
    'field_name': 'Talhão 01',
    'dates': [],
    'date_selection': None,
    'query_year': None,
    'analysis_signature': None,
    'ee_yearly': None,
    'region_details': {},
    'concord_result': None,
    'concord_points': [],
    'concord_trend': [],
    'concord_signature': None,
    'ee_concord_yearly': None,
    'concord_details': {},
}
for key, value in INITIAL.items():
    st.session_state.setdefault(key, value)


def normalize(obj):
    if obj.get('type') == 'FeatureCollection':
        for feature in obj.get('features', []):
            polygon = normalize(feature)
            if polygon:
                return polygon
        return None
    geom = obj.get('geometry') if obj.get('type') == 'Feature' else obj
    if not isinstance(geom, dict) or geom.get('type') not in ('Polygon', 'MultiPolygon') or not geom.get('coordinates'):
        return None
    return {'type': 'Feature', 'properties': {}, 'geometry': geom}


def center(feature):
    coords = []

    def walk(obj):
        if isinstance(obj, (list, tuple)) and len(obj) >= 2 and all(isinstance(x, (float, int)) for x in obj[:2]):
            coords.append(obj[:2])
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                walk(item)

    walk(feature['geometry']['coordinates'])
    return (
        (min(c[1] for c in coords) + max(c[1] for c in coords)) / 2,
        (min(c[0] for c in coords) + max(c[0] for c in coords)) / 2,
    )


def clear_main_results():
    st.session_state.result = None
    st.session_state.points = []
    st.session_state.trend = []
    st.session_state.analysis_signature = None
    st.session_state.ee_yearly = None
    st.session_state.region_details = {}


def clear_concordance():
    st.session_state.concord_result = None
    st.session_state.concord_points = []
    st.session_state.concord_trend = []
    st.session_state.concord_signature = None
    st.session_state.ee_concord_yearly = None
    st.session_state.concord_details = {}


def clear_results():
    clear_main_results()
    clear_concordance()


def make_map(feature, base, overlay=None, points=None, draw=False):
    m = folium.Map(
        location=st.session_state.center,
        zoom_start=st.session_state.zoom,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )
    folium.TileLayer('OpenStreetMap', name='Ruas', show=(base == 'Ruas')).add_to(m)
    folium.TileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles © Esri',
        name='Satélite',
        show=(base == 'Satélite'),
    ).add_to(m)
    if overlay:
        folium.TileLayer(
            tiles=overlay,
            name='Resultado Sentinel-2',
            attr='Copernicus Sentinel / Google Earth Engine',
            overlay=True,
            opacity=.85,
        ).add_to(m)
    if feature:
        folium.GeoJson(
            feature,
            name='Talhão',
            style_function=lambda _: dict(color=GREEN, weight=3, fillOpacity=.035),
        ).add_to(m)
    for point in points or []:
        years = point.get('max_hit_years', point.get('max_concord_years', 0))
        extra = ''
        if 'max_indices_same_year' in point:
            extra = f"<br>Máx. índices no mesmo ano: {point['max_indices_same_year']}"
        folium.Marker(
            [point['latitude'], point['longitude']],
            tooltip=f"Investigação {point['id']}",
            popup=folium.Popup(
                f"<b>Ponto {point['id']}</b><br>Área: {point['area_ha']:.2f} ha<br>Recorrência: {years} de 5 anos{extra}",
                max_width=300,
            ),
            icon=folium.Icon(color='red', icon='info-sign'),
        ).add_to(m)
    if draw:
        Draw(
            export=False,
            draw_options={
                'polyline': False,
                'rectangle': False,
                'circle': False,
                'circlemarker': False,
                'marker': False,
                'polygon': True,
            },
            edit_options={'edit': False, 'remove': True},
        ).add_to(m)
    Fullscreen().add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def kml_points(points):
    parts = ['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>']
    for point in points:
        years = point.get('max_hit_years', point.get('max_concord_years', 0))
        desc = f"{years} de 5 anos; {point['area_ha']} ha"
        if 'max_indices_same_year' in point:
            desc += f"; até {point['max_indices_same_year']} índices no mesmo ano"
        parts.append(
            f"<Placemark><name>{escape('Ponto '+str(point['id']))}</name>"
            f"<description>{escape(desc)}</description><Point><coordinates>"
            f"{point['longitude']},{point['latitude']},0</coordinates></Point></Placemark>"
        )
    return ''.join(parts) + '</Document></kml>'



def _safe_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _priority_label(point):
    """Exploratory priority based only on LandVision recurrence/concordance outputs."""
    years = int(_safe_float(point.get('max_concord_years'), 0))
    indices = int(_safe_float(point.get('max_indices_same_year'), 0))
    recurrence = _safe_float(point.get('recurrence_pct'), 0)
    if years >= 5 and indices >= 3 and recurrence >= 60:
        return 'MUITO ALTA'
    if (years >= 4 and indices >= 3) or (years >= 4 and recurrence >= 50):
        return 'ALTA'
    if years >= 3 and indices >= 2:
        return 'MODERADA'
    return 'EXPLORATÓRIA'


def _concordance_region_summary(point, detail_df, indices, min_indices, scale):
    """Build a deterministic, non-diagnostic summary from already computed results."""
    frame = detail_df.sort_values('year').copy()
    if frame.empty:
        return None
    reference_year = int(frame['year'].max())
    historical = frame[frame['year'] < reference_year]
    current = frame[frame['year'] == reference_year]

    center_counts = {}
    valid_counts = {}
    for name in indices:
        col = name + '_center'
        if col not in historical:
            center_counts[name] = 0
            valid_counts[name] = 0
            continue
        vals = pd.to_numeric(historical[col], errors='coerce')
        valid_counts[name] = int(vals.notna().sum())
        center_counts[name] = int((vals.fillna(-1) >= .5).sum())

    common_valid = 0
    center_concord_years = 0
    if not historical.empty:
        center_cols = [name + '_center' for name in indices if name + '_center' in historical]
        if center_cols:
            numeric = historical[center_cols].apply(pd.to_numeric, errors='coerce')
            valid_mask = numeric.notna().all(axis=1)
            common_valid = int(valid_mask.sum())
            if common_valid:
                center_concord_years = int(((numeric.fillna(0) >= .5).sum(axis=1) >= min_indices)[valid_mask].sum())

    current_anomalous = []
    if not current.empty:
        row = current.iloc[0]
        for name in indices:
            val = row.get(name + '_center')
            if pd.notna(val) and _safe_float(val) >= .5:
                current_anomalous.append(name)

    max_years = int(_safe_float(point.get('max_concord_years'), 0))
    max_indices = int(_safe_float(point.get('max_indices_same_year'), 0))
    recurrence = _safe_float(point.get('recurrence_pct'), 0)
    area = _safe_float(point.get('area_ha'), 0)
    priority = _priority_label(point)

    recurrent_names = [name for name in indices if center_counts.get(name, 0) >= 3]
    if priority in ('MUITO ALTA', 'ALTA'):
        interpretation = ('Padrão espacial multiespectral recorrente. Esta região merece prioridade de inspeção de campo, '
                          'especialmente se o padrão também coincidir com informações de solo, drenagem, manejo ou produtividade.')
    elif priority == 'MODERADA':
        interpretation = ('Há repetição espacial suficiente para justificar acompanhamento. A intensidade e os índices envolvidos '
                          'devem ser comparados com o histórico agronômico antes de priorizar intervenção.')
    else:
        interpretation = ('O sinal é exploratório. Use-o como indicação de onde conferir dados adicionais, sem interpretar a anomalia '
                          'como diagnóstico de uma causa específica.')

    return {
        'priority': priority,
        'reference_year': reference_year,
        'area': area,
        'recurrence': recurrence,
        'max_years': max_years,
        'max_indices': max_indices,
        'center_counts': center_counts,
        'valid_counts': valid_counts,
        'common_valid': common_valid,
        'center_concord_years': center_concord_years,
        'current_anomalous': current_anomalous,
        'recurrent_names': recurrent_names,
        'interpretation': interpretation,
        'scale': scale,
    }


# -----------------------------------------------------------------------------
# SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f'''<div class="brand-shell"><img class="brand-logo" src="{LOGO_URI}">
        <div><div class="brand-name">LANDVISION</div><div class="brand-sub">GDM Seeds · Field Intelligence</div>
        <span class="side-version">Professional · V0.7</span></div></div>''',
        unsafe_allow_html=True,
    )

    st.markdown('#### 01 · Área de estudo')
    field = st.text_input('Nome do talhão', key='field_name')
    lat = st.number_input('Latitude', -90.0, 90.0, float(st.session_state.center[0]), format='%.6f')
    lon = st.number_input('Longitude', -180.0, 180.0, float(st.session_state.center[1]), format='%.6f')
    if st.button('Ir para coordenadas', use_container_width=True):
        st.session_state.center = (lat, lon)
        st.session_state.zoom = 15
        st.rerun()

    upload = st.file_uploader('Importar polígono (GeoJSON)', type=['geojson', 'json'])
    if upload and st.button('Usar polígono importado', use_container_width=True):
        try:
            geom = normalize(json.load(upload))
            if geom is None:
                st.error('Informe um GeoJSON Polygon ou MultiPolygon válido.')
            else:
                st.session_state.geometry = geom
                st.session_state.center = center(geom)
                st.session_state.zoom = 15
                clear_results()
                st.session_state.dates = []
                st.rerun()
        except (ValueError, TypeError) as exc:
            st.error('Arquivo inválido: ' + str(exc))

    if st.button('Limpar talhão', use_container_width=True):
        st.session_state.geometry = None
        clear_results()
        st.session_state.dates = []
        st.rerun()
    st.caption('Ou desenhe o polígono diretamente no Mapa 1.')
    st.divider()

    st.markdown('#### 02 · Período e índice')
    mode = st.radio('Modo de análise', ['PERÍODO', 'DATA ÚNICA'], horizontal=True)
    chosen = date.today()
    year = date.today().year
    m1, m2 = 6, 9
    if mode == 'DATA ÚNICA':
        chosen = st.date_input(
            'Data da cena',
            value=date(2025, 7, 15),
            min_value=date(2019, 1, 1),
            max_value=date.today(),
        )
        year = chosen.year
    else:
        years = list(range(date.today().year, 2022, -1))
        year = st.selectbox('Ano de referência', years, index=min(1, len(years) - 1))
        m1 = st.selectbox('Mês inicial', range(1, 13), index=5, format_func=lambda x: MONTHS[x - 1])
        m2 = st.selectbox('Mês final', range(1, 13), index=8, format_func=lambda x: MONTHS[x - 1])

    idx = st.selectbox('Índice para os dois mapas e toda a série histórica', list(INDEX_DESC))
    st.caption(INDEX_DESC[idx])
    main_scale = analysis_scale(idx)
    st.caption(f'Resolução efetiva usada na detecção/delimitação: {main_scale} m.')

    if idx == MULTI:
        direction = 'Combinado'
        threshold = 1.0
        st.caption('Critério fixo original: NDVI e NDRE abaixo de −1 DP; NDMI com |Z| > 1; pelo menos 2 sinais.')
    else:
        direction = st.selectbox(
            'Direção da anomalia no talhão',
            ['Abaixo', 'Acima', 'Ambos'],
            index=['Abaixo', 'Acima', 'Ambos'].index(DEFAULT_DIRECTIONS[idx]),
            help='Abaixo: Z < −limiar; Acima: Z > limiar; Ambos: |Z| > limiar.',
        )
        threshold = st.slider('Intensidade mínima |Z| (desvios-padrão)', .5, 2.5, 1.0, .1)
        st.caption('São desvios em relação à distribuição espacial do próprio talhão na mesma época de cada ano.')

    base = st.radio('Mapa-base', ['Satélite', 'Ruas'], horizontal=True)
    st.divider()

    st.markdown('#### 03 · Detector de recorrência')
    min_hits = st.slider('Anomalia em pelo menos X dos 5 anos anteriores', 3, 5, 4)
    min_valid = st.slider('Mínimo de anos com pixels válidos', 3, 5, 3)
    min_ha = st.number_input('Área mínima das regiões (ha)', .04, 100., .20, step=.10)
    st.caption('O índice e a direção escolhidos controlam o mapa atual, a recorrência, o gráfico e os pontos.')
    run = st.button('Executar análise', type='primary', use_container_width=True)

    st.divider()
    st.markdown('#### 04 · Concordância multíndice · opcional')
    concord_indices = st.multiselect(
        'Índices a comparar no mesmo local',
        list(BANDS),
        default=['NDVI', 'NDRE', 'NDMI'],
        max_selections=4,
        help='É calculada apenas quando você clicar no botão abaixo. Máximo de 4 índices para manter o processamento controlado.',
    )
    concord_directions = {}
    concord_min_indices = 2
    concord_min_years = 3
    concord_min_valid = 3
    concord_min_ha = .20
    concord_threshold = 1.0
    run_concord = False

    if len(concord_indices) >= 2:
        concord_scale = analysis_scale(concord_indices)
        load_label = 'leve' if len(concord_indices) == 2 else ('moderada' if len(concord_indices) == 3 else 'alta')
        st.caption(f'Grade comum de comparação: {concord_scale} m · carga estimada: {load_label}.')
        concord_min_indices = st.slider(
            'Mínimo de índices anômalos no mesmo pixel/ano',
            2,
            len(concord_indices),
            min(2, len(concord_indices)),
        )
        concord_min_years = st.slider('Concordância em pelo menos X dos 5 anos anteriores', 2, 5, 3)
        concord_min_valid = st.slider('Anos válidos mínimos · concordância', 3, 5, 3)
        concord_min_ha = st.number_input('Área mínima da concordância (ha)', .04, 100., .20, step=.10)
        concord_threshold = st.slider('Limiar |Z| da concordância', .5, 2.5, 1.0, .1)
        with st.expander('Direção da anomalia por índice'):
            for name in concord_indices:
                concord_directions[name] = st.selectbox(
                    name,
                    ['Abaixo', 'Acima', 'Ambos'],
                    index=['Abaixo', 'Acima', 'Ambos'].index(DEFAULT_DIRECTIONS[name]),
                    key=f'concord_direction_{name}',
                )
        run_concord = st.button('Analisar concordância multíndice', use_container_width=True)
        st.caption('Só este botão executa a análise extra. O uso normal por índice continua independente.')
    else:
        concord_scale = 20
        st.caption('Selecione pelo menos dois índices para habilitar a concordância.')

    st.divider()
    search = st.button('Buscar melhores datas (até 30)', use_container_width=True)
    st.caption('Busca cenas do ano escolhido com até 25% de nuvens e prioriza cobertura dentro do talhão.')
    test_conn = st.button('Testar conexão Earth Engine', use_container_width=True)
    st.caption('O teste faz uma consulta mínima, sem executar a análise histórica.')


# -----------------------------------------------------------------------------
# HEADER / CONNECTION / DATE SEARCH
# -----------------------------------------------------------------------------
st.markdown(
    f'''<div class="hero-professional"><div class="hero-inner">
      <div class="hero-logo-wrap"><img class="hero-logo" src="{LOGO_URI}"></div>
      <div><div class="hero-eyebrow">Satellite Field Intelligence · GDM Seeds</div>
      <div class="hero-title">LANDVISION</div>
      <div class="hero-copy">Inteligência espacial para monitoramento multitemporal, recorrência histórica e investigação de zonas agrícolas.</div>
      <div class="hero-chips"><span class="hero-chip accent">Sentinel-2 SR Harmonized</span><span class="hero-chip">Google Earth Engine</span><span class="hero-chip">Histórico 5 anos</span><span class="hero-chip">Concordância Multíndice</span></div>
      </div></div></div>''',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="info-bar"><span><span class="status-dot"></span>Processamento sob demanda · núcleo analítico V0.6.1 preservado.</span><span>Resultados espectrais exploratórios · validar em campo</span></div>',
    unsafe_allow_html=True,
)

if test_conn:
    ok, err = connect()
    if not ok:
        st.error(err)
    else:
        try:
            if connectivity_test():
                st.success('Conexão ativa: Earth Engine respondeu à consulta de teste.')
            else:
                st.warning('A conexão inicializou, mas o teste não retornou o resultado esperado.')
        except Exception as exc:
            st.error('A inicialização ocorreu, mas a consulta falhou (' + type(exc).__name__ + '). Confira API e IAM; não compartilhe credenciais.')

if search:
    if not st.session_state.geometry:
        st.warning('Desenhe ou importe um talhão antes de pesquisar datas.')
    else:
        ok, err = connect()
        if not ok:
            st.error('Conexão Earth Engine: ' + err)
        else:
            with st.spinner('Avaliando cobertura válida do talhão no Sentinel-2...'):
                try:
                    st.session_state.dates = best_dates(st.session_state.geometry, year)
                    st.session_state.query_year = year
                except Exception as exc:
                    st.error('Falha na busca de datas (' + type(exc).__name__ + '). Confira área, período e cotas no Earth Engine.')

if st.session_state.dates and st.session_state.query_year == year:
    date_options = {
        f"{d['date']} | cobertura {d['coverage']:.1f}% | nuvens da cena {d['clouds']:.1f}%": d['date']
        for d in st.session_state.dates
    }
    choice = st.selectbox('Melhores datas Sentinel-2 para o talhão', list(date_options))
    st.caption('No modo DATA ÚNICA, escolha no calendário da barra lateral a data sugerida acima. A busca não altera a análise automaticamente.')
    st.code(date_options[choice], language=None)

metrics = st.columns(4)
metrics[0].metric('Talhão', field)
metrics[1].metric('Análise', 'Multi' if idx == MULTI else idx)
metrics[2].metric('Histórico', '5 anos')
metrics[3].metric('Resolução efetiva', f'{main_scale} m')

signature = json.dumps({
    'geometry': st.session_state.geometry,
    'year': year,
    'm1': m1,
    'm2': m2,
    'mode': mode,
    'date': chosen.isoformat(),
    'index': idx,
    'direction': direction,
    'threshold': threshold,
    'hits': min_hits,
    'valid': min_valid,
    'ha': min_ha,
}, sort_keys=True)

if st.session_state.result and signature != st.session_state.analysis_signature:
    st.info('Os parâmetros da análise individual foram alterados. Clique em Executar análise para atualizar os resultados.')
    clear_main_results()

concord_signature = json.dumps({
    'geometry': st.session_state.geometry,
    'year': year,
    'm1': m1,
    'm2': m2,
    'mode': mode,
    'date': chosen.isoformat(),
    'indices': concord_indices,
    'directions': concord_directions,
    'threshold': concord_threshold,
    'min_indices': concord_min_indices,
    'min_years': concord_min_years,
    'min_valid': concord_min_valid,
    'ha': concord_min_ha,
}, sort_keys=True)
if st.session_state.concord_result and concord_signature != st.session_state.concord_signature:
    st.info('Os parâmetros da concordância foram alterados. Clique em Analisar concordância multíndice para atualizar essa seção.')
    clear_concordance()


# -----------------------------------------------------------------------------
# INDEX-SPECIFIC ANALYSIS — V0.5 CORE PRESERVED
# -----------------------------------------------------------------------------
if run:
    if not st.session_state.geometry:
        st.warning('Desenhe ou importe um talhão antes da análise.')
    else:
        ok, err = connect()
        if not ok:
            st.error('Earth Engine não conectado. ' + err + ' Veja o README.')
        else:
            with st.spinner('Processando a imagem atual e a recorrência histórica. Aguarde...'):
                try:
                    stage = 'Medir a área do talhão'
                    hectares = field_hectares(st.session_state.geometry)
                    if hectares > MAX_FIELD_HA:
                        st.warning(f'Área de {hectares:,.1f} ha excede o limite de {MAX_FIELD_HA:,} ha. Divida o talhão para preservar velocidade e cotas.')
                        st.stop()
                    stage = 'Preparar análise histórica'
                    out = analyze(
                        st.session_state.geometry,
                        year, m1, m2, mode, chosen,
                        min_hits, min_valid, min_ha,
                        idx, direction, threshold,
                    )
                    stage = 'Consultar cenas e pixels válidos da imagem atual'
                    from ee import Dictionary
                    scalars = Dictionary({'scenes': out['current_scenes'], 'valid': out['current_valid']}).getInfo()
                    scenes, valid = scalars['scenes'], scalars['valid']
                    if not scenes or valid is None or not valid:
                        clear_main_results()
                        st.warning('Sem pixels válidos no talhão para essa data/período. Escolha outra data ou janela.')
                    else:
                        stage = 'Extrair regiões de recorrência'
                        raw = out['regions'].limit(101).getInfo()['features']
                        capped = len(raw) > 100
                        raw = raw[:100]
                        points = []
                        for number, feat in enumerate(raw, 1):
                            prop = feat['properties']
                            points.append({
                                'id': number,
                                'latitude': float(prop['latitude']),
                                'longitude': float(prop['longitude']),
                                'area_ha': round(float(prop['area_ha']), 3),
                                'recurrence_pct': round(float(prop['recurrence_pct']), 1) if prop.get('recurrence_pct') is not None else None,
                                'max_hit_years': int(prop['max_hit_years']) if prop.get('max_hit_years') is not None else 0,
                            })
                        stage = 'Criar camada histórica do mapa'
                        history = tile_url(out['recurrence'], RECURRENCE_VIS)
                        stage = 'Criar camada atual do mapa'
                        current = tile_url(out['current_display'], VIS[idx])
                        stage = 'Consultar série temporal do gráfico'
                        trend_raw = out['trend'].getInfo()['features']
                        trend = [feature['properties'] for feature in trend_raw]
                        st.session_state.result = {
                            'current': current,
                            'history': history,
                            'regions': {'type': 'FeatureCollection', 'features': raw},
                            'scenes': scenes,
                            'capped': capped,
                            'index': idx,
                            'scale': out['scale'],
                        }
                        st.session_state.points = points
                        st.session_state.trend = trend
                        st.session_state.analysis_signature = signature
                        st.session_state.ee_yearly = out['yearly']
                        st.session_state.region_details = {}
                        st.success(
                            f'Análise concluída: {scenes} cenas elegíveis; {len(points)} regiões exibidas; escala efetiva {out["scale"]} m.'
                            + (' Existem mais de 100 regiões; refine os filtros.' if capped else '')
                        )
                except Exception as exc:
                    clear_main_results()
                    logging.exception('LandVision processing failed; stage=%s', stage)
                    st.error('Falha na etapa: ' + stage + ' (' + type(exc).__name__ + '). Consulte o final dos registros privados; não compartilhe chaves.')


# -----------------------------------------------------------------------------
# OPTIONAL MULTI-INDEX CONCORDANCE
# -----------------------------------------------------------------------------
if run_concord:
    if not st.session_state.geometry:
        st.warning('Desenhe ou importe um talhão antes da concordância.')
    elif len(concord_indices) < 2:
        st.warning('Selecione pelo menos dois índices.')
    else:
        ok, err = connect()
        if not ok:
            st.error('Earth Engine não conectado. ' + err)
        else:
            with st.spinner('Comparando os índices no mesmo local e montando a recorrência histórica...'):
                try:
                    stage = 'Medir a área do talhão · concordância'
                    hectares = field_hectares(st.session_state.geometry)
                    if hectares > MAX_FIELD_HA:
                        st.warning(f'Área de {hectares:,.1f} ha excede o limite de {MAX_FIELD_HA:,} ha. Divida o talhão antes da concordância.')
                        st.stop()
                    stage = 'Preparar concordância multíndice'
                    out = concordance_analyze(
                        st.session_state.geometry,
                        year, m1, m2, mode, chosen,
                        concord_indices,
                        concord_min_indices,
                        concord_min_years,
                        concord_min_valid,
                        concord_min_ha,
                        concord_directions,
                        concord_threshold,
                    )
                    stage = 'Consultar cenas e pixels válidos · concordância'
                    from ee import Dictionary
                    scalars = Dictionary({'scenes': out['current_scenes'], 'valid': out['current_valid']}).getInfo()
                    scenes, valid = scalars['scenes'], scalars['valid']
                    if not scenes or valid is None or not valid:
                        clear_concordance()
                        st.warning('Sem pixels comuns válidos entre os índices escolhidos para esta data/período.')
                    else:
                        stage = 'Extrair regiões de concordância recorrente'
                        raw = out['regions'].limit(101).getInfo()['features']
                        capped = len(raw) > 100
                        raw = raw[:100]
                        points = []
                        for number, feat in enumerate(raw, 1):
                            prop = feat['properties']
                            points.append({
                                'id': number,
                                'latitude': float(prop['latitude']),
                                'longitude': float(prop['longitude']),
                                'area_ha': round(float(prop['area_ha']), 3),
                                'recurrence_pct': round(float(prop['recurrence_pct']), 1) if prop.get('recurrence_pct') is not None else None,
                                'max_concord_years': int(prop['max_concord_years']) if prop.get('max_concord_years') is not None else 0,
                                'max_indices_same_year': int(prop['max_indices_same_year']) if prop.get('max_indices_same_year') is not None else 0,
                            })
                        stage = 'Criar mapa atual de concordância'
                        current = tile_url(
                            out['current_count'],
                            {'min': 0, 'max': len(concord_indices), 'palette': CONCORD_PALETTE[:len(concord_indices) + 1]},
                        )
                        stage = 'Criar mapa histórico de concordância'
                        history = tile_url(out['recurrence'], RECURRENCE_VIS)
                        stage = 'Consultar série histórica da concordância'
                        trend_raw = out['trend'].getInfo()['features']
                        trend = [feature['properties'] for feature in trend_raw]
                        st.session_state.concord_result = {
                            'current': current,
                            'history': history,
                            'regions': {'type': 'FeatureCollection', 'features': raw},
                            'scenes': scenes,
                            'capped': capped,
                            'indices': list(concord_indices),
                            'scale': out['scale'],
                            'min_indices': concord_min_indices,
                        }
                        st.session_state.concord_points = points
                        st.session_state.concord_trend = trend
                        st.session_state.concord_signature = concord_signature
                        st.session_state.ee_concord_yearly = out['yearly']
                        st.session_state.concord_details = {}
                        st.success(
                            f'Concordância concluída: {len(concord_indices)} índices, escala comum {out["scale"]} m, {len(points)} regiões recorrentes exibidas.'
                            + (' Existem mais de 100 regiões; refine os filtros.' if capped else '')
                        )
                except Exception as exc:
                    clear_concordance()
                    logging.exception('LandVision concordance failed; stage=%s', stage)
                    st.error('Falha na concordância: ' + stage + ' (' + type(exc).__name__ + '). Consulte os registros privados; não compartilhe chaves.')


# -----------------------------------------------------------------------------
# MAIN MAPS
# -----------------------------------------------------------------------------
st.markdown('<div class="section-banner"><div class="section-kicker">VISUALIZAÇÃO PRINCIPAL</div><div class="section-title">Situação atual e recorrência histórica</div><div class="section-copy">Os dois mapas usam o mesmo índice selecionado. O mapa histórico destaca onde a anomalia reaparece espacialmente nos anos anteriores.</div></div>', unsafe_allow_html=True)
result = st.session_state.result
points = st.session_state.points
left, right = st.columns(2, gap='medium')
with left:
    st.markdown(f'#### MAPA 1 · {idx} atual')
    st.caption('Desenhe um polígono pelo ícone do mapa. Clique no primeiro vértice para concluir.')
    feedback = st_folium(
        make_map(st.session_state.geometry, base, overlay=result['current'] if result else None, draw=True),
        height=510,
        use_container_width=True,
        key='landvision_map_drawing',
        returned_objects=['all_drawings'],
    )
    drawings = (feedback or {}).get('all_drawings') or []
    if drawings:
        candidate = normalize(drawings[-1])
        if candidate and candidate != st.session_state.geometry:
            st.session_state.geometry = candidate
            st.session_state.center = center(candidate)
            st.session_state.zoom = 15
            clear_results()
            st.session_state.dates = []
            st.rerun()

with right:
    st.markdown(f'#### MAPA 2 · Recorrência histórica de {idx}')
    st.caption('Percentual dos anos históricos válidos em que o mesmo pixel apresentou anomalia no índice escolhido.')
    st_folium(
        make_map(st.session_state.geometry, base, overlay=result['history'] if result else None, points=points),
        height=510,
        use_container_width=True,
        key='landvision_map_history',
        returned_objects=[],
    )
    st.caption('LEGENDA · 0%: nenhum ano válido com anomalia | Verde: baixa recorrência | Amarelo: intermediária | Vermelho: alta | Transparente: dados insuficientes ou fora do talhão.')

if st.session_state.geometry:
    st.download_button(
        'Exportar talhão · GeoJSON',
        json.dumps(st.session_state.geometry, ensure_ascii=False, indent=2),
        'landvision_talhao.geojson',
        'application/geo+json',
    )


# -----------------------------------------------------------------------------
# MAIN RESULT TABLES
# -----------------------------------------------------------------------------
if result:
    st.markdown(f'### Série histórica · {idx}')
    st.caption('Por ano: percentual dos pixels válidos classificados com anomalia espacial e média do índice selecionado. Ano sem dado não vira zero.')
    if mode == 'DATA ÚNICA':
        st.caption('Comparação sazonal: anos anteriores usam janela de ±10 dias; o ano atual usa a cena da data exata.')
    trend = st.session_state.trend
    df = pd.DataFrame(trend).rename(columns={
        'year': 'Ano',
        'pct': 'Área com anomalia (%)',
        'mean_index': 'Média do score' if idx == MULTI else f'Média {idx}',
        'scenes': 'Cenas elegíveis',
    }).sort_values('Ano')
    if not df.empty:
        c1, c2 = st.columns(2)
        if df['Área com anomalia (%)'].notna().any():
            with c1:
                st.markdown('**Extensão anual da anomalia**')
                st.bar_chart(df.set_index('Ano')['Área com anomalia (%)'], y_label='% dos pixels válidos', x_label='Ano')
        mean_col = 'Média do score' if idx == MULTI else f'Média {idx}'
        if df[mean_col].notna().any():
            with c2:
                st.markdown('**Média anual do índice**' if idx != MULTI else '**Média anual do score espacial**')
                st.line_chart(df.set_index('Ano')[mean_col], x_label='Ano')
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.warning('Dados insuficientes para representar a série histórica.')

    st.caption('Diferenças de cultura, semeadura, estádio fenológico, solo e cobertura válida podem alterar a comparação. O resultado mede variação relativa dentro do talhão.')
    st.markdown(f'### Pontos de investigação · {idx}')
    if points:
        point_df = pd.DataFrame(points).rename(columns={
            'id': 'Ponto',
            'latitude': 'Latitude',
            'longitude': 'Longitude',
            'area_ha': 'Área (ha)',
            'recurrence_pct': 'Recorrência média (%)',
            'max_hit_years': 'Máximo de anos com anomalia',
        })
        st.dataframe(point_df, use_container_width=True, hide_index=True)
        out_csv = io.StringIO()
        writer = csv.DictWriter(out_csv, fieldnames=points[0].keys())
        writer.writeheader()
        writer.writerows(points)
        d1, d2, d3 = st.columns(3)
        slug = idx.lower()
        d1.download_button('Coordenadas CSV', out_csv.getvalue().encode('utf-8-sig'), f'landvision_{slug}_pontos.csv', 'text/csv', use_container_width=True)
        d2.download_button('Regiões GeoJSON', json.dumps(result['regions'], ensure_ascii=False), f'landvision_{slug}_regioes.geojson', 'application/geo+json', use_container_width=True)
        d3.download_button('Pontos KML', kml_points(points), f'landvision_{slug}_pontos.kml', 'application/vnd.google-earth.kml+xml', use_container_width=True)
        if result['capped']:
            st.warning('Exibição/exportação limitada a 100 regiões; refine os limiares antes de exportar resultados completos.')

        st.markdown('#### Evolução histórica de uma região identificada')
        selected_point = st.selectbox(
            'Região para investigar',
            range(1, len(points) + 1),
            format_func=lambda number: f'Ponto {number} — {points[number-1]["area_ha"]:.2f} ha',
            key='single_region_selector',
        )
        if st.button('Consultar histórico desta região', use_container_width=True):
            if not st.session_state.ee_yearly:
                st.warning('Execute novamente a análise antes de consultar uma região.')
            else:
                ok, err = connect()
                if not ok:
                    st.error('Earth Engine não conectado. ' + err)
                else:
                    with st.spinner('Consultando somente a região escolhida...'):
                        try:
                            feature = result['regions']['features'][selected_point - 1]
                            detail = region_series(st.session_state.ee_yearly, feature['geometry'])
                            rows = [feature['properties'] for feature in detail.getInfo()['features']]
                            st.session_state.region_details[selected_point] = rows
                        except Exception as exc:
                            logging.exception('LandVision point detail query failed')
                            st.error('Falha ao consultar esta região (' + type(exc).__name__ + '). Consulte os registros privados.')
        if selected_point in st.session_state.region_details:
            detail_df = pd.DataFrame(st.session_state.region_details[selected_point]).rename(columns={
                'year': 'Ano',
                'mean_index': 'Média do score' if idx == MULTI else f'Média {idx}',
                'anomaly_pct': 'Pixels anômalos na região (%)',
            }).sort_values('Ano')
            st.caption('Percentual dos pixels válidos desta região com anomalia em cada ano; valor ausente não significa 0%.')
            st.dataframe(detail_df, hide_index=True, use_container_width=True)
            st.download_button('Baixar histórico da região · CSV', detail_df.to_csv(index=False).encode('utf-8-sig'), f'landvision_{slug}_ponto_{selected_point}_historico.csv', 'text/csv')
    else:
        st.info('Nenhuma região atendeu aos filtros escolhidos. Isso não demonstra ausência de problemas em campo.')

    scale_used = result.get('scale', main_scale)
    st.caption(f'As coordenadas são centroides aproximados de regiões raster analisadas em {scale_used} m; não equivalem a levantamento topográfico. Índices que usam banda de 20 m não ganham informação real ao serem visualizados em grade mais fina.')
else:
    st.info('Importe/desenhe o talhão e execute a análise. O mapa-base não é um resultado de índice ou estresse.')


# -----------------------------------------------------------------------------
# CONCORDANCE RESULTS — OPTIONAL MODULE
# -----------------------------------------------------------------------------
concord = st.session_state.concord_result
if concord:
    st.markdown('<div class="section-banner"><div class="section-kicker">INTELIGÊNCIA ESPACIAL</div><div class="section-title">Concordância Multíndice · mesmo local</div><div class="section-copy">Cruza índices diferentes na mesma posição e verifica se o padrão reaparece historicamente. A análise só é executada quando solicitada.</div></div>', unsafe_allow_html=True)

    cm = st.columns(4)
    cm[0].metric('Índices', len(concord['indices']))
    cm[1].metric('Concordância mínima', f"{concord['min_indices']}/{len(concord['indices'])}")
    cm[2].metric('Grade comum', f"{concord['scale']} m")
    cm[3].metric('Índices usados', ' · '.join(concord['indices']))

    c_left, c_right = st.columns(2, gap='medium')
    with c_left:
        st.markdown('#### MAPA C1 · Concordância atual')
        st.caption('Número de índices anômalos no mesmo pixel no período atual.')
        st_folium(
            make_map(st.session_state.geometry, base, overlay=concord['current']),
            height=500,
            use_container_width=True,
            key='landvision_concord_current',
            returned_objects=[],
        )
        st.caption('LEGENDA · Verde: nenhum/poucos índices concordando · Amarelo/laranja: concordância intermediária · Vermelho: maior número de índices anômalos no mesmo local.')

    with c_right:
        st.markdown('#### MAPA C2 · Recorrência histórica da concordância')
        st.caption(f"Percentual dos 5 anos anteriores em que pelo menos {concord['min_indices']} índices foram anômalos no mesmo pixel.")
        st_folium(
            make_map(st.session_state.geometry, base, overlay=concord['history'], points=st.session_state.concord_points),
            height=500,
            use_container_width=True,
            key='landvision_concord_history',
            returned_objects=[],
        )
        st.caption('LEGENDA · Verde: concordância rara · Amarelo: intermediária · Vermelho: concordância multíndice repetida. Marcadores: centroides das regiões que passaram pelos filtros.')

    st.markdown('### Série histórica da concordância')
    ctrend = pd.DataFrame(st.session_state.concord_trend).rename(columns={
        'year': 'Ano',
        'concordance_pct': 'Área com concordância (%)',
        'mean_index_count': 'Número médio de índices anômalos',
        'scenes': 'Cenas elegíveis',
    }).sort_values('Ano')
    if not ctrend.empty:
        g1, g2 = st.columns(2)
        if ctrend['Área com concordância (%)'].notna().any():
            with g1:
                st.markdown('**Extensão da concordância por ano**')
                st.bar_chart(ctrend.set_index('Ano')['Área com concordância (%)'], y_label='% dos pixels válidos', x_label='Ano')
        if ctrend['Número médio de índices anômalos'].notna().any():
            with g2:
                st.markdown('**Quantidade média de índices anômalos por pixel**')
                st.line_chart(ctrend.set_index('Ano')['Número médio de índices anômalos'], x_label='Ano')
        st.dataframe(ctrend, hide_index=True, use_container_width=True)

    cpoints = st.session_state.concord_points
    st.markdown('### Regiões prioritárias · concordância multíndice')
    if cpoints:
        highest_years = max(int(_safe_float(p.get('max_concord_years'), 0)) for p in cpoints)
        highest_indices = max(int(_safe_float(p.get('max_indices_same_year'), 0)) for p in cpoints)
        largest_area = max(_safe_float(p.get('area_ha'), 0) for p in cpoints)
        st.markdown(
            f'''<div class="summary-callout"><b>Resumo geral da concordância</b><br>
            Foram identificadas <b>{len(cpoints)} regiões prioritárias</b>. A maior recorrência observada foi de <b>{highest_years}/5 anos</b>,
            com até <b>{highest_indices} índices anômalos no mesmo ano</b>. A maior região delimitada possui <b>{largest_area:.2f} ha</b>.
            <br><small>Selecione uma região abaixo para gerar o resumo automático detalhado índice × ano.</small></div>''',
            unsafe_allow_html=True,
        )
        cpoint_df = pd.DataFrame(cpoints).rename(columns={
            'id': 'Ponto',
            'latitude': 'Latitude',
            'longitude': 'Longitude',
            'area_ha': 'Área (ha)',
            'recurrence_pct': 'Recorrência média da concordância (%)',
            'max_concord_years': 'Máximo de anos concordantes',
            'max_indices_same_year': 'Máximo de índices no mesmo ano',
        })
        st.dataframe(cpoint_df, hide_index=True, use_container_width=True)

        out_csv = io.StringIO()
        writer = csv.DictWriter(out_csv, fieldnames=cpoints[0].keys())
        writer.writeheader()
        writer.writerows(cpoints)
        e1, e2, e3 = st.columns(3)
        e1.download_button('Concordância · CSV', out_csv.getvalue().encode('utf-8-sig'), 'landvision_concordancia_pontos.csv', 'text/csv', use_container_width=True)
        e2.download_button('Concordância · GeoJSON', json.dumps(concord['regions'], ensure_ascii=False), 'landvision_concordancia_regioes.geojson', 'application/geo+json', use_container_width=True)
        e3.download_button('Concordância · KML', kml_points(cpoints), 'landvision_concordancia_pontos.kml', 'application/vnd.google-earth.kml+xml', use_container_width=True)

        st.markdown('#### Resumo automático e matriz índice × ano')
        c_selected = st.selectbox(
            'Região multíndice para investigar',
            range(1, len(cpoints) + 1),
            format_func=lambda number: f'Ponto {number} — {cpoints[number-1]["area_ha"]:.2f} ha',
            key='concord_region_selector',
        )
        st.caption('Escolha uma região e clique abaixo. O resumo automático aparecerá imediatamente antes da matriz histórica.')
        if st.button('Gerar resumo automático desta região', type='primary', use_container_width=True):
            if not st.session_state.ee_concord_yearly:
                st.warning('Execute novamente a concordância antes de consultar uma região.')
            else:
                ok, err = connect()
                if not ok:
                    st.error('Earth Engine não conectado. ' + err)
                else:
                    with st.spinner('Consultando índice por índice e ano por ano somente nesta região...'):
                        try:
                            feature = concord['regions']['features'][c_selected - 1]
                            detail = concordance_region_series(
                                st.session_state.ee_concord_yearly,
                                feature['geometry'],
                                concord['indices'],
                            )
                            rows = [feature['properties'] for feature in detail.getInfo()['features']]
                            st.session_state.concord_details[c_selected] = rows
                        except Exception as exc:
                            logging.exception('LandVision concordance region detail failed')
                            st.error('Falha ao consultar a matriz (' + type(exc).__name__ + '). Consulte os registros privados.')

        if c_selected in st.session_state.concord_details:
            rows = st.session_state.concord_details[c_selected]
            detail_df = pd.DataFrame(rows).sort_values('year')

            summary = _concordance_region_summary(
                cpoints[c_selected - 1],
                detail_df,
                concord['indices'],
                concord['min_indices'],
                concord['scale'],
            )
            if summary:
                st.markdown('#### Resumo automático da região · leitura rápida')
                r1, r2, r3, r4 = st.columns(4)
                r1.metric('Prioridade exploratória', summary['priority'])
                r2.metric('Área da região', f"{summary['area']:.2f} ha")
                r3.metric('Máx. concordância', f"{summary['max_years']}/5 anos")
                r4.metric('Resolução efetiva', f"{summary['scale']} m")

                recurrence_by_index = ' · '.join(
                    f"{name}: {summary['center_counts'][name]}/{summary['valid_counts'][name]}"
                    for name in concord['indices']
                )
                current_text = (
                    ', '.join(summary['current_anomalous'])
                    if summary['current_anomalous'] else 'nenhum dos índices selecionados no centroide aproximado'
                )
                recurrent_text = (
                    ', '.join(summary['recurrent_names'])
                    if summary['recurrent_names'] else 'nenhum índice atingiu 3 ocorrências no centroide aproximado'
                )
                st.markdown(
                    f"""<div class="region-summary">
                    <h4>Região {c_selected} · {summary['priority']}</h4>
                    <p><b>Recorrência espacial da região:</b> média de {summary['recurrence']:.1f}% nos pixels da região; algum pixel atingiu concordância em até {summary['max_years']} dos 5 anos históricos.</p>
                    <p><b>Mesmo ponto aproximado (centroide):</b> concordância de pelo menos {concord['min_indices']} índices em {summary['center_concord_years']}/{summary['common_valid']} anos com dados comuns.</p>
                    <p><b>Recorrência por índice no centroide:</b> {recurrence_by_index}.</p>
                    <p><b>Índices mais recorrentes nesse ponto:</b> {recurrent_text}.</p>
                    <p><b>Período de referência ({summary['reference_year']}):</b> anomalia em {current_text}.</p>
                    <p><b>Interpretação:</b> {summary['interpretation']}</p>
                    </div>""",
                    unsafe_allow_html=True,
                )
                st.caption('Resumo automático baseado somente nos resultados espectrais do LandVision. Prioridade exploratória não é diagnóstico agronômico e deve ser validada no campo.')

            matrix = pd.DataFrame({'Ano': detail_df['year']})
            for name in concord['indices']:
                center_col = name + '_center'

                def label(value):
                    if pd.isna(value):
                        return 'Sem dado'
                    return 'Anomalia' if float(value) >= .5 else 'Normal'

                matrix[name] = detail_df[center_col].apply(label)
            st.markdown('**Mesmo ponto aproximado (centroide) ao longo dos anos**')
            st.caption('A matriz abaixo responde diretamente se cada índice estava anômalo ou normal na mesma coordenada aproximada da região em cada ano.')
            st.dataframe(matrix, hide_index=True, use_container_width=True)

            area_table = pd.DataFrame({'Ano': detail_df['year']})
            for name in concord['indices']:
                area_table[f'{name} · área anômala (%)'] = detail_df[name + '_pct']
            area_table['Área com concordância (%)'] = detail_df['concordance_pct']
            area_table['Nº médio de índices anômalos'] = detail_df['mean_index_count']
            st.markdown('**Quanto da região apresentou cada anomalia**')
            st.dataframe(area_table, hide_index=True, use_container_width=True)
            st.download_button(
                'Baixar matriz e percentuais · CSV',
                area_table.to_csv(index=False).encode('utf-8-sig'),
                f'landvision_concordancia_ponto_{c_selected}.csv',
                'text/csv',
            )
    else:
        st.info('Nenhuma região apresentou concordância recorrente suficiente com os filtros escolhidos. Isso não significa ausência de anomalias individuais.')

    st.caption(f'A concordância foi comparada em grade comum de {concord["scale"]} m. Se qualquer índice selecionado depender de banda Sentinel-2 de 20 m, a comparação multíndice usa 20 m para não criar falsa precisão espacial.')


st.divider()
st.caption(
    'LandVision V0.7 Professional · Núcleo analítico V0.6.1 preservado · Dados: Sentinel-2 SR Harmonized / Google Earth Engine. '
    'Anomalia espectral e concordância são indicadores exploratórios, não diagnósticos de nematoides, doença, compactação, deficiência ou estresse hídrico. '
    'Considere cultura, rotação, data de plantio, estádio fenológico, solo e cobertura de nuvens.'
)

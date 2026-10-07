"""LandVision report/export utilities.

Builds in-memory ZIP exports with a PDF report plus the essential analysis files.
No credentials are written to the package.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = '#0C243A'
GREEN = '#95A237'
DARK = '#2C3D20'
GREY = '#6F7E89'
LIGHT = '#F3F5F2'


def slugify(value: str) -> str:
    value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^A-Za-z0-9_-]+', '_', value).strip('_').lower()
    return value or 'talhao'


def csv_bytes(rows) -> bytes:
    if isinstance(rows, pd.DataFrame):
        return rows.to_csv(index=False).encode('utf-8-sig')
    rows = list(rows or [])
    if not rows:
        return b''
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode('utf-8-sig')


def kml_points(points, title='LandVision') -> bytes:
    def esc(text):
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    chunks = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
        f'<name>{esc(title)}</name>',
    ]
    for point in points or []:
        years = point.get('max_hit_years', point.get('max_concord_years', 0))
        desc = (
            f"Área: {point.get('area_ha', '')} ha | "
            f"Recorrência: {point.get('recurrence_pct', '')}% | "
            f"Máximo de anos: {years}"
        )
        chunks.append(
            '<Placemark>'
            f"<name>Ponto {point.get('id', '')}</name>"
            f'<description>{esc(desc)}</description>'
            f"<Point><coordinates>{point.get('longitude')},{point.get('latitude')},0</coordinates></Point>"
            '</Placemark>'
        )
    chunks.append('</Document></kml>')
    return ''.join(chunks).encode('utf-8')


def chart_png(trend, title, value_key, ylabel, chart_type='bar') -> bytes | None:
    if not trend:
        return None
    frame = pd.DataFrame(trend)
    if 'year' not in frame or value_key not in frame:
        return None
    frame = frame[['year', value_key]].dropna().sort_values('year')
    if frame.empty:
        return None

    fig, ax = plt.subplots(figsize=(9.6, 4.8), dpi=150)
    if chart_type == 'line':
        ax.plot(frame['year'], frame[value_key], marker='o', linewidth=2)
    else:
        ax.bar(frame['year'].astype(str), frame[value_key])
    ax.set_title(title, loc='left', fontsize=14, fontweight='bold')
    ax.set_xlabel('Ano')
    ax.set_ylabel(ylabel)
    ax.grid(axis='y', alpha=.20)
    fig.tight_layout()
    out = io.BytesIO()
    fig.savefig(out, format='png', bbox_inches='tight')
    plt.close(fig)
    return out.getvalue()


def earth_engine_thumb(image, vis, feature, dimensions=850) -> bytes:
    """Download a clean PNG of one analytical Earth Engine layer.

    The image contains the analysis raster and a white field boundary, without a
    third-party basemap. This keeps report generation reproducible and free.
    """
    import ee

    geom = ee.Geometry(feature['geometry'])
    rendered = image.visualize(**vis)
    outline = ee.Image().byte().paint(geom, 1, 2).selfMask().visualize(palette=['FFFFFF'])
    rendered = rendered.blend(outline)
    region = feature['geometry']['coordinates']
    url = rendered.getThumbURL({
        'region': region,
        'dimensions': dimensions,
        'format': 'png',
    })
    req = urllib.request.Request(url, headers={'User-Agent': 'LandVision/0.8.1'})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()


def _geometry_bounds(feature: dict):
    """Return min_lon, min_lat, max_lon, max_lat for Polygon/MultiPolygon GeoJSON."""
    geometry = (feature or {}).get('geometry', feature or {})
    coords = geometry.get('coordinates') or []
    pairs = []

    def walk(value):
        if not isinstance(value, (list, tuple)):
            return
        if len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            pairs.append((float(value[0]), float(value[1])))
            return
        for item in value:
            walk(item)

    walk(coords)
    if not pairs:
        return None
    lons = [p[0] for p in pairs]
    lats = [p[1] for p in pairs]
    return min(lons), min(lats), max(lons), max(lats)


def annotate_investigation_points(
    png_bytes: bytes,
    points: list,
    feature: dict,
    max_points: int = 25,
) -> bytes:
    """Draw P1, P2... over the exported analytical PNG.

    The report thumbnails use the bounding box of the field geometry. For a
    normal agricultural field this linear lon/lat-to-pixel conversion is a very
    good approximation and keeps the exported point labels aligned with the
    investigation centroids shown in the app.
    """
    if not png_bytes or not points:
        return png_bytes

    bounds = _geometry_bounds(feature)
    if not bounds:
        return png_bytes
    min_lon, min_lat, max_lon, max_lat = bounds
    if max_lon <= min_lon or max_lat <= min_lat:
        return png_bytes

    try:
        image_array = plt.imread(io.BytesIO(png_bytes), format='png')
    except Exception:
        return png_bytes

    height_px, width_px = image_array.shape[:2]
    dpi = 150
    fig = plt.figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(image_array)

    label_font = max(7.0, min(10.0, width_px / 95.0))
    marker_size = max(70, min(145, width_px * 0.12))

    for point in list(points)[:max_points]:
        try:
            lon = float(point.get('longitude'))
            lat = float(point.get('latitude'))
        except (TypeError, ValueError):
            continue
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            continue

        x = (lon - min_lon) / (max_lon - min_lon) * (width_px - 1)
        y = (max_lat - lat) / (max_lat - min_lat) * (height_px - 1)
        point_id = point.get('id', '')

        # Strong marker that remains visible over green, yellow, orange and red rasters.
        ax.scatter(
            [x], [y],
            s=marker_size,
            facecolors=NAVY,
            edgecolors='white',
            linewidths=1.8,
            zorder=5,
        )
        ax.annotate(
            f'P{point_id}',
            xy=(x, y),
            xytext=(0, -15),
            textcoords='offset points',
            ha='center',
            va='top',
            fontsize=label_font,
            fontweight='bold',
            color='white',
            bbox={
                'boxstyle': 'round,pad=0.25',
                'facecolor': NAVY,
                'edgecolor': 'white',
                'linewidth': 1.1,
            },
            zorder=6,
        )

    ax.set_xlim(-0.5, width_px - 0.5)
    ax.set_ylim(height_px - 0.5, -0.5)
    ax.axis('off')

    output = io.BytesIO()
    fig.savefig(output, format='png', dpi=dpi, facecolor='white', pad_inches=0)
    plt.close(fig)
    return output.getvalue()


def _rl_image(data: bytes, max_width=180*mm, max_height=108*mm):
    bio = io.BytesIO(data)
    width_px, height_px = ImageReader(bio).getSize()
    ratio = min(max_width / width_px, max_height / height_px)
    bio.seek(0)
    return Image(bio, width=width_px * ratio, height=height_px * ratio)


def _points_table(points, styles, title='Pontos de investigação'):
    if not points:
        return [Paragraph(title, styles['H2']), Paragraph('Nenhuma região atendeu aos filtros selecionados.', styles['Body'])]
    header = ['Ponto', 'Área (ha)', 'Recorrência (%)', 'Anos', 'Latitude', 'Longitude']
    rows = [header]
    for point in points[:25]:
        years = point.get('max_hit_years', point.get('max_concord_years', 0))
        rows.append([
            str(point.get('id', '')),
            f"{float(point.get('area_ha') or 0):.2f}",
            '' if point.get('recurrence_pct') is None else f"{float(point['recurrence_pct']):.1f}",
            str(years),
            f"{float(point.get('latitude') or 0):.6f}",
            f"{float(point.get('longitude') or 0):.6f}",
        ])
    table = Table(rows, repeatRows=1, colWidths=[16*mm, 24*mm, 30*mm, 16*mm, 39*mm, 39*mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (3, -1), 'CENTER'),
        ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F6F8F5')]),
        ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#D9DEDA')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return [Paragraph(title, styles['H2']), table]


def create_pdf_report(
    *,
    logo_path: Path,
    field_name: str,
    parameters: dict,
    main_points: list,
    main_trend: list,
    concord_points: list,
    concord_trend: list,
    images: dict[str, bytes],
) -> bytes:
    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=16*mm,
        title=f'LandVision - {field_name}',
        author='LandVision',
    )
    sample = getSampleStyleSheet()
    styles = {
        'Title': ParagraphStyle('LVTitle', parent=sample['Title'], fontName='Helvetica-Bold', fontSize=22, leading=25, textColor=colors.HexColor(NAVY), alignment=TA_LEFT, spaceAfter=2),
        'Subtitle': ParagraphStyle('LVSubtitle', parent=sample['Normal'], fontSize=9, leading=13, textColor=colors.HexColor(GREY), spaceAfter=8),
        'H2': ParagraphStyle('LVH2', parent=sample['Heading2'], fontName='Helvetica-Bold', fontSize=13, leading=16, textColor=colors.HexColor(NAVY), spaceBefore=9, spaceAfter=7),
        'Body': ParagraphStyle('LVBody', parent=sample['BodyText'], fontSize=9, leading=13, textColor=colors.HexColor('#344957'), spaceAfter=6),
        'Small': ParagraphStyle('LVSmall', parent=sample['BodyText'], fontSize=7.8, leading=10.5, textColor=colors.HexColor(GREY), spaceAfter=5),
        'Callout': ParagraphStyle('LVCallout', parent=sample['BodyText'], fontSize=9.2, leading=13, textColor=colors.HexColor(NAVY), backColor=colors.HexColor('#F2F5E8'), borderColor=colors.HexColor(GREEN), borderWidth=.7, borderPadding=8, spaceBefore=5, spaceAfter=10),
    }

    story = []
    logo = Image(str(logo_path), width=23*mm, height=23*mm)
    heading = [
        Paragraph('LANDVISION', styles['Title']),
        Paragraph('Satellite Field Intelligence · Relatório técnico de análise espectral', styles['Subtitle']),
    ]
    head_table = Table([[logo, heading]], colWidths=[29*mm, 145*mm])
    head_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LINEBELOW', (0, 0), (-1, -1), 1.2, colors.HexColor(GREEN)), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    story += [head_table, Spacer(1, 7)]

    period = parameters.get('period_label', '')
    meta = [
        ['Talhão', field_name, 'Fonte', 'Sentinel-2 SR Harmonized'],
        ['Período', period, 'Earth Engine', 'Google Earth Engine'],
        ['Índice principal', parameters.get('index', ''), 'Resolução efetiva', f"{parameters.get('scale', '')} m"],
        ['Gerado em', datetime.now().strftime('%Y-%m-%d %H:%M'), 'Histórico', '5 anos anteriores'],
    ]
    meta_table = Table(meta, colWidths=[28*mm, 59*mm, 30*mm, 57*mm])
    meta_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#344957')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F7F8F6')),
        ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#D7DDD8')),
        ('FONTSIZE', (0, 0), (-1, -1), 8.2), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story += [meta_table, Spacer(1, 7)]

    summary = (
        f"A análise principal identificou <b>{len(main_points)} região(ões)</b> que atenderam aos filtros de recorrência. "
        f"A concordância multíndice identificou <b>{len(concord_points)} região(ões)</b> prioritárias. "
        "Os resultados indicam zonas para investigação em campo e não constituem diagnóstico agronômico isolado."
    )
    story += [Paragraph('Resumo executivo', styles['H2']), Paragraph(summary, styles['Callout'])]

    if images.get('main_current'):
        story += [Paragraph('Mapa atual - índice selecionado', styles['H2']), _rl_image(images['main_current']), Paragraph('Camada analítica do Earth Engine com limite do talhão. Os marcadores P1, P2, P3... correspondem aos pontos de investigação listados na tabela do relatório.', styles['Small'])]
    if images.get('main_history'):
        story += [Paragraph('Recorrência histórica - mesmo índice', styles['H2']), _rl_image(images['main_history']), Paragraph('A recorrência representa a frequência espacial da anomalia nos cinco anos anteriores. Os marcadores P1, P2, P3... mostram onde investigar em campo.', styles['Small'])]
    if images.get('main_chart'):
        story += [Paragraph('Série histórica', styles['H2']), _rl_image(images['main_chart'], max_height=85*mm)]

    story += _points_table(main_points, styles, 'Pontos de investigação - análise principal')

    if concord_trend or concord_points:
        story += [PageBreak(), Paragraph('Concordância Multíndice', styles['H2'])]
        indices = ', '.join(parameters.get('concordance', {}).get('indices', []))
        min_indices = parameters.get('concordance', {}).get('min_indices', '')
        story += [Paragraph(f"Índices comparados: <b>{indices or 'não informado'}</b>. Critério de concordância: pelo menos <b>{min_indices}</b> índices anômalos no mesmo local e ano.", styles['Body'])]
        if images.get('concord_current'):
            story += [Paragraph('Concordância no período de referência', styles['H2']), _rl_image(images['concord_current'])]
        if images.get('concord_history'):
            story += [Paragraph('Recorrência histórica da concordância', styles['H2']), _rl_image(images['concord_history'])]
        if images.get('concord_chart'):
            story += [Paragraph('Série histórica da concordância', styles['H2']), _rl_image(images['concord_chart'], max_height=85*mm)]
        story += _points_table(concord_points, styles, 'Regiões prioritárias - concordância multíndice')

    story += [Spacer(1, 8), Paragraph('Notas técnicas', styles['H2'])]
    story += [Paragraph(
        'As coordenadas representam centroides aproximados de regiões raster. A resolução efetiva depende das bandas Sentinel-2 usadas por cada índice. '
        'Índices que dependem de bandas de 20 m não adquirem informação espacial real de 10 m por reamostragem. Diferenças de cultura, semeadura, estádio fenológico, solo, manejo e cobertura de nuvens devem ser consideradas na interpretação.',
        styles['Body'],
    )]
    story += [Paragraph('LandVision · Resultado exploratório para apoio à investigação de campo.', styles['Small'])]

    doc.build(story)
    return out.getvalue()



def build_quick_bundle(
    *,
    logo_path: Path,
    field_name: str,
    geometry: dict,
    parameters: dict,
    main_points: list,
    main_trend: list,
    concord_points: list,
    concord_trend: list,
    map_specs: list | None = None,
    progress_cb=None,
) -> tuple[bytes, list[str]]:
    """Build the fast LandVision archive.

    Designed for routine field work. It intentionally avoids GeoJSON region
    exports and per-region detail files. Only the two principal Earth Engine
    map thumbnails are requested; the remaining charts are generated locally
    from scalar results already returned by the app.
    """
    warnings: list[str] = []
    files: dict[str, bytes] = {}
    images: dict[str, bytes] = {}
    safe = slugify(field_name)

    def progress(value: int, message: str):
        if progress_cb:
            try:
                progress_cb(value, message)
            except Exception:
                pass

    progress(8, 'Preparando CSV, KML e parâmetros...')
    files['dados/parametros_analise.json'] = json.dumps(
        parameters, ensure_ascii=False, indent=2, default=str
    ).encode('utf-8')

    if main_trend:
        files['dados/serie_historica.csv'] = csv_bytes(pd.DataFrame(main_trend))
    if main_points:
        files['dados/pontos_investigacao.csv'] = csv_bytes(main_points)
        files['dados/pontos_investigacao.kml'] = kml_points(
            main_points, 'LandVision - Pontos de investigação'
        )

    if concord_trend:
        files['dados/concordancia_serie_historica.csv'] = csv_bytes(
            pd.DataFrame(concord_trend)
        )
    if concord_points:
        files['dados/concordancia_pontos.csv'] = csv_bytes(concord_points)
        files['dados/concordancia_pontos.kml'] = kml_points(
            concord_points, 'LandVision - Concordância multíndice'
        )

    progress(18, 'Gerando gráficos locais...')
    main_chart = chart_png(
        main_trend, 'Área com anomalia por ano', 'pct', '% dos pixels válidos'
    )
    if main_chart:
        images['main_chart'] = main_chart
        files['imagens/serie_historica.png'] = main_chart

    concord_chart = chart_png(
        concord_trend,
        'Área com concordância multíndice por ano',
        'concordance_pct',
        '% dos pixels válidos',
    )
    if concord_chart:
        images['concord_chart'] = concord_chart
        files['imagens/concordancia_serie_historica.png'] = concord_chart

    specs = list(map_specs or [])[:2]
    if specs:
        # Two analytical thumbnails are the only network-heavy part of quick export.
        span = 52
        for i, spec in enumerate(specs):
            start = 24 + int(span * i / max(1, len(specs)))
            end = 24 + int(span * (i + 1) / max(1, len(specs)))
            progress(start, f"Gerando {spec.get('label', 'mapa')}...")
            try:
                png = earth_engine_thumb(
                    spec['image'], spec['vis'], geometry, dimensions=850
                )
                point_source = (
                    concord_points
                    if str(spec.get('name', '')).startswith('concord')
                    else main_points
                )
                png = annotate_investigation_points(
                    png, point_source, geometry, max_points=25
                )
                images[spec['name']] = png
                files[f"imagens/{spec['filename']}"] = png
            except Exception as exc:
                warnings.append(
                    f"Não foi possível gerar {spec.get('filename', spec.get('name'))}: {type(exc).__name__}"
                )
            progress(end, f"{spec.get('label', 'Mapa')} concluído.")

    progress(80, 'Montando relatório PDF...')
    pdf = create_pdf_report(
        logo_path=logo_path,
        field_name=field_name,
        parameters=parameters,
        main_points=main_points,
        main_trend=main_trend,
        concord_points=concord_points,
        concord_trend=concord_trend,
        images=images,
    )
    files[f'relatorio/Relatorio_LandVision_{safe}.pdf'] = pdf

    readme = f"""LANDVISION - EXPORTAÇÃO RÁPIDA\n\nTalhão: {field_name}\nGerado em: {datetime.now().isoformat(timespec='minutes')}\n\nCONTEÚDO\n- relatorio/: PDF técnico\n- imagens/: mapas principais e gráficos em PNG\n- dados/: CSV, KML e parâmetros usados\n\nMODO RÁPIDO\nEsta exportação prioriza velocidade. GeoJSON, matrizes individuais e mapas adicionais de concordância não são gerados.\n\nIMPORTANTE\nOs resultados espectrais são indicadores exploratórios e devem ser validados em campo.\nNenhuma credencial, chave ou conteúdo do Streamlit Secrets é incluído neste pacote.\n"""
    files['LEIA-ME.txt'] = readme.encode('utf-8')

    progress(92, 'Compactando arquivos...')
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, data in files.items():
            zf.writestr(filename, data)
    progress(100, 'Exportação pronta.')
    return out.getvalue(), warnings

def build_analysis_bundle(
    *,
    logo_path: Path,
    field_name: str,
    geometry: dict,
    parameters: dict,
    main_result: dict | None,
    main_points: list,
    main_trend: list,
    concord_result: dict | None,
    concord_points: list,
    concord_trend: list,
    region_details: dict | None = None,
    concord_details: dict | None = None,
    map_specs: list | None = None,
) -> tuple[bytes, list[str]]:
    """Return ZIP bytes and non-fatal warnings.

    `map_specs` items: {name, image, vis}. Earth Engine thumbnails are downloaded
    only when the user explicitly asks to prepare the bundle.
    """
    warnings = []
    files: dict[str, bytes] = {}
    images: dict[str, bytes] = {}
    safe = slugify(field_name)

    files['dados/talhao.geojson'] = json.dumps(geometry, ensure_ascii=False, indent=2).encode('utf-8')
    files['dados/parametros_analise.json'] = json.dumps(parameters, ensure_ascii=False, indent=2, default=str).encode('utf-8')

    if main_trend:
        files['dados/serie_historica.csv'] = csv_bytes(pd.DataFrame(main_trend))
    if main_points:
        files['dados/pontos_investigacao.csv'] = csv_bytes(main_points)
        files['dados/pontos_investigacao.kml'] = kml_points(main_points, 'LandVision - Pontos de investigação')
    if main_result and main_result.get('regions'):
        files['dados/regioes_investigacao.geojson'] = json.dumps(main_result['regions'], ensure_ascii=False).encode('utf-8')

    if concord_trend:
        files['dados/concordancia_serie_historica.csv'] = csv_bytes(pd.DataFrame(concord_trend))
    if concord_points:
        files['dados/concordancia_pontos.csv'] = csv_bytes(concord_points)
        files['dados/concordancia_pontos.kml'] = kml_points(concord_points, 'LandVision - Concordância multíndice')
    if concord_result and concord_result.get('regions'):
        files['dados/concordancia_regioes.geojson'] = json.dumps(concord_result['regions'], ensure_ascii=False).encode('utf-8')

    for number, rows in sorted((region_details or {}).items()):
        files[f'dados/regioes/ponto_{number}_historico.csv'] = csv_bytes(pd.DataFrame(rows))
    for number, rows in sorted((concord_details or {}).items()):
        files[f'dados/concordancia/ponto_{number}_matriz.csv'] = csv_bytes(pd.DataFrame(rows))

    # Historical figures from already-returned scalar data.
    main_chart = chart_png(main_trend, 'Área com anomalia por ano', 'pct', '% dos pixels válidos')
    if main_chart:
        images['main_chart'] = main_chart
        files['imagens/serie_historica.png'] = main_chart
    concord_chart = chart_png(concord_trend, 'Área com concordância multíndice por ano', 'concordance_pct', '% dos pixels válidos')
    if concord_chart:
        images['concord_chart'] = concord_chart
        files['imagens/concordancia_serie_historica.png'] = concord_chart

    for spec in map_specs or []:
        try:
            png = earth_engine_thumb(spec['image'], spec['vis'], geometry)
            point_source = (
                concord_points
                if str(spec.get('name', '')).startswith('concord')
                else main_points
            )
            png = annotate_investigation_points(
                png, point_source, geometry, max_points=25
            )
            images[spec['name']] = png
            files[f"imagens/{spec['filename']}"] = png
        except Exception as exc:
            warnings.append(f"Não foi possível gerar {spec.get('filename', spec.get('name'))}: {type(exc).__name__}")

    pdf = create_pdf_report(
        logo_path=logo_path,
        field_name=field_name,
        parameters=parameters,
        main_points=main_points,
        main_trend=main_trend,
        concord_points=concord_points,
        concord_trend=concord_trend,
        images=images,
    )
    files[f'relatorio/Relatorio_LandVision_{safe}.pdf'] = pdf

    readme = f"""LANDVISION - PACOTE DE ANÁLISE\n\nTalhão: {field_name}\nGerado em: {datetime.now().isoformat(timespec='minutes')}\n\nCONTEÚDO\n- relatorio/: PDF técnico da análise\n- imagens/: mapas analíticos e gráficos em PNG\n- dados/: CSV, KML, GeoJSON e parâmetros usados\n\nIMPORTANTE\nOs resultados espectrais são indicadores exploratórios e devem ser validados em campo.\nNenhuma credencial, chave ou conteúdo do Streamlit Secrets é incluído neste pacote.\n"""
    files['LEIA-ME.txt'] = readme.encode('utf-8')

    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, data in files.items():
            zf.writestr(filename, data)
    return out.getvalue(), warnings

# LANDVISION — V0.1 (interface)

## Instalação (Windows / PowerShell)
1. Instale Python 3.11 ou 3.12 e marque 'Add Python to PATH'.
2. Extraia o ZIP e abra um terminal na pasta `landvision`.
3. Execute:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Caso a política do PowerShell impeça a ativação, execute os comandos diretamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

O navegador abre o endereço local exibido pelo Streamlit (geralmente http://localhost:8501).

## O que funciona nesta etapa
- Layout com controles para data única, período, índice e mapa-base;
- Dois mapas, com imagem de satélite como mapa-base;
- Desenho de polígono no mapa esquerdo ou importação de GeoJSON;
- O polígono é mostrado nos dois mapas e pode ser exportado em GeoJSON;
- Coordenadas para localizar a área.

## O que ainda não está conectado
Não há processamento Sentinel-2, NDVI, NDRE, NDMI, classificação de estresse, recorrência histórica ou gráfico real nesta versão. Esses módulos serão migrados do GEE V20.2 na etapa 2, usando `earthengine-api`/`geemap` e credenciais/ projeto GEE elegível.

**Nota:** O arquivo de script `.txt` entregue junto com o ZIP é uma cópia do `app.py` para leitura e edição.

# LandVision V0.3 — plataforma web de investigação agrícola

Versão preparada para publicar no **mesmo** repositório do GitHub e manter o mesmo endereço do Streamlit. Inclui o símbolo PNG fornecido pelo usuário (sem alegar que seja um logo oficial licenciado), paleta solicitada `#0C243A`, `#2C3D20`, `#95A237`, `#919CA8`, `#F1F1F1`, e favicon.

## Arquivos a enviar ao GitHub

Coloque **todos** estes itens na raiz do seu repositório, sem enviar apenas o ZIP:

- `app.py` (substituir)
- `engine.py` (substituir)
- `requirements.txt` (substituir)
- `README.md` (substituir)
- `.streamlit/config.toml` (criar pasta e arquivo, se necessário)
- `assets/simbolo_enviado.png` (criar pasta `assets` e enviar imagem)

Faça **Commit changes**. O aplicativo principal continua `app.py`. O Streamlit deve iniciar novo deploy automaticamente. Se o arquivo de imagem estiver faltando ou mudar de pasta, corrija `SYMBOL` em `app.py`.

## Recursos

- Dois mapas com satélite/ruas, desenho/importação/exportação de talhão (GeoJSON).
- Modo data exata (mosaico das cenas do dia) ou intervalo de meses (mediana); histórico dos 5 anos anteriores no mesmo período ou ±10 dias de cada data histórica.
- Camadas disponíveis no mapa atual: NDVI, NDRE, NDMI, NDWI de água superficial (verde–NIR), EVI, SAVI, ARVI, DVI, NBR, NBR2 e GNDVI.
- Busca de até 30 datas Sentinel-2 com máximo de 25% de nuvem na cena, ranqueadas por cobertura válida SCL dentro do talhão.
- Detector **independente do seletor de camada**, com método preservado da V20.2: NDVI z < -1, NDRE z < -1, |NDMI z| > 1; 2 ou mais sinais indicam anomalia espacial exploratória. Busca repetição em 3/4/5 dos últimos 5 anos, mínimo de anos válidos por pixel e mínimo de área de região.
- Marcação de centroides e exportações CSV (coordenadas), GeoJSON (regiões), KML (pontos); gráfico percentual por ano. Limite operacional de 100 regiões exibidas/exportadas por análise. Coordenadas não indicam a causa do estresse nem têm precisão de levantamento topográfico.
- Sem dados falsos: se Earth Engine não estiver conectado, a interface exibe mapas-base mas **não** resultados espectrais.

## Ativar Earth Engine no Streamlit

É necessário ter um projeto Google Cloud **registrado no Earth Engine**, a Earth Engine API habilitada e uma conta de serviço com permissões adequadas para esse projeto. Verifique os termos e cotas do Earth Engine para a natureza do uso (uso empresarial não é automaticamente gratuito).

No Streamlit Community Cloud: **Manage app → Settings → Secrets**. Cadastre o seguinte TOML, preenchendo *somente ali* com os valores verdadeiros da conta de serviço:

```toml
[gee]
project = "SEU_GOOGLE_CLOUD_PROJECT_ID"
service_account = "SUA_CONTA@SEU_PROJETO.iam.gserviceaccount.com"
private_key_id = "ID_DA_CHAVE"
private_key = "-----BEGIN PRIVATE KEY-----\nCONTEUDO_DA_CHAVE\n-----END PRIVATE KEY-----\n"
```

**Nunca** envie chave JSON, private key, screenshots contendo secrets ou `.streamlit/secrets.toml` para repositório público. Não há integração automática com o login pessoal do Earth Engine: autenticar esta aplicação publicada requer configuração explícita de credenciais e permissões. Se ocorrer erro, abra os logs do Streamlit sem compartilhar segredos.

## Como usar

1. Desenhe talhão no Mapa 1 ou importe GeoJSON. Ajuste latitude/longitude para navegar.
2. Escolha **DATA ÚNICA** ou **PERÍODO**, selecione o índice visual desejado.
3. Opcionalmente busque melhores datas para escolher uma imagem com maior cobertura válida.
4. Ajuste mínimo de recorrência/anos válidos/área e clique em **Executar análise**. Espere o processamento Earth Engine.
5. Consulte a camada no Mapa 1, a recorrência no Mapa 2, o gráfico e as coordenadas dos centroides; exporte os arquivos desejados.

**Metodologia e limites:** cenas até 80% nuvem na análise, classes SCL 0/1/3/8/9/10/11 mascaradas; pixels sem imagem válida não entram no denominador da recorrência. A análise anual pressupõe comparação de mesma cultura e estádio fenológico; uma data escolhida com cena válida ainda pode não cobrir todos os pixels do talhão. Índice diferente/menor não equivale necessariamente a estresse nem a doença. Recorrência = anos com anomalia / anos válidos, e a configuração de X anos exige X ocorrências dentre os cinco anos anteriores. Para volumes muito grandes, reduza a área ou restrinja os parâmetros antes de vetorização.

## Instalação local, se desejar

`pip install -r requirements.txt` e `streamlit run app.py`. Cadastre as mesmas credenciais em `.streamlit/secrets.toml` localmente, sem commit. O site publicado não exige instalar Python no computador dos visitantes.

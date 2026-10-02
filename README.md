# LandVision V0.4 — processamento Earth Engine com foco em eficiência

Mantenha o **mesmo** repositório e a implantação Streamlit existente. Página principal: `app.py`.

## Estrutura do GitHub

```
LandVision/
  app.py
  engine.py
  requirements.txt
  README.md
  .streamlit/config.toml
  assets/simbolo_enviado.png
```

Não publique o arquivo JSON de credenciais, o `.streamlit/secrets.toml` nem prints com `private_key`.

## Ativação (faça as etapas na sua própria conta)

1. Confirme se o seu projeto Google Cloud está **registrado no Earth Engine** e com a **Earth Engine API habilitada**: https://console.cloud.google.com/ e https://code.earthengine.google.com/register . A categoria não comercial é exclusiva para usos elegíveis, não cobre automaticamente produção de uma empresa.
2. Em **IAM e administrador → Contas de serviço (Service Accounts)**, crie uma conta para o LandVision. Nas permissões de projeto, conceda somente o necessário: `Earth Engine Resource Viewer` (`roles/earthengine.viewer`) e `Service Usage Consumer` (`roles/serviceusage.serviceUsageConsumer`). Siga a política da sua organização; algumas contas podem restringir geração de chave.
3. Na conta de serviço, em **Keys → Add key → Create new key → JSON**, baixe a chave em seu computador e guarde-a em local privado. NUNCA a envie por chat, e-mail público ou GitHub. Se não puder criar chave por política de segurança, será necessário hospedar em ambiente com Application Default Credentials (ADC), como Cloud Run, em vez de Community Cloud com chave.
4. Abra seu app no Streamlit, clique **Manage app → ⋮ → Settings → Secrets**, ou entre em `https://share.streamlit.io/`, localize LandVision, ⋮ → Settings → Secrets. Cole SOMENTE ali o seguinte TOML, substituindo valores pelo conteúdo do JSON da conta de serviço:

```toml
[gee]
project = "ID-DO-PROJETO-GOOGLE-CLOUD"
service_account_json = '''
{
  "type": "service_account",
  "project_id": "ID-DO-PROJETO-GOOGLE-CLOUD",
  "private_key_id": "VALOR-DA-CHAVE-JSON",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "CONTA-DE-SERVICO@PROJETO.iam.gserviceaccount.com",
  "client_id": "VALOR-DO-JSON",
  "token_uri": "https://oauth2.googleapis.com/token"
}
'''
```

**Mais fácil e mais seguro contra erros de transcrição:** no bloco `service_account_json`, cole TODO o conteúdo do JSON original, intacto, entre as três aspas simples. Mantenha `project` com o ID do projeto de uso/quota (que pode coincidir com o projeto da conta de serviço). A linha de exemplo `private_key` é **ilustrativa**, não é uma chave válida.

O formato anterior da V0.3 também continua aceito:

```toml
[gee]
project = "ID-DO-PROJETO"
service_account = "CONTA@PROJETO.iam.gserviceaccount.com"
private_key_id = "ID-DA-CHAVE"
private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
```

5. Clique **Save** e atualize a página. Clique **Testar conexão Earth Engine**: essa ação executa uma requisição mínima ao serviço, sem processar 5 anos. Se falhar, confira `project`, API, registro e os papéis IAM. Não envie prints da aba Secrets; envie apenas mensagem pública de erro (sem chaves).
6. Desenhe ou importe um polígono GeoJSON, selecione data/período, opcionalmente busque boas datas e clique **Executar análise**.

Fontes: https://developers.google.com/earth-engine/guides/service_account , https://developers.google.com/earth-engine/guides/access_control , https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings .

## O que ficou mais eficiente

- **Histórico de cinco anos:** calcula apenas NDVI, NDRE, NDMI, pois são as três bandas do detector.
- **Mapa atual:** calcula as três bandas do detector mais um índice adicional apenas se foi selecionado.
- A imagem atual não é construída duas vezes.
- A estatística espacial das três bandas é solicitada em um único `reduceRegion` por ano, em escala nominal de 20 m; sem `bestEffort`, que poderia degradar a resolução silenciosamente.
- A busca de até 30 datas agrupa três listas em uma resposta do servidor e não altera a seleção automaticamente.
- Vetorização aplica filtro de área, ordena e limita a 101 regiões **antes** das estatísticas detalhadas. Até 100 pontos são exibidos/exportados; se houver mais, o app avisa.
- A análise só roda após clique; alterar controles invalida os resultados anteriores para não apresentá-los como atuais. Limite preventivo de 2.000 ha por consulta nesta versão.
- As duas camadas coloridas são reais e só aparecem se a API estiver autorizada. O detector é exploratório: anomalia espectral recorrente não diagnostica doença, fertilidade ou compactação.

**Cautelas:** A condição de 4/5 representa 4 anos com anomalia entre cinco anos históricos; o percentual de recorrência usa como denominador os anos válidos por pixel. A ausência de imagem não é computada como zero. Os centroides das regiões a 20 m são pontos aproximados para investigação, não levantamento topográfico. Evite misturar épocas fenológicas ou culturas distintas em interpretações de estresse. A disponibilidade, capacidade e gratuidade estão sujeitas às regras e cotas do Earth Engine e do Streamlit.

## Verificação

`python -m py_compile app.py engine.py` verifica sintaxe. Sem credenciais privadas reais, não se consegue confirmar end-to-end o processamento no servidor Earth Engine. Teste de conexão disponível no menu lateral.

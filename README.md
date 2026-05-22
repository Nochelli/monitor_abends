# monitor_abends
Programa escrito em Python para monitorar Mainframe job ABENDs via z/OSMF com a interface do ZOWE no VSCODE _(extenção IBM Z Open Editor)_. Programa monitora de 5 em 5 minutos e envia alertas para o appl Telegram caso houver abends.

# Requisitos
1) Assim que instalar o ZOWE no VSCODE é necessário configurar o arquivo `zowe_config.json`, é aqui que inserimos o host e porta do z/OSMF. Segue imagem abaixo dos campos que precisam ser configurado:
![Minha imagem de exempl](JSON_FILE.png)

2) Variáveis de ambiente:
  - `ZOWE_USER`
  - `ZOWE_PASSWORD`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - 
No Powershell eu configurei as variáveis juntamente com o comando .py para rodar o programa. Segue abaixo.
_(lembrando que é preciso criar um BOT no BotFather do Telegram para ter o TOKEN e CHAT ID)_

$env:ZOWE_USER = "seu_usuario"
$env:ZOWE_PASSWORD = "sua_senha"
$env:TELEGRAM_BOT_TOKEN = "seu_token_do_bot"
$env:TELEGRAM_CHAT_ID = "seu_chat_id"

python monitor_abends.py

# Instale dependências:

```bash
python -m pip install -r requirements.txt
```

## Como funciona

- Conecta ao z/OSMF usando as configurações de `zowe_config.json`.
- Busca jobs com status `ENDED`.
- Lê o `JOBLOG` de cada job.
- Detecta ABENDs por padrão de texto ou RC.
- Envia alerta via Telegram para o `chat_id` configurado.

## Arquivos

- `monitor_abends.py`: script principal.
- `zowe_config.json`: configuração de acesso Zowe.
- `requirements.txt`: dependências.
- `.last_seen_jobs.json`: estado local gerado automaticamente.

# search_job_abend

Monitor mainframe job ABENDs via z/OSMF e envie alertas para Telegram.

## Requisitos

- Python 3.8+
- `requests`
- Zowe `zowe_config.json` configurado com host e porta do z/OSMF
- Variáveis de ambiente:
  - `ZOWE_USER`
  - `ZOWE_PASSWORD`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`

## Instalação

1. Instale dependências:

```bash
python -m pip install -r requirements.txt
```

2. Configure as credenciais do Zowe e do Telegram:

```bash
setx ZOWE_USER "seu_usuario"
setx ZOWE_PASSWORD "sua_senha"
setx TELEGRAM_BOT_TOKEN "seu_token_do_bot"
setx TELEGRAM_CHAT_ID "seu_chat_id"
```

> No PowerShell, use `setx` para definir variáveis de ambiente permanentes. Para a sessão atual, use `set`.

## Uso

Executar uma vez:

```bash
python monitor_abends.py --config zowe_config.json --state .last_seen_jobs.json
```

Executar em loop a cada 5 minutos:

```bash
python monitor_abends.py --interval 300 --config zowe_config.json --state .last_seen_jobs.json
```

## Como funciona

- Conecta ao z/OSMF usando as configurações de `zowe_config.json`.
- Busca jobs com status `ENDED`.
- Lê o `JOBLOG` de cada job.
- Detecta ABENDs por padrão de texto ou condição final.
- Envia alerta via Telegram para o `chat_id` configurado.

## Arquivos

- `monitor_abends.py`: script principal.
- `zowe_config.json`: configuração de acesso Zowe.
- `requirements.txt`: dependências.
- `.last_seen_jobs.json`: estado local gerado automaticamente.

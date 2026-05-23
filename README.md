# Monitor Abends
![Author](https://img.shields.io/badge/Author-Jeferson%20Nochelli-blue)

Programa escrito em **Python** para monitorar **Mainframe job ABENDs via z/OSMF com a interface do ZOWE no VSCODE** _(extenção IBM Z Open Editor)_. 
O Monitor Abend verifica os jobs automaticamente a cada 5 minutos e envia alertas para um BOT no Telegram caso algum ABEND seja identificado.

## Requisitos e Configurações:

1) Após instalar o ZOWE no VSCode, será carregado o arquivo `zowe_config.json`, é nele que configuramos o host, account e porta do z/OSMF. Configure os campos que estão indicados na imagem abaixo:
   
![JSON](JSON_FILE.png)   

_(O arquivo `zowe_config.json` já está disponível no repositório caso queira utilizá-lo como modelo. Basta substituir pelo arquivo original após realizar as configurações necessárias.)_


2) Variáveis de ambiente:
  - `ZOWE_USER`
  - `ZOWE_PASSWORD`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
    
Eu utilizei o Powershell para configurar as variáveis juntamente com o comando .py para rodar o programa logo em seguida. Segue abaixo.
_(lembrando que é preciso criar um BOT no BotFather do Telegram para ter o TOKEN e CHAT ID)_

```bash
$env:ZOWE_USER = "seu_usuario"
$env:ZOWE_PASSWORD = "sua_senha"
$env:TELEGRAM_BOT_TOKEN = "seu_token_do_bot"
$env:TELEGRAM_CHAT_ID = "seu_chat_id"

python monitor_abends.py
```

3) Instale dependências:

```bash
python -m pip install -r requirements.txt
```

# Como funciona
 - Na imagem abaixo simulei um Job Abend dentro do ZOWE.
   - `Job: @REXX1`
   - `JOBID: JOB04361`
   - `RC=0127`
   - `THURSDAY, 21 MAY` _(horário do Mainframe se difere do meu fuso horário)_
     
![JESJCL](ABEND_NO_JESJCL.png)   

Na imagem abaixo podemos notar o programa `monitor_abends` em funcionamento! _(com o intervalo de 5min em 5min)_

Note que o programa se conecta ao z/OSMF usando as configurações definidas no arquivo `zowe_config.json`, busca jobs com status `ENDED`, lê o `JOBLOG` de cada job e detecta ABENDs por padrão de texto ou RC.
Em seguida, o programa já indentificou que o **JOB @REXX1 (JOBID JOB04361)** abendou e dessa forma envia o alerta:

![TERMINAL](ABEND_NO_TERMINAL.png) 

O alerta é enviado ao BOT no Telegram, assim como na imagem abaixo:

_durante o looping, esse mesmo abend não será alertado novamente pois o programa mantém um controle local utilizando: `.last_seen_jobs.json`_.
_Assim, o mesmo JOB não gera múltiplos alertas repetidos._

<img src="https://github.com/Nochelli/monitor_abends/blob/main/ALERTA_TELEGRAM.png" width="400">


_O envio de alertas foi implementado utilizando o Telegram por ser simples de configurar e fácil de acompanhar pelo celular. Porém, nada impede de adicionar outros métodos de notificação, assim como o envio por e-mail que também seria bem prático._


## Arquivos no repositório:

- `monitor_abends.py`: script principal.
- `zowe_config.json`: configuração de acesso Zowe.
- `requirements.txt`: dependências.
- `.last_seen_jobs.json`: guarda o último estado dos jobs monitorados, esse arquivo é gerado automaticamente após rodar o monitor_abends.
- `ABEND_NO_JESJCL.png`: imagem para o README
- `ABEND_NO_TERMINAL.png`: imagem para o README
- `ALERTA_TELEGRAM.png`: imagem para o README
- `JSON_FILE.png`: imagem para o README

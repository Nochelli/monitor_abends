import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

ABEND_PATTERNS = re.compile(
    r"\b(ABEND|S0C[0-9A-F]|S0CB|S806|S322|U4044|U4033|U4088)\b",
    flags=re.IGNORECASE,
)
KNOWN_OK_RETURN_CODES = {"0", "00", "0000", "0H", "00H", "000H"}


def load_json_file(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(path: Path, data: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def build_zosmf_base_url(config: Dict[str, Any], profile_name: str = "zosmf") -> str:
    defaults = config.get("defaults", {})
    zosmf_profile = defaults.get(profile_name, profile_name)
    base_profile = defaults.get("base", "base")

    zosmf_properties = config["profiles"][zosmf_profile]["properties"]
    base_properties = config["profiles"][base_profile]["properties"]

    host = base_properties.get("host")
    port = zosmf_properties.get("port", 443)
    scheme = "https"

    return f"{scheme}://{host}:{port}/zosmf"


def get_zowe_credentials() -> Dict[str, str]:
    user = os.environ.get("ZOWE_USER") or os.environ.get("ZOWE_USERNAME")
    password = os.environ.get("ZOWE_PASSWORD")

    if not user or not password:
        raise RuntimeError(
            "As variáveis de ambiente ZOWE_USER e ZOWE_PASSWORD são obrigatórias."
        )

    return {"user": user, "password": password}


def get_telegram_config() -> Dict[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "As variáveis de ambiente TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID são obrigatórias."
        )

    return {"token": token, "chat_id": chat_id}


def create_authenticated_session(config: Dict[str, Any]) -> requests.Session:
    creds = get_zowe_credentials()
    base_profile = config.get("defaults", {}).get("base", "base")
    verify = config["profiles"][base_profile]["properties"].get(
        "rejectUnauthorized", True
    )

    session = requests.Session()
    session.auth = (creds["user"], creds["password"])
    session.verify = verify
    session.headers.update({"Accept": "application/json"})
    return session


def parse_field(job: Dict[str, Any], field_names: List[str]) -> Optional[str]:
    for name in field_names:
        if name in job and job[name] is not None:
            return str(job[name])
    return None


def normalize_return_code(rc_value: Optional[str]) -> Optional[int]:
    if rc_value is None:
        return None

    rc_text = str(rc_value).strip().upper()
    if rc_text in KNOWN_OK_RETURN_CODES:
        return 0

    if rc_text.endswith("H"):
        rc_text = rc_text[:-1]
        try:
            return int(rc_text, 16)
        except ValueError:
            return None

    try:
        return int(rc_text, 10)
    except ValueError:
        try:
            return int(rc_text, 16)
        except ValueError:
            return None


def format_job_key(job: Dict[str, Any]) -> str:
    name = parse_field(job, ["jobName", "jobname", "job_name"]) or "UNKNOWN"
    jid = parse_field(job, ["jobId", "jobid", "job_id"]) or "UNKNOWN"
    return f"{name}:{jid}"


def fetch_jobs(session: requests.Session, base_url: str, max_jobs: int) -> List[Dict[str, Any]]:
    url = f"{base_url}/restjobs/jobs"
    params = {"status": "ENDED", "limit": max_jobs}
    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()

    data = response.json()
    if isinstance(data, dict) and "jobs" in data:
        jobs = data["jobs"]
    elif isinstance(data, list):
        jobs = data
    else:
        jobs = [data]

    return jobs if isinstance(jobs, list) else [jobs]


def fetch_job_log(
    session: requests.Session, base_url: str, job_name: str, job_id: str
) -> str:
    quoted_job_name = quote(job_name, safe="")
    quoted_job_id = quote(job_id, safe="")
    url = f"{base_url}/restjobs/jobs/{quoted_job_name}/{quoted_job_id}/output"
    params = {"type": "JOBLOG"}
    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()

    try:
        payload = response.json()
        if isinstance(payload, dict):
            if "output" in payload:
                output = payload["output"]
                if isinstance(output, list):
                    return "\n".join(str(line) for line in output)
                return str(output)
            if "jobLog" in payload:
                return str(payload["jobLog"])
            return json.dumps(payload)
    except ValueError:
        return response.text

    return response.text


def contains_abend(job: Dict[str, Any], job_log: str) -> bool:
    if ABEND_PATTERNS.search(job_log):
        return True
    final_condition = parse_field(job, ["finalCondition", "final_condition"])
    if final_condition and final_condition.upper() == "ABEND":
        return True
    return False


def build_alert_message(job: Dict[str, Any], job_log: str) -> str:
    job_name = parse_field(job, ["jobName", "jobname", "job_name"]) or "UNKNOWN"
    job_id = parse_field(job, ["jobId", "jobid", "job_id"]) or "UNKNOWN"
    owner = parse_field(job, ["owner", "user", "jobOwner"]) or "UNKNOWN"
    return_code = parse_field(job, ["returnCode", "return_code"]) or "UNKNOWN"
    status = parse_field(job, ["status", "jobStatus"]) or "UNKNOWN"

    excerpt = job_log
    if len(excerpt) > 1000:
        excerpt = excerpt[:1000].rsplit("\n", 1)[0] + "\n..."

    safe_excerpt = excerpt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return (
        f"<b>ALERTA de ABEND</b>\n"
        f"<b>JOB</b>: {job_name}\n"
        f"<b>JOBID</b>: {job_id}\n"
        f"<b>OWNER</b>: {owner}\n"
        f"<b>STATUS</b>: {status}\n"
        f"<b>RETURN CODE</b>: {return_code}\n"
        f"<b>TRECHO DO JOBLOG</b>:\n<pre>{safe_excerpt}</pre>"
    )


def send_telegram_alert(token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"alerted_jobs": []}
    return load_json_file(path)


def save_state(path: Path, state: Dict[str, Any]) -> None:
    state["alerted_jobs"] = sorted(set(state.get("alerted_jobs", [])))
    save_json_file(path, state)


def scan_and_alert(
    config_path: Path,
    state_path: Path,
    max_jobs: int,
    verbose: bool,
) -> None:
    config = load_json_file(config_path)
    base_url = build_zosmf_base_url(config)
    session = create_authenticated_session(config)
    telegram_cfg = get_telegram_config()
    state = load_state(state_path)
    alerted_jobs = set(state.get("alerted_jobs", []))

    jobs = fetch_jobs(session, base_url, max_jobs)
    logging.info("Encontradas %d jobs no z/OSMF.", len(jobs))

    new_alerts = 0
    for job in jobs:
        job_key = format_job_key(job)
        if job_key in alerted_jobs:
            logging.debug("Job já alertado: %s", job_key)
            continue

        job_name = parse_field(job, ["jobName", "jobname", "job_name"]) or "UNKNOWN"
        job_id = parse_field(job, ["jobId", "jobid", "job_id"]) or "UNKNOWN"

        try:
            job_log = fetch_job_log(session, base_url, job_name, job_id)
        except Exception as exc:
            logging.warning(
                "Falha ao buscar joblog para %s: %s. Ignorando esta job por enquanto.",
                job_key,
                exc,
            )
            continue

        if contains_abend(job, job_log):
            message = build_alert_message(job, job_log)
            send_telegram_alert(
                telegram_cfg["token"], telegram_cfg["chat_id"], message
            )
            alerted_jobs.add(job_key)
            new_alerts += 1
            logging.info("Alerta enviado para job %s.", job_key)
        elif verbose:
            logging.debug("Job sem ABEND detectado: %s", job_key)

    state["alerted_jobs"] = list(alerted_jobs)
    save_state(state_path, state)

    logging.info("Novos alertas enviados: %d", new_alerts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monitora abends de jobs no mainframe via z/OSMF e envia alertas para Telegram."
    )
    parser.add_argument(
        "--config",
        default="zowe_config.json",
        help="Caminho para o arquivo de configuração Zowe JSON.",
    )
    parser.add_argument(
        "--state",
        default=".last_seen_jobs.json",
        help="Arquivo de estado local para evitar alertas duplicados.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=100,
        help="Máximo de jobs retornados em cada verificação.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="Intervalo em segundos para executar periodicamente. 0 executa uma vez.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Exibe logs mais verbosos para depuração.",
    )

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config_path = Path(args.config)
    state_path = Path(args.state)

    if not config_path.exists():
        logging.error("Arquivo de configuração não encontrado: %s", config_path)
        return 1

    try:
        if args.interval > 0:
            logging.info("Iniciando monitoramento com intervalo de %s segundos.", args.interval)
            while True:
                scan_and_alert(config_path, state_path, args.max_jobs, args.verbose)
                time.sleep(args.interval)
        else:
            scan_and_alert(config_path, state_path, args.max_jobs, args.verbose)
    except KeyboardInterrupt:
        logging.info("Monitoramento interrompido pelo usuário.")
        return 0
    except Exception as exc:
        logging.exception("Erro durante a execução: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
import urllib3

ABEND_PATTERNS = re.compile(
    r"\b(ABEND|S0C[0-9A-F]|S0CB|S806|S322|U4044|U4033|U4088)\b",
    flags=re.IGNORECASE,
)
KNOWN_OK_RETURN_CODES = {"0", "00", "0000", "0H", "00H", "000H"}
RETURN_CODE_LOG_PATTERNS = [
    re.compile(r"\b(?:return(?: |_)?code|rc|cc|condition(?: |_)?code|return value)\b[^0-9A-Fa-f]*([0-9A-Fa-f]{1,4}H?)", re.IGNORECASE),
    re.compile(r"\b(?:RC|rc|CC|cc)\W*[:=]?\W*([0-9A-Fa-f]{1,4}H?)\b"),
    re.compile(r"\b([0-9A-Fa-f]{1,4}H?)\b"),
]


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
            "As variáveis de ambiente ZOWE_USER (ou ZOWE_USERNAME) e ZOWE_PASSWORD são obrigatórias."
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
    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session.headers.update({"Accept": "application/json"})
    return session


def parse_field(job: Dict[str, Any], field_names: List[str]) -> Optional[str]:
    for name in field_names:
        if name in job and job[name] is not None:
            return str(job[name])
    return None


def find_field_recursive(data: Any, field_names: List[str]) -> Optional[str]:
    if isinstance(data, dict):
        for name, value in data.items():
            if name in field_names and value is not None:
                return str(value)
            nested = find_field_recursive(value, field_names)
            if nested is not None:
                return nested
    elif isinstance(data, list):
        for item in data:
            nested = find_field_recursive(item, field_names)
            if nested is not None:
                return nested
    return None


def parse_return_code(job: Dict[str, Any]) -> Optional[str]:
    names = [
        "returnCode",
        "return_code",
        "returncode",
        "rc",
        "RC",
        "return",
        "jobReturnCode",
        "job_rc",
    ]
    result = parse_field(job, names)
    if result is not None:
        return result
    return find_field_recursive(job, names)


def extract_return_code_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    lines = text.splitlines()
    for pattern in RETURN_CODE_LOG_PATTERNS:
        for line in lines:
            match = pattern.search(line)
            if match:
                return match.group(1).upper()

    keyword_search = re.compile(r"\b(return|rc|cc|condition|abend|returned|return code|cond)\b", re.IGNORECASE)
    for line in reversed(lines[-40:]):
        if keyword_search.search(line):
            fallback = re.search(r"\b([0-9A-Fa-f]{1,4}H?)\b", line)
            if fallback:
                return fallback.group(1).upper()

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


def parse_job_timestamp(job: Dict[str, Any]) -> Optional[str]:
    time_fields = [
        "endTime",
        "end_time",
        "jobEndTime",
        "job_end_time",
        "endDate",
        "end_date",
        "submitTime",
        "submit_time",
        "startTime",
        "start_time",
        "createdAt",
        "created_at",
        "updatedAt",
        "updated_at",
        "timestamp",
        "date",
        "time",
    ]
    timestamp = parse_field(job, time_fields)
    if timestamp:
        return str(timestamp)
    return None


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

    candidates = [
        (f"{base_url}/restjobs/jobs/{quoted_job_name}/{quoted_job_id}/output", {"type": "JOBLOG", "format": "TEXT"}, {"Accept": "text/plain"}),
        (f"{base_url}/restjobs/jobs/{quoted_job_name}/{quoted_job_id}/output", {"type": "JOBLOG"}, {"Accept": "text/plain"}),
        (f"{base_url}/restjobs/jobs/{quoted_job_name}/{quoted_job_id}", {"type": "JOBLOG"}, {"Accept": "text/plain"}),
        (f"{base_url}/restjobs/jobs/{quoted_job_name}/{quoted_job_id}/joblog", {}, {"Accept": "text/plain"}),
        (f"{base_url}/restjobs/jobs/{quoted_job_name}/{quoted_job_id}/log", {}, {"Accept": "text/plain"}),
    ]

    last_response = None
    last_url = None
    for url, params, headers in candidates:
        response = session.get(url, params=params, headers=headers, timeout=60)
        if response.status_code == 200:
            last_response = response
            last_url = url
            break
        if response.status_code != 400:
            response.raise_for_status()
        last_response = response
        last_url = url

    if last_response is None:
        raise RuntimeError("Não foi possível recuperar o JOBLOG do servidor.")

    if last_response.status_code != 200:
        extra = ""
        try:
            extra = last_response.text
        except Exception:
            extra = ""
        raise RuntimeError(
            f"Falha ao recuperar JOBLOG usando {last_url}: {last_response.status_code} {extra}"
        )

    if last_response.headers.get("Content-Type", "").startswith("application/json"):
        try:
            payload = last_response.json()
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
            pass

    return last_response.text


def contains_abend(job: Dict[str, Any], job_log: str) -> bool:
    return_code = parse_return_code(job)
    if return_code is not None:
        normalized = normalize_return_code(return_code)
        if normalized is not None and normalized != 0:
            return True

    if ABEND_PATTERNS.search(job_log):
        return True
    final_condition = parse_field(job, ["finalCondition", "final_condition"])
    if final_condition and final_condition.upper() == "ABEND":
        return True
    return False


def build_alert_message(job: Dict[str, Any], job_log: str) -> str:
    job_name = parse_field(job, ["jobName", "jobname", "job_name"]) or "UNKNOWN"
    job_id = parse_field(job, ["jobId", "jobid", "job_id"]) or "UNKNOWN"
    return_code = parse_return_code(job) or "UNKNOWN"
    timestamp = parse_job_timestamp(job) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return (
        f"<b>ALERTA de ABEND</b>\n"
        f"<b>JOB</b>: {job_name}\n"
        f"<b>JOBID</b>: {job_id}\n"
        f"<b>DATA/HORA</b>: {timestamp}\n"
        f"<b>RETURN CODE</b>: {return_code}\n"
        f"\nFavor verificar."
    )


def build_jobs_summary_message(job_infos: List[Dict[str, Any]]) -> str:
    lines = []
    for job in job_infos:
        job_name = job.get("job_name", "UNKNOWN")
        job_id = job.get("job_id", "UNKNOWN")
        return_code = job.get("return_code", "UNKNOWN")
        status = job.get("status", "UNKNOWN")
        final_condition = job.get("final_condition", "UNKNOWN")
        lines.append(
            f"{job_name}/{job_id} RC={return_code} STATUS={status} FINAL={final_condition}"
        )

    excerpt = "\n".join(lines)
    if len(excerpt) > 3800:
        excerpt = excerpt[:3800].rsplit("\n", 1)[0] + "\n..."

    safe_excerpt = excerpt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f"<b>RELATÓRIO de JOBS</b>\n"
        f"<b>Total de jobs</b>: {len(job_infos)}\n"
        f"<pre>{safe_excerpt}</pre>"
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
    send_summary: bool,
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
    job_infos: List[Dict[str, Any]] = []
    for job in jobs:
        job_key = format_job_key(job)
        job_name = parse_field(job, ["jobName", "jobname", "job_name"]) or "UNKNOWN"
        job_id = parse_field(job, ["jobId", "jobid", "job_id"]) or "UNKNOWN"
        return_code = parse_return_code(job) or "UNKNOWN"
        final_condition = parse_field(job, ["finalCondition", "final_condition"]) or "UNKNOWN"
        status = parse_field(job, ["status", "jobStatus"]) or "UNKNOWN"
        job_log = None

        should_fetch_log = False
        if return_code == "UNKNOWN":
            should_fetch_log = True
        if job_key not in alerted_jobs:
            should_fetch_log = True

        if should_fetch_log:
            try:
                job_log = fetch_job_log(session, base_url, job_name, job_id)
                if return_code == "UNKNOWN":
                    extracted = extract_return_code_from_text(job_log)
                    if extracted:
                        return_code = extracted
                        job["returnCode"] = extracted
            except Exception as exc:
                logging.warning(
                    "Falha ao buscar joblog para %s: %s.",
                    job_key,
                    exc,
                )
                job_log = ""

        job_infos.append(
            {
                "job_name": job_name,
                "job_id": job_id,
                "return_code": return_code,
                "status": status,
                "final_condition": final_condition,
            }
        )

        if job_key in alerted_jobs:
            logging.debug("Job já alertado: %s", job_key)
            continue

        if contains_abend(job, job_log or ""):
            message = build_alert_message(job, job_log or "")
            send_telegram_alert(
                telegram_cfg["token"], telegram_cfg["chat_id"], message
            )
            alerted_jobs.add(job_key)
            new_alerts += 1
            logging.info("Alerta enviado para job %s.", job_key)
        else:
            if verbose:
                if not job_log:
                    logging.debug("Job %s: joblog não disponível.", job_key)
                else:
                    logging.debug("Job %s: sem ABEND detectado (RC=%s, Status=%s).", job_key, return_code, status)

    if send_summary:
        summary = build_jobs_summary_message(job_infos)
        send_telegram_alert(
            telegram_cfg["token"], telegram_cfg["chat_id"], summary
        )
        logging.info("Relatório de jobs enviado para Telegram.")

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
        default=300,
        help="Intervalo em segundos para executar periodicamente. 0 executa uma vez. Default 300s.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Exibe logs mais verbosos para depuração.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Enviar relatório de todos os jobs ao Telegram.",
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
                scan_and_alert(
                    config_path,
                    state_path,
                    args.max_jobs,
                    args.verbose,
                    args.summary,
                )
                time.sleep(args.interval)
        else:
            scan_and_alert(
                config_path,
                state_path,
                args.max_jobs,
                args.verbose,
                args.summary,
            )
    except KeyboardInterrupt:
        logging.info("Monitoramento interrompido pelo usuário.")
        return 0
    except Exception as exc:
        logging.exception("Erro durante a execução: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

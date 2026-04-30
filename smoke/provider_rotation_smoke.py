#!/usr/bin/env python3
"""Reusable live smoke tests for C-f-C Provider Rotation.

This script intentionally avoids printing API keys. It launches isolated local
uvicorn instances, uses temporary health databases, and writes reports under
workbench/output.

Modes:
  runtime   Validate one live runtime request on stable-agentic.
  profiles  Validate all main provider-rotation profiles.
  fallback  Validate controlled failover with temporary model ring configs.
  all       Run runtime, profiles, and fallback.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml


PROJECT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT / "workbench" / "output"
MEMORY_DIR = PROJECT / "memory_store"
CONFIG_PATH = PROJECT / "config" / "model_rings.yaml"

STATUS_ENDPOINT_CANDIDATES = (
    "/v1/provider-rotation/status",
    "/provider-rotation/status",
    "/api/v1/provider-rotation/status",
)


@dataclass(frozen=True)
class SmokeResult:
    name: str
    verdict: str
    http_code: int | None
    profile: str
    port: int
    parsed_model: str | None
    marker_found: bool
    report_files: dict[str, str]
    details: dict[str, Any]


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def load_model_rings(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def assert_required_config(required_profiles: list[str], required_rings: list[str]) -> None:
    data = load_model_rings()
    profiles = data.get("profiles") or {}
    rings = data.get("rings") or {}

    missing_profiles = [profile for profile in required_profiles if profile not in profiles]
    missing_rings = [ring for ring in required_rings if ring not in rings]

    print(f"MODEL_RINGS_FILE={CONFIG_PATH}")
    print("PROFILES=" + ",".join(sorted(profiles)))
    print("RINGS=" + ",".join(sorted(rings)))

    for profile in required_profiles:
        print(f"PROFILE_PRESENT_{profile}={profile in profiles}")

    for ring in required_rings:
        print(f"RING_PRESENT_{ring}={ring in rings}")
        print(f"RING_SIZE_{ring}={len(rings.get(ring, []))}")

    if missing_profiles or missing_rings:
        raise SystemExit(
            "Configuration incomplète: "
            f"missing_profiles={missing_profiles}, missing_rings={missing_rings}"
        )


def port_is_free(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


@contextlib.contextmanager
def launch_server(
    *,
    port: int,
    profile: str,
    health_db: Path,
    log_path: Path,
    auth_token: str,
    config_path: Path | None = None,
):
    env = os.environ.copy()
    env.update(
        {
            "ENABLE_PROVIDER_ROTATION": "true",
            "PROVIDER_ROTATION_PROFILE": profile,
            "MODEL_PROFILE": profile,
            "CFC_MODEL_PROFILE": profile,
            "PROVIDER_ROTATION_HEALTH_DB": str(health_db),
            "ANTHROPIC_AUTH_TOKEN": auth_token,
            "MESSAGING_PLATFORM": "none",
        }
    )

    if config_path is not None:
        env["PROVIDER_ROTATION_CONFIG"] = str(config_path)

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=PROJECT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

    try:
        yield process
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=8)


def wait_for_server(base_url: str, auth_token: str, process: subprocess.Popen[str], log_path: Path) -> None:
    for _ in range(80):
        if process.poll() is not None:
            tail = safe_tail(log_path, 120)
            raise RuntimeError(f"Serveur arrêté pendant le démarrage.\n{tail}")

        try:
            response = requests.get(
                f"{base_url}/v1/models",
                headers={"Authorization": f"Bearer {auth_token}"},
                timeout=2,
            )
            if response.status_code < 500:
                print("SERVER_READY=1")
                return
        except requests.RequestException:
            pass

        time.sleep(0.5)

    tail = safe_tail(log_path, 160)
    raise TimeoutError(f"Serveur non prêt.\n{tail}")


def fetch_rotation_status(base_url: str, auth_token: str) -> tuple[str, dict[str, Any]]:
    for endpoint in STATUS_ENDPOINT_CANDIDATES:
        try:
            response = requests.get(
                f"{base_url}{endpoint}",
                headers={"Authorization": f"Bearer {auth_token}"},
                timeout=10,
            )
        except requests.RequestException:
            continue

        if response.status_code == 200:
            return endpoint, response.json()

    raise RuntimeError("Aucun endpoint provider-rotation/status ne répond en HTTP 200.")


def call_messages(base_url: str, auth_token: str, marker: str, timeout_seconds: int = 240) -> tuple[int, str]:
    payload = {
        "model": "claude-3-opus-20240229",
        "messages": [{"role": "user", "content": f"Réponds exactement : {marker}"}],
        "max_tokens": 80,
    }
    response = requests.post(
        f"{base_url}/v1/messages",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}",
        },
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=timeout_seconds,
    )
    return response.status_code, response.text


def parse_sse(raw: str, marker: str) -> dict[str, Any]:
    model = None
    text_parts: list[str] = []
    error_events: list[str] = []

    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue

        payload = line[6:].strip()
        if not payload or payload == "[DONE]":
            continue

        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "message_start":
            model = (event.get("message") or {}).get("model")

        if event.get("type") in {"error", "message_error"}:
            error_events.append(json.dumps(event, ensure_ascii=False)[:700])

        delta = event.get("delta") or {}
        if isinstance(delta, dict):
            if "text" in delta:
                text_parts.append(str(delta["text"]))
            elif delta.get("type") == "text_delta" and "text" in delta:
                text_parts.append(str(delta["text"]))

    text = "".join(text_parts)
    return {
        "model": model,
        "marker_found": marker in raw or marker in text,
        "text_preview": text[:500],
        "error_events": error_events[:3],
    }


def inspect_health_db(db_path: Path, bad_model_ref: str | None = None, good_fragment: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "db": str(db_path),
        "db_exists": db_path.exists(),
        "tables": [],
        "counts": {},
        "bad_rows_count": 0,
        "good_rows_count": 0,
        "bad_failure_detected": False,
        "good_success_detected": False,
    }

    if not db_path.exists():
        return result

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table' order by name")]
    result["tables"] = tables

    for table in tables:
        try:
            result["counts"][table] = conn.execute(f"select count(*) from {table}").fetchone()[0]
        except sqlite3.Error as exc:
            result["counts"][table] = f"ERROR:{exc}"

    if bad_model_ref is None and good_fragment is None:
        return result

    bad_rows_count = 0
    good_rows_count = 0
    bad_failure_detected = False
    good_success_detected = False

    for table in tables:
        try:
            rows = [dict(row) for row in conn.execute(f"select * from {table}")]
        except sqlite3.Error:
            continue

        for row in rows:
            blob = json.dumps(row, ensure_ascii=False, default=str)
            lower_blob = blob.lower()

            if bad_model_ref and (bad_model_ref in blob or bad_model_ref.split("/", 1)[-1] in blob):
                bad_rows_count += 1
                if any(token in lower_blob for token in ("failure", "failed", "invalid", "disabled", "error")):
                    bad_failure_detected = True

            if good_fragment and good_fragment in blob:
                good_rows_count += 1
                if any(token in lower_blob for token in ("success", "active")):
                    good_success_detected = True

    result.update(
        {
            "bad_rows_count": bad_rows_count,
            "good_rows_count": good_rows_count,
            "bad_failure_detected": bad_failure_detected,
            "good_success_detected": good_success_detected,
        }
    )
    return result


def safe_tail(path: Path, lines: int) -> str:
    if not path.exists():
        return ""

    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-lines:])


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_markdown_report(path: Path, title: str, results: list[SmokeResult]) -> None:
    ok = [item for item in results if item.verdict == "OK"]
    failed = [item for item in results if item.verdict != "OK"]

    lines = [
        f"# {title}",
        "",
        "## Verdict consolidé",
        "",
        "```text",
        f"TESTS={len(results)}",
        f"OK={len(ok)}",
        f"FAILED={len(failed)}",
    ]

    for result in results:
        lines.append(
            f"RESULT name={result.name} profile={result.profile} "
            f"verdict={result.verdict} http={result.http_code} "
            f"port={result.port} model={result.parsed_model}"
        )

    lines.extend(["```", "", "## Fichiers générés", "", "```text"])

    for result in results:
        lines.append(f"{result.name}:")
        for key, value in result.report_files.items():
            lines.append(f"  {key}: {value}")

    lines.extend([f"rapport: {path}", "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def run_one_request(
    *,
    name: str,
    profile: str,
    port: int,
    marker: str,
    auth_token: str,
    ts: str,
    config_path: Path | None = None,
    good_fragment: str | None = None,
    bad_model_ref: str | None = None,
) -> SmokeResult:
    if not port_is_free(port):
        raise RuntimeError(f"Port déjà utilisé: {port}")

    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    base_url = f"http://127.0.0.1:{port}"

    health_db = MEMORY_DIR / f"provider_rotation_{safe_name}_{ts}.db"
    log_path = OUT_DIR / f"provider_rotation_{safe_name}_{ts}.log"
    response_path = OUT_DIR / f"provider_rotation_{safe_name}_{ts}.sse"
    status_before_path = OUT_DIR / f"provider_rotation_{safe_name}_status_before_{ts}.json"
    status_after_path = OUT_DIR / f"provider_rotation_{safe_name}_status_after_{ts}.json"
    health_json_path = OUT_DIR / f"provider_rotation_{safe_name}_health_{ts}.json"

    with launch_server(
        port=port,
        profile=profile,
        health_db=health_db,
        log_path=log_path,
        auth_token=auth_token,
        config_path=config_path,
    ) as process:
        print(f"SERVER_PID={process.pid}")
        print(f"LOG={log_path}")
        wait_for_server(base_url, auth_token, process, log_path)

        status_endpoint, status_before = fetch_rotation_status(base_url, auth_token)
        print(f"STATUS_ENDPOINT={status_endpoint}")
        write_json(status_before_path, status_before)

        actual_profile = status_before.get("profile")
        ring = status_before.get("ring") or {}
        candidates = ring.get("candidates") or []
        first_candidate = candidates[0] if candidates else {}

        print(f"STATUS_PROFILE_EXPECTED={profile}")
        print(f"STATUS_PROFILE_ACTUAL={actual_profile}")
        print(f"STATUS_PROFILE_MATCH={actual_profile == profile}")
        print(f"STATUS_CANDIDATE_COUNT={len(candidates)}")
        print(f"STATUS_FIRST_MODEL_REF={first_candidate.get('model_ref')}")
        print(f"STATUS_FIRST_PROVIDER={first_candidate.get('provider_id')}")
        print(f"STATUS_FIRST_PROVIDER_MODEL={first_candidate.get('provider_model')}")

        if actual_profile != profile:
            raise RuntimeError(f"Profil actif inattendu: expected={profile}, actual={actual_profile}")

        if bad_model_ref is not None:
            first_is_bad = first_candidate.get("model_ref") == bad_model_ref
            print(f"STATUS_FIRST_IS_BAD={first_is_bad}")
            if not first_is_bad:
                raise RuntimeError("La config temporaire n'a pas injecté le mauvais candidat en tête.")

        http_code, raw_response = call_messages(base_url, auth_token, marker)
        response_path.write_text(raw_response, encoding="utf-8", errors="replace")

        parsed = parse_sse(raw_response, marker)
        print(f"HTTP_CODE={http_code}")
        print(f"RESPONSE_FILE={response_path}")
        print(f"PARSED_MODEL={parsed['model']}")
        print(f"MARKER_EXPECTED={marker}")
        print(f"MARKER_FOUND={parsed['marker_found']}")
        print(f"TEXT_PREVIEW={parsed['text_preview']!r}")
        print(f"ERROR_EVENTS={parsed['error_events']!r}")

        _, status_after = fetch_rotation_status(base_url, auth_token)
        write_json(status_after_path, status_after)

        health = inspect_health_db(health_db, bad_model_ref=bad_model_ref, good_fragment=good_fragment)
        write_json(health_json_path, health)

        print(f"DB_PATH={health_db}")
        print(f"DB_EXISTS={health['db_exists']}")
        print("TABLES=" + ",".join(health.get("tables") or []))
        for key, value in (health.get("counts") or {}).items():
            print(f"{key}_COUNT={value}")

        good_fragment_found = True
        bad_model_exposed = False

        if good_fragment is not None:
            good_fragment_found = good_fragment in str(parsed["model"]) or good_fragment in raw_response
            print(f"GOOD_FRAGMENT_EXPECTED={good_fragment}")
            print(f"GOOD_FRAGMENT_FOUND={good_fragment_found}")

        if bad_model_ref is not None:
            bad_model_exposed = bad_model_ref in str(parsed["model"])
            print(f"BAD_MODEL_EXPOSED_IN_FINAL_MODEL={bad_model_exposed}")
            print(f"BAD_ROWS_COUNT={health['bad_rows_count']}")
            print(f"GOOD_ROWS_COUNT={health['good_rows_count']}")
            print(f"BAD_FAILURE_DETECTED={health['bad_failure_detected']}")
            print(f"GOOD_SUCCESS_DETECTED={health['good_success_detected']}")

    verdict = "OK"
    if http_code != 200:
        verdict = "FAIL"
    if not parsed["marker_found"]:
        verdict = "FAIL"
    if parsed["error_events"]:
        verdict = "FAIL"
    if good_fragment is not None and not good_fragment_found:
        verdict = "FAIL"
    if bad_model_ref is not None and bad_model_exposed:
        verdict = "FAIL"
    if bad_model_ref is not None and not health["bad_failure_detected"]:
        verdict = "FAIL"
    if good_fragment is not None and bad_model_ref is not None and not health["good_success_detected"]:
        verdict = "FAIL"

    print(f"SMOKE_VERDICT_{name}={verdict}")

    return SmokeResult(
        name=name,
        verdict=verdict,
        http_code=http_code,
        profile=profile,
        port=port,
        parsed_model=parsed["model"],
        marker_found=bool(parsed["marker_found"]),
        report_files={
            "log": str(log_path),
            "response_sse": str(response_path),
            "status_before": str(status_before_path),
            "status_after": str(status_after_path),
            "health_db": str(health_db),
            "health_json": str(health_json_path),
        },
        details={
            "marker": marker,
            "parsed": parsed,
            "health": health,
        },
    )


def make_temp_config(ts: str, ring_name: str, bad_model_ref: str, name: str) -> Path:
    data = load_model_rings()
    rings = data.get("rings") or {}

    if ring_name not in rings:
        raise RuntimeError(f"Ring introuvable: {ring_name}")

    candidates = rings[ring_name]
    if not candidates:
        raise RuntimeError(f"Ring vide: {ring_name}")

    bad_candidate = copy.deepcopy(candidates[0])
    if not isinstance(bad_candidate, dict):
        raise RuntimeError("Schéma candidat inattendu: candidat non-dict")

    bad_candidate["model_ref"] = bad_model_ref
    bad_candidate["priority"] = 999
    bad_candidate["weight"] = 1.0

    rings[ring_name] = [bad_candidate] + candidates

    tmp_dir = Path("/tmp") / f"cfc_provider_rotation_fallback_{ts}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    output = tmp_dir / f"model_rings_{name}.yaml"
    output.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    print(f"TEMP_CONFIG={output}")
    print(f"PATCHED_RING={ring_name}")
    print(f"BAD_MODEL_REF={bad_model_ref}")
    print(f"ORIGINAL_FIRST={candidates[0].get('model_ref') if isinstance(candidates[0], dict) else candidates[0]}")
    print(f"PATCHED_FIRST={bad_candidate['model_ref']}")
    print(f"PATCHED_RING_SIZE={len(rings[ring_name])}")

    return output


def run_runtime(auth_token: str, ts: str) -> list[SmokeResult]:
    print("=== RUNTIME SMOKE ===")
    assert_required_config(["stable-agentic"], ["code_agentic"])
    return [
        run_one_request(
            name="runtime_stable-agentic",
            profile="stable-agentic",
            port=18084,
            marker="OK_RUNTIME_ROTATION",
            auth_token=auth_token,
            ts=ts,
        )
    ]


def run_profiles(auth_token: str, ts: str) -> list[SmokeResult]:
    print("=== PROFILES SMOKE ===")
    assert_required_config(
        ["stable-agentic", "code-max", "fast-resilient", "long-context-docs"],
        ["code_agentic", "fast", "long_context"],
    )

    specs = [
        ("profile_stable-agentic", "stable-agentic", 18085, "OK_PROFILE_STABLE_AGENTIC"),
        ("profile_code-max", "code-max", 18086, "OK_PROFILE_CODE_MAX"),
        ("profile_fast-resilient", "fast-resilient", 18087, "OK_PROFILE_FAST_RESILIENT"),
        ("profile_long-context-docs", "long-context-docs", 18088, "OK_PROFILE_LONG_CONTEXT_DOCS"),
    ]

    return [
        run_one_request(
            name=name,
            profile=profile,
            port=port,
            marker=marker,
            auth_token=auth_token,
            ts=ts,
        )
        for name, profile, port, marker in specs
    ]


def run_fallback(auth_token: str, ts: str) -> list[SmokeResult]:
    print("=== FALLBACK SMOKE ===")
    assert_required_config(["stable-agentic", "fast-resilient"], ["code_agentic", "fast"])

    specs = [
        {
            "name": "fallback_stable-agentic",
            "profile": "stable-agentic",
            "port": 18089,
            "ring": "code_agentic",
            "bad_model_ref": "cloudflare/@cf/moonshotai/fallback-smoke-invalid-model",
            "marker": "OK_FALLBACK_STABLE_AGENTIC",
            "good_fragment": "@cf/moonshotai/kimi-k2.6",
        },
        {
            "name": "fallback_fast-resilient",
            "profile": "fast-resilient",
            "port": 18090,
            "ring": "fast",
            "bad_model_ref": "groq/fallback-smoke-invalid-model",
            "marker": "OK_FALLBACK_FAST_RESILIENT",
            "good_fragment": "llama-3.3-70b-versatile",
        },
    ]

    results: list[SmokeResult] = []
    for spec in specs:
        tmp_config = make_temp_config(ts, spec["ring"], spec["bad_model_ref"], spec["name"])
        results.append(
            run_one_request(
                name=spec["name"],
                profile=spec["profile"],
                port=spec["port"],
                marker=spec["marker"],
                auth_token=auth_token,
                ts=ts,
                config_path=tmp_config,
                good_fragment=spec["good_fragment"],
                bad_model_ref=spec["bad_model_ref"],
            )
        )

    return results


def print_summary(mode: str, results: list[SmokeResult], report_path: Path) -> None:
    ok = [item for item in results if item.verdict == "OK"]
    failed = [item for item in results if item.verdict != "OK"]

    print()
    print("================================================================================")
    print(f"=== SYNTHESE PROVIDER ROTATION SMOKE — MODE {mode} ===")
    print("================================================================================")
    print(f"SMOKE_MODE={mode}")
    print(f"SMOKE_TESTS={len(results)}")
    print(f"SMOKE_OK={len(ok)}")
    print(f"SMOKE_FAILED={len(failed)}")

    for result in results:
        print(
            f"SMOKE_RESULT name={result.name} profile={result.profile} "
            f"verdict={result.verdict} http={result.http_code} "
            f"port={result.port} model={result.parsed_model}"
        )

    success_marker = f"SMOKE_PROVIDER_ROTATION_{mode.upper()}_OK"
    print(f"{success_marker}={1 if not failed else 0}")
    print(f"REPORT={report_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reusable Provider Rotation smoke tests.")
    parser.add_argument(
        "mode",
        choices=("runtime", "profiles", "fallback", "all"),
        help="Smoke suite to run.",
    )
    parser.add_argument(
        "--auth-token",
        default=os.environ.get("ANTHROPIC_AUTH_TOKEN", "freecc"),
        help="Proxy auth token. Defaults to ANTHROPIC_AUTH_TOKEN or freecc. The value is not printed.",
    )
    args = parser.parse_args()

    ensure_dirs()

    ts = timestamp()
    print("=== PROVIDER ROTATION SMOKE RUNNER ===")
    print(f"PROJECT={PROJECT}")
    print(f"MODE={args.mode}")
    print(f"TIMESTAMP={ts}")

    results: list[SmokeResult] = []

    if args.mode in ("runtime", "all"):
        results.extend(run_runtime(args.auth_token, ts))

    if args.mode in ("profiles", "all"):
        results.extend(run_profiles(args.auth_token, ts))

    if args.mode in ("fallback", "all"):
        results.extend(run_fallback(args.auth_token, ts))

    summary_path = OUT_DIR / f"provider_rotation_smoke_{args.mode}_{ts}.json"
    report_path = OUT_DIR / f"provider_rotation_smoke_{args.mode}_{ts}.md"

    write_json(summary_path, [result.__dict__ for result in results])
    write_markdown_report(report_path, f"Provider Rotation smoke — {args.mode}", results)

    print_summary(args.mode, results, report_path)
    print(f"SUMMARY_JSON={summary_path}")

    return 0 if all(result.verdict == "OK" for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

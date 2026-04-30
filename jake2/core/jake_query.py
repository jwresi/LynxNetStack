#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from api.jake_api_server import run_server
from agents.ollama_client import OllamaClient
from core.context_builder import NetworkContextBuilder
from core.dispatch import IntentDispatcher
from core.intent_schema import IntentSchema
from core.shared import PROJECT_ROOT, seed_project_envs
from mcp.jake_ops_mcp import JakeOps


LAST_QUERY_PATH = PROJECT_ROOT / "output" / ".jake_last_query.json"
INTENT_EXAMPLES_PATH = PROJECT_ROOT / "data" / "intent_examples.jsonl"
INTENT_EXAMPLES_ARCHIVE_PATH = PROJECT_ROOT / "data" / "intent_examples_archive.jsonl"
MAX_CONFIRMED_EXAMPLES = 500


def _build_cli_synthesis_prompt(raw: str, execution: dict[str, Any]) -> str:
    result_payload = execution.get("result", {})
    rendered = json.dumps(result_payload, indent=2, default=str)[:2000]
    return (
        f'The operator asked: "{raw}"\n\n'
        f"Network data returned:\n{rendered}\n\n"
        "Write a 2-4 sentence direct answer that:\n"
        "- Answers the specific question asked\n"
        "- Uses real values from the data (device names, counts, site IDs, timestamps)\n"
        "- Flags anything that needs attention\n"
        "- Skips zero/empty fields unless zero IS the answer\n"
        "- Ends with 1-2 follow-up questions if something looks worth investigating\n\n"
        'Do not say "Based on the data" or "According to the results". Just answer directly as Jake.'
    )


def _retry_cli_synthesis(dispatcher: IntentDispatcher, raw: str, execution: dict[str, Any]) -> str | None:
    client = getattr(dispatcher.parser, "client", None)
    if client is None:
        return None
    retry_client = OllamaClient(client.endpoint, client.model, 20.0)

    prompts = [
        _build_cli_synthesis_prompt(raw, execution),
        (
            f'The operator asked: "{raw}"\n\n'
            f"Jake already has this deterministic answer:\n{execution.get('operator_summary') or execution.get('assistant_answer') or ''}\n\n"
            "Rewrite it as a short operator-facing answer in 2-3 sentences. "
            "Keep the real values, remove list formatting, and end with at most one useful follow-up question."
        ),
    ]
    for prompt in prompts:
        try:
            text = retry_client.generate(
                prompt,
                system_prompt=(
                    "You are Jake, a NOC assistant for a WISP. Be direct and specific. "
                    "Use real values. Do not hedge or pad. 3 sentences maximum."
                ),
            )
        except Exception:
            continue
        rendered = str(text or "").strip()
        if rendered:
            return rendered
    return None


def _cli_human_fallback(execution: dict[str, Any]) -> str | None:
    action = str(execution.get("matched_action") or "")
    result = execution.get("result") or {}

    def _as_int(value: Any) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return 0
        return 0

    if action == "get_site_summary" and isinstance(result, dict):
        site_id = result.get("site_id") or "unknown site"
        online_value = result.get("online_customers")
        if isinstance(online_value, dict):
            online_value = online_value.get("count") or online_value.get("online") or 0
        online = _as_int(online_value)
        outliers = _as_int(result.get("outlier_count") or 0)
        devices = _as_int(result.get("devices_total") or 0)
        scan = result.get("scan") or {}
        reachable = scan.get("reachable_hosts")
        attempted = scan.get("attempted_hosts")
        sentence_1 = f"Site {site_id} currently shows {online} online customers across {devices} tracked devices."
        if isinstance(reachable, int) and isinstance(attempted, int) and attempted > 0:
            sentence_2 = f"The latest scan saw {reachable} of {attempted} hosts reachable by API."
        else:
            sentence_2 = "The latest scan is present, but API reachability details are limited."
        if outliers > 0:
            sentence_3 = f"There are {outliers} outliers worth investigating."
        else:
            sentence_3 = "No active outliers are standing out right now."
        return " ".join((sentence_1, sentence_2, sentence_3))
    if action == "get_cpe_state":
        summary = str(execution.get("operator_summary") or "").strip()
        if summary:
            return summary.replace("\n", " ")
    return None


def _prefer_deterministic_cli_summary(execution: dict[str, Any]) -> bool:
    if execution.get("matched_action") == "get_cpe_state":
        bridge = (execution.get("result") or {}).get("bridge") or {}
        primary = bridge.get("primary_sighting") or {}
        port_name = str(primary.get("port_name") or primary.get("on_interface") or "").strip().lower()
        if port_name.startswith(("sfp-sfpplus", "sfp", "ether1", "bond", "bridge")):
            return True
    result = execution.get("result") or {}
    classifications = result.get("classifications") or []
    for row in classifications:
        kind = str(row.get("kind") or "")
        confidence = str(row.get("confidence") or "").lower()
        if confidence == "high" and kind in {"stuck_port_down", "dhcp_abnormal_rate"}:
            return True
    return False


def _cli_answer(payload) -> str:
    if payload.execution:
        if _prefer_deterministic_cli_summary(payload.execution):
            return payload.execution["operator_summary"]
        return (
            payload.synthesized_response
            or _cli_human_fallback(payload.execution)
            or payload.execution["operator_summary"]
        )
    return payload.response


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(payload, sort_keys=True)}\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def _append_jsonl(path: Path, payloads: list[dict[str, Any]]) -> None:
    if not payloads:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for payload in payloads:
            handle.write(json.dumps(payload, sort_keys=True))
            handle.write("\n")


def _build_last_query_payload(raw: str, intent: IntentSchema) -> dict[str, Any]:
    return {
        "raw": raw,
        "resolved_intent": intent.intent,
        "resolved_site": intent.entities.site_id,
        "confidence": float(intent.confidence),
        "timestamp": _utc_now_iso(),
    }


def save_last_query_result(
    raw: str,
    intent: IntentSchema,
    *,
    last_query_path: Path = LAST_QUERY_PATH,
) -> dict[str, Any]:
    payload = _build_last_query_payload(raw, intent)
    _dump_json(last_query_path, payload)
    return payload


def confirm_last_query(
    *,
    last_query_path: Path = LAST_QUERY_PATH,
    examples_path: Path = INTENT_EXAMPLES_PATH,
    archive_path: Path = INTENT_EXAMPLES_ARCHIVE_PATH,
    max_entries: int = MAX_CONFIRMED_EXAMPLES,
) -> dict[str, Any]:
    if not last_query_path.exists():
        raise RuntimeError("No previous Jake query result is available to confirm.")

    confirmed = dict(_read_json(last_query_path))
    confirmed["confirmed"] = True
    if "timestamp" not in confirmed:
        confirmed["timestamp"] = _utc_now_iso()

    records = _read_jsonl(examples_path)
    records.append(confirmed)
    overflow = max(0, len(records) - max_entries)
    if overflow:
        _append_jsonl(archive_path, records[:overflow])
        records = records[overflow:]

    examples_path.parent.mkdir(parents=True, exist_ok=True)
    examples_path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )
    return confirmed


def main() -> None:
    seed_project_envs(PROJECT_ROOT)
    parser = argparse.ArgumentParser(description="Jake understanding-layer query runner")
    parser.add_argument("query", nargs="*", help="Natural-language operator query")
    parser.add_argument("--confirm", action="store_true", help="Confirm the last successful Jake answer")
    parser.add_argument("--serve", action="store_true", help="Start the Jake WebUI API server")
    parser.add_argument("--port", type=int, default=8017, help="Port for Jake WebUI API server")
    parser.add_argument("--summary", action="store_true", help="Print only the operator summary")
    args = parser.parse_args()

    if args.confirm:
        if args.query or args.serve:
            parser.error("--confirm does not accept a query argument or --serve")
        confirmed = confirm_last_query()
        print(
            f"Saved confirmed example for intent {confirmed['resolved_intent']}"
            f" at site {confirmed['resolved_site'] or 'unknown'}."
        )
        return

    if args.serve:
        if args.query:
            parser.error("--serve does not accept a query argument")
        server = run_server(port=args.port)
        url = f"http://127.0.0.1:{args.port}"
        print(f"Jake WebUI running at {url}")
        try:
            subprocess.run(["open", url], check=False)
        except Exception:
            pass
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return

    if not args.query:
        parser.error("query is required unless --confirm or --serve is used")

    query = " ".join(args.query)
    context = None
    try:
        context = NetworkContextBuilder.build()
    except Exception:
        context = None
    dispatcher = IntentDispatcher(context=context)
    payload = dispatcher.dispatch(JakeOps(), query)
    if payload.execution and payload.synthesized_response is None:
        payload.synthesized_response = _retry_cli_synthesis(dispatcher, query, payload.execution)
    if payload.execution and payload.intent is not None:
        save_last_query_result(query, payload.intent)
    if args.summary:
        print(_cli_answer(payload))
        return
    if payload.execution:
        print(_cli_answer(payload))
        return
    print(
        json.dumps(
            {
                "status": payload.status,
                "response": payload.response,
                "classification": payload.classification,
                "intent": payload.intent.to_dict() if payload.intent else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

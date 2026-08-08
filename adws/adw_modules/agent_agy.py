"""Gemini / Antigravity (agy) coding agent interface for SSSF.

Runs `agy --output-format json --dangerously-skip-permissions --model <model> --effort <effort> -p`
and processes its JSON response for SSSF context handoffs and gates.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from .data_types import PiRequest, PiResult
from .utils import now_iso, operator_env


def _resolve_cli() -> str:
    override = os.environ.get("AGY_PATH")
    if override:
        return override
    found = shutil.which("agy")
    if found:
        return str(found)
    for fallback in [
        r"C:\Users\barth\.gemini\antigravity-cli\agy.exe",
        r"C:\claudeOS\Gemini\agy.exe",
    ]:
        if os.path.exists(fallback):
            return fallback
    return "agy"


AGY_PATH = _resolve_cli()
SESSION_NAMESPACE = uuid.UUID("7e8d4a1c-4b7e-5d28-9a04-2e8c7b2f0d64")

RESULT_SNIPPET_CHARS = 20_000
ARG_VALUE_CHARS = 20_000
LABEL_CHARS = 80

PRIMARY_ARGS = ("command", "file_path", "path", "pattern", "query", "url", "prompt")

EFFORT = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
    "none": "low",
    "off": "low",
}

KNOWN_MODELS = {
    "gemini-3.6-flash", "gemini-3.6-pro",
    "gemini-3.5-flash", "gemini-3.5-pro",
    "gemini-3.1-pro", "flash", "pro", "flash_lite",
}


def resolve_model(pattern: str) -> tuple[str, str]:
    name = pattern.split("/")[-1].strip().lower()
    if name in KNOWN_MODELS or "gemini" in name or name in ("flash", "pro"):
        return "google", name
    return "google", name


def context_window(provider: str, model_id: str) -> int:
    if "3.1-pro" in model_id or "pro" in model_id:
        return 2_000_000
    return 1_000_000


def session_uuid(session_key: str) -> str:
    return str(uuid.uuid5(SESSION_NAMESPACE, session_key))


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _label(tool: str, args: dict) -> str:
    value = next((args[key] for key in PRIMARY_ARGS
                  if isinstance(args.get(key), str) and args[key].strip()), "")
    if not value:
        value = next((v for v in args.values() if isinstance(v, str) and v.strip()), "")
    value = " ".join(str(value).split())
    return f"{tool}: {_clip(value, LABEL_CHARS)}" if value else tool


def _pi_shaped_usage(usage: dict) -> dict:
    return {
        "input": usage.get("input_tokens") or usage.get("prompt_tokens") or 0,
        "output": usage.get("output_tokens") or usage.get("completion_tokens") or 0,
        "cacheRead": usage.get("cache_read_tokens") or usage.get("cache_read_input_tokens") or 0,
        "cacheWrite": usage.get("cache_creation_tokens") or 0,
    }


def _context_tokens(usage: dict) -> int:
    return int(sum(usage.get(part) or 0 for part in
                   ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens", "total_tokens")))


class ToolCallTracker:
    def __init__(self) -> None:
        self._open: dict[str, dict] = {}

    def observe(self, event: dict) -> Optional[dict]:
        etype = event.get("type")
        if etype in ("tool_use", "call", "assistant"):
            call_id = str(event.get("id") or event.get("tool_use_id") or "")
            tool = str(event.get("name") or event.get("tool") or "tool")
            args = event.get("input") or event.get("args") or {}
            if call_id:
                self._open[call_id] = {
                    "tool": tool,
                    "args": args,
                    "started_at": now_iso(),
                    "clock": time.monotonic(),
                }
            return None

        if etype in ("tool_result", "result", "user"):
            call_id = str(event.get("tool_use_id") or event.get("id") or "")
            opened = self._open.pop(call_id, {})
            if not opened and not call_id:
                return None
            tool = str(opened.get("tool") or event.get("tool") or "tool")
            args = opened.get("args") or event.get("args") or {}
            record = {
                "tool": tool,
                "tool_call_id": call_id,
                "args": {key: _clip(value, ARG_VALUE_CHARS) if isinstance(value, str) else value
                         for key, value in args.items()},
                "ok": not event.get("is_error", False),
                "label": _label(tool, args),
                "ended_at": now_iso(),
            }
            if opened.get("clock"):
                record["duration_ms"] = int((time.monotonic() - opened["clock"]) * 1000)
            if opened.get("started_at"):
                record["started_at"] = opened["started_at"]
            return record
        return None


def _session_ledger(session_dir: Path) -> Path:
    return session_dir / "created_sessions.json"


def _is_new_session(session_dir: Path, key: str) -> bool:
    ledger = _session_ledger(session_dir)
    try:
        known = set(json.loads(ledger.read_text()))
    except (OSError, ValueError):
        known = set()
    return key not in known


def _record_session(session_dir: Path, key: str) -> None:
    ledger = _session_ledger(session_dir)
    try:
        known = set(json.loads(ledger.read_text()))
    except (OSError, ValueError):
        known = set()
    known.add(key)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(sorted(known), indent=2))


def run(request: PiRequest, on_event: Optional[Callable[[dict], None]] = None,
        on_spawn: Optional[Callable[[int], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None) -> PiResult:
    _, model_id = resolve_model(request.model)
    session_dir = Path(request.session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    agy_session = session_uuid(request.session_id)
    starting = _is_new_session(session_dir, request.session_id)

    # Place options BEFORE -p so Go flag parser handles flags properly
    cmd = [
        AGY_PATH,
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--model", model_id,
        "--effort", EFFORT.get(request.thinking, request.thinking),
    ]
    if starting:
        cmd += ["--conversation", agy_session]
    else:
        cmd += ["--conversation", agy_session, "--continue"]

    cmd += ["-p"]

    raw_path = Path(request.raw_output_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    result = PiResult(session_id=request.session_id,
                      context_window=context_window("google", model_id))

    full_prompt = request.prompt
    if request.system_prompt:
        try:
            sys_text = Path(request.system_prompt).read_text(encoding="utf-8")
            full_prompt = f"System Instructions:\n{sys_text}\n\nTask:\n{request.prompt}"
        except OSError:
            pass

    process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace",
                               bufsize=1, cwd=request.cwd,
                               env=operator_env())
    if on_spawn:
        on_spawn(process.pid)

    assert process.stdin is not None
    process.stdin.write(full_prompt)
    process.stdin.close()

    stdout_data, stderr_data = process.communicate()
    result.returncode = process.returncode
    if on_exit:
        on_exit(process.pid)

    with raw_path.open("a", encoding="utf-8") as raw:
        raw.write(stdout_data + "\n")

    stdout_clean = stdout_data.strip()
    if stdout_clean:
        try:
            parsed = json.loads(stdout_clean)
            if isinstance(parsed, dict):
                result.text = str(parsed.get("response") or parsed.get("result") or "")
                usage = parsed.get("usage") or {}
                turn = _context_tokens(usage)
                if turn:
                    result.tokens += turn
                    result.context_tokens = turn
                    result.usage.add_turn(_pi_shaped_usage(usage), turn)
                if on_event:
                    on_event(parsed)
            else:
                result.text = stdout_clean
        except json.JSONDecodeError:
            result.text = stdout_clean

    if starting and result.returncode == 0:
        _record_session(session_dir, request.session_id)

    if result.returncode != 0 and not result.text:
        raise RuntimeError(f"agy exited {result.returncode}: {stderr_data.strip()[-800:]}")
    return result

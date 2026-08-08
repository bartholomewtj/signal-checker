"""Gemini / Antigravity (agy) coding agent interface for SSSF.

Runs `agy --output-format stream-json --dangerously-skip-permissions --model
<model> --effort <effort> -p <prompt>` and tails its JSONL stdout line by
line, so events reach the tracer while the agent is still working — the same
contract agent_cc.py honours. Every stream line is an envelope of the shape
`{"event": <type>, <type>: {...}}`; the final `result` envelope carries the
response text and the authoritative usage totals.
"""

from __future__ import annotations

import json
import os
import re
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
# agy's print-mode wait defaults to 5m. With stream-json the CLI emits events
# as it works instead of buffering one blob, so the wait no longer races an
# entire thinking-heavy turn; 5m stays the default, override via env if a
# model legitimately needs longer between responses.
AGY_PRINT_TIMEOUT = os.environ.get("AGY_PRINT_TIMEOUT", "5m")
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
    # agy reports total_tokens alongside its components; summing components AND
    # the total would double-count, so prefer the total when it is present.
    total = usage.get("total_tokens")
    if total:
        return int(total)
    return int(sum(usage.get(part) or 0 for part in
                   ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens")))


def _extract_json_artifacts(text: str) -> list[str]:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = match.group(1) if match else text
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "artifacts" in data:
            return data.get("artifacts") or []
    except Exception:
        pass
    return []


def _ensure_artifacts(parsed_data: dict, full_text: str, cwd: str) -> None:
    artifacts = []
    if isinstance(parsed_data, dict):
        response_str = str(parsed_data.get("response") or "")
        artifacts = _extract_json_artifacts(response_str)
        if not artifacts and "artifacts" in parsed_data:
            artifacts = parsed_data.get("artifacts") or []

    for art in artifacts:
        if isinstance(art, str) and art.strip():
            art_path = Path(cwd) / art if not Path(art).is_absolute() else Path(art)
            if not art_path.exists():
                art_path.parent.mkdir(parents=True, exist_ok=True)
                art_path.write_text(full_text, encoding="utf-8")


# Step types that are conversation plumbing rather than tool work. Anything
# else a step reports doing is treated as tool activity and traced.
NON_TOOL_STEPS = {"user_input", "agent_response", "checkpoint", "planning",
                  "unknown", ""}


def _tool_details(step: dict, step_type: str) -> tuple[str, dict]:
    """Best-effort tool name and args for a step.

    agy does not document the tool payload inside step_update, so look under
    the likely keys and fall back to the step type itself — a lane dot labeled
    `run_command` with no args still beats five silent minutes.
    """
    for key in ("tool_call", "tool_use", "tool"):
        nested = step.get(key)
        if isinstance(nested, dict):
            tool = str(nested.get("name") or nested.get("tool") or step_type)
            args = nested.get("input") or nested.get("args") or {}
            return tool, args if isinstance(args, dict) else {}
    tool = str(step.get("tool_name") or step_type)
    args = {key: value for key, value in step.items()
            if key in PRIMARY_ARGS and isinstance(value, str)}
    return tool, args


class ToolCallTracker:
    """Derive tool_call records from agy's stream-json step updates.

    Every stream line arrives as `{"event": <type>, <type>: {...}}`. Tool
    activity rides `step_update` envelopes; a step may surface more than once
    as its state advances, so records are keyed by step_index, opened on first
    sighting, and emitted exactly once — when the step reports DONE.
    """

    def __init__(self) -> None:
        self._open: dict[int, dict] = {}
        self._done: set[int] = set()

    def observe(self, event: dict) -> Optional[dict]:
        step = event.get("step_update")
        if not isinstance(step, dict):
            return None

        index = step.get("step_index")
        step_type = str(step.get("step_type") or "")
        if index is None or step_type in NON_TOOL_STEPS:
            return None

        if index not in self._open:
            self._open[index] = {"started_at": now_iso(),
                                 "clock": time.monotonic()}
        state = str(step.get("state") or "").upper()
        if state != "DONE" or index in self._done:
            return None
        self._done.add(index)
        opened = self._open.pop(index)

        tool, args = _tool_details(step, step_type)
        record = {
            "tool": tool,
            "tool_call_id": f"step-{index}",
            "args": {key: _clip(value, ARG_VALUE_CHARS) if isinstance(value, str) else value
                     for key, value in args.items()},
            "ok": not step.get("is_error", False),
            "label": _label(tool, args),
            "started_at": opened["started_at"],
            "ended_at": now_iso(),
        }
        duration = step.get("duration_seconds")
        if isinstance(duration, (int, float)):
            record["duration_ms"] = int(duration * 1000)
        else:
            record["duration_ms"] = int((time.monotonic() - opened["clock"]) * 1000)
        return record


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

    full_prompt = request.prompt
    if request.system_prompt:
        try:
            sys_text = Path(request.system_prompt).read_text(encoding="utf-8")
            full_prompt = f"System Instructions:\n{sys_text}\n\nTask:\n{request.prompt}"
        except OSError:
            pass

    cmd = [
        AGY_PATH,
        "--output-format", "stream-json",
        "--dangerously-skip-permissions",
        "--model", model_id,
        "--effort", EFFORT.get(request.thinking, request.thinking),
        "--print-timeout", AGY_PRINT_TIMEOUT,
    ]
    if starting:
        cmd += ["--conversation", agy_session]
    else:
        cmd += ["--conversation", agy_session, "--continue"]

    cmd += ["-p", full_prompt]

    raw_path = Path(request.raw_output_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    result = PiResult(session_id=request.session_id,
                      context_window=context_window("google", model_id))

    # encoding pinned for the same reason as agent_cc: Windows decodes pipes
    # with the locale code page unless told otherwise, and one bad byte would
    # kill an otherwise healthy stream. bufsize=1 keeps it line-buffered.
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace",
                               bufsize=1, cwd=request.cwd, env=operator_env())
    if on_spawn:
        on_spawn(process.pid)

    final: dict = {}
    with raw_path.open("a", encoding="utf-8") as raw:
        assert process.stdout is not None
        for line in process.stdout:
            raw.write(line)
            raw.flush()                      # events land on disk as they happen
            line = line.strip()
            if not line:
                continue
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(envelope, dict):
                continue

            etype = envelope.get("event")
            if etype == "step_update":
                usage = (envelope.get("step_update") or {}).get("usage") or {}
                turn = _context_tokens(usage)
                if turn:
                    result.tokens += turn
                    result.context_tokens = turn
                    result.usage.add_turn(_pi_shaped_usage(usage), turn)
            elif etype == "result":
                final = envelope.get("result") or {}

            if on_event:
                on_event(envelope)

    stderr_data = process.stderr.read() if process.stderr else ""
    result.returncode = process.wait()
    if on_exit:
        on_exit(process.pid)

    if final:
        resp = str(final.get("response") or "")
        if resp:
            result.text = resp
        _ensure_artifacts(final, resp, request.cwd)
        # Steps already carried their own usage; the final totals are only a
        # fallback for a stream that reported none, never added on top.
        if not result.tokens:
            usage = final.get("usage") or {}
            turn = _context_tokens(usage)
            if turn:
                result.tokens += turn
                result.context_tokens = turn
                result.usage.add_turn(_pi_shaped_usage(usage), turn)

    if starting and result.returncode == 0:
        _record_session(session_dir, request.session_id)

    if result.returncode != 0 and not result.text:
        raise RuntimeError(f"agy exited {result.returncode}: {stderr_data.strip()[-800:]}")
    return result

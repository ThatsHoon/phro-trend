"""Set the reader's interests for one project folder from its recent documents and Claude Code sessions.

  python interest.py gather --project P [--days 14] [--claude-dir D]
  python interest.py save --project P [--home H] FILE|-
  python interest.py show --project P [--home H]
Session records: only the person's own prompts, titles and compaction summaries are read; tool output never is.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home() / ".claude" / "phro-trend"
CLAUDE_DIR = Path(os.environ["CLAUDE_CONFIG_DIR"]) if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude"
DAYS = 14
PROMPT_CHARS = 160
PROMPTS_PER_SESSION = 8
SUMMARY_CHARS = 600
TAG_BLOCK = re.compile(r"<([A-Za-z][\w-]*)\b[^>]*>.*?</\1>", re.S)  # system reminders, notifications, pasted text
COMMAND = re.compile(r"<command-name>(.*?)</command-name>", re.S)
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def project_key(project) -> str:
    return os.path.normcase(str(Path(project).resolve()))


def _under(path: str, project: Path) -> bool:
    child, root = project_key(path), project_key(project)
    return child == root or child.startswith(root.rstrip(os.sep) + os.sep)


def clean_prompt(text: str) -> str:
    cmd = COMMAND.search(text)
    if cmd:
        args = COMMAND_ARGS.search(text)
        text = cmd.group(1) + (" " + args.group(1) if args else "")
    else:
        text = TAG_BLOCK.sub(" ", text)
    return " ".join(text.split())[:PROMPT_CHARS]


def _stamp(value) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _summary_head(text: str) -> str:
    m = re.search(r"^Summary:\s*$", text, re.M)
    return (text[m.end():] if m else text).strip()[:SUMMARY_CHARS]


def _records(claude_dir: Path, project: Path, since: datetime) -> list[tuple[float, Path, bool]]:
    """Top-level records of P's session folders touched inside the window, newest first.

    Claude Code names a folder after the start path with every non-alphanumeric character as "-";
    a subfolder's name extends it. The bool says the folder is P's own, not a subfolder or a lookalike.
    """
    base = os.path.normcase(re.sub(r"[^A-Za-z0-9]", "-", str(Path(project).resolve())))
    found = []
    for d in (Path(claude_dir) / "projects").glob("*"):
        name = os.path.normcase(d.name)
        if not d.is_dir() or not (name == base or name.startswith(base + "-")):
            continue
        for f in d.glob("*.jsonl"):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if mtime >= since.timestamp():
                found.append((mtime, f, name == base))
    return sorted(found, key=lambda x: -x[0])


def _read(path: Path, project: Path, exact: bool, since: datetime, seen: set) -> tuple[dict | None, int]:
    """One record's title, newest prompts and latest summary; None when it belongs to another folder."""
    title, summary, summary_at, prompts, cwd, skipped = "", "", None, [], None, 0
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None, 1
    with fh:
        for line in fh:
            need_cwd = cwd is None and '"cwd":"' in line
            wanted = ('"custom-title"' in line or '"isCompactSummary":true' in line
                      or ('"type":"user"' in line and '"tool_result"' not in line))
            if not (need_cwd or wanted):
                continue
            try:
                e = json.loads(line)
            except ValueError:
                skipped += 1
                continue
            if need_cwd and e.get("cwd"):
                cwd = e["cwd"]
                if not _under(cwd, project):
                    return None, skipped
            if not wanted:
                continue
            if e.get("type") == "custom-title":
                title = e.get("customTitle") or title
                continue
            when = _stamp(e.get("timestamp"))
            if e.get("type") != "user" or e.get("isSidechain") or when is None or when < since:
                continue
            uid = e.get("uuid")
            if uid in seen:
                continue
            text = _text((e.get("message") or {}).get("content"))
            if e.get("isCompactSummary"):
                if summary_at is None or when >= summary_at:
                    summary, summary_at = _summary_head(text), when
            elif not e.get("isMeta"):
                prompt = clean_prompt(text)
                if prompt:
                    prompts.append((when, prompt))
            if uid:
                seen.add(uid)
    if cwd is None and not exact:
        return None, skipped
    prompts.sort(key=lambda x: x[0], reverse=True)
    return {"title": title, "prompts": [p for _, p in prompts[:PROMPTS_PER_SESSION]], "summary": summary}, skipped


def sessions(claude_dir: Path, project: Path, since: datetime) -> tuple[list[dict], int]:
    out, skipped, seen = [], 0, set()
    for mtime, path, exact in _records(claude_dir, project, since):
        s, bad = _read(path, project, exact, since, seen)
        skipped += bad
        if s is not None:
            s["last"] = datetime.fromtimestamp(mtime, timezone.utc)
            out.append(s)
    return out, skipped

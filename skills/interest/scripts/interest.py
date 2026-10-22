"""Set the reader's interests for one project folder from its recent documents and Claude Code sessions.

  python interest.py gather --project P [--days 14] [--claude-dir D]
  python interest.py save --project P [--home H] FILE|-
  python interest.py show --project P [--home H]
Session records: only the person's own prompts, titles and compaction summaries are read; tool output never is.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home() / ".claude" / "phro-trend"
CLAUDE_DIR = Path(os.environ["CLAUDE_CONFIG_DIR"]) if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude"
DAYS = 14
PROMPT_CHARS = 160
PROMPTS_PER_SESSION = 8
SUMMARY_CHARS = 600
SESSION_BUDGET = 7000
DOC_BUDGET = 3000
BUDGET = SESSION_BUDGET + DOC_BUDGET
DOC_LIMIT = 60
FOLD_AT = 20  # a folder with more matching files is a data dump: one line, contents unread
MAX_DOC_BYTES = 2_000_000
SKIP_DIRS = {"node_modules", "__pycache__", "venv", "trend-weekly", "trend-papers"}
TEXT_DOCS = {".md", ".rst", ".html", ".htm"}
PATH_DOCS = {".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".hwp"}
NL = chr(10)
HTML_HEADS = re.compile(r"<(title|h[1-3])\b[^>]*>(.*?)</\1>", re.S | re.I)
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


def _headings(path: Path) -> list[str] | None:
    """Title and the first headings; None for a page phro-trend wrote itself."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".html", ".htm"):
        if 'name="phro-kind"' in text:
            return None
        heads = [re.sub(r"<[^>]+>", " ", m.group(2)) for m in HTML_HEADS.finditer(text)]
    else:
        heads = [line.lstrip("#") for line in text.splitlines() if line.startswith("#")]
    return [" ".join(h.split()) for h in heads if h.strip()][:3]


def documents(project: Path, since: datetime) -> tuple[list[str], int]:
    project = Path(project).resolve()
    found, skipped = [], 0
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
        here = []
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() not in TEXT_DOCS | PATH_DOCS:
                continue
            try:
                st = path.stat()
            except OSError:
                skipped += 1
                continue
            if st.st_mtime >= since.timestamp() and st.st_size <= MAX_DOC_BYTES:
                here.append((st.st_mtime, path))
        if len(here) > FOLD_AT:
            folder = Path(root).relative_to(project).as_posix()
            found.append((max(m for m, _ in here), f"{folder}/ ({len(here)} files)"))
            continue
        for mtime, path in here:
            rel = path.relative_to(project).as_posix()
            if path.suffix.lower() in TEXT_DOCS:
                try:
                    heads = _headings(path)
                except OSError:
                    skipped += 1
                    continue
                if heads is None:
                    continue
                rel = f"{rel}: {'; '.join(heads)}" if heads else rel
            found.append((mtime, rel))
    found.sort(key=lambda x: -x[0])
    return [line for _, line in found[:DOC_LIMIT]], skipped


def render(sessions: list[dict], docs: list[str]) -> str:
    """Sessions share SESSION_BUDGET equally (summary at most half of a share), documents get DOC_BUDGET."""
    parts = []
    if sessions:
        share = SESSION_BUDGET // len(sessions) - 2
        for s in sessions:
            block = f"## {s['title'] or '(untitled)'} ({s['last']:%Y-%m-%d})"
            if s["summary"]:
                block += NL + s["summary"][: share // 2]
            for prompt in s["prompts"]:
                if len(block) + len(prompt) + 3 > share:
                    break
                block += NL + "- " + prompt
            parts.append(block[:share])
    if docs:
        block = "## Documents"
        for line in docs:
            if len(block) + len(line) + 1 > DOC_BUDGET:
                break
            block += NL + line
        parts.append(block)
    return (NL * 2).join(parts)[:BUDGET]


def gather(project: Path, claude_dir: Path = CLAUDE_DIR, days: int = DAYS, now: datetime | None = None) -> tuple[str, str]:
    since = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    found, bad = sessions(claude_dir, project, since)
    docs, bad_docs = documents(project, since)
    text = render(found, docs)
    count = (f"sessions {len(found)}, prompts {sum(len(s['prompts']) for s in found)}, documents {len(docs)}, "
             f"skipped {bad + bad_docs}, {len(text)} chars")
    return text, count


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="interest.py", description="phro-trend interests for one project folder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gather", help="print the input for writing interests")
    g.add_argument("--project", required=True, help="the folder the session started in")
    g.add_argument("--days", type=int, default=DAYS)
    g.add_argument("--claude-dir", default=str(CLAUDE_DIR))
    args = ap.parse_args(argv)
    text, count = gather(Path(args.project), Path(args.claude_dir), args.days)
    if text:
        print(text)
    print(count)
    return 0 if text else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

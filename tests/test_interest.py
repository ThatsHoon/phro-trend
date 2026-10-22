import contextlib, io, json, os, re, tempfile, time, unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from tests._load import load

i = load("skills/interest/scripts/interest.py")
NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=14)


def ts(days_ago=1.0, minutes=0):
    return (NOW - timedelta(days=days_ago, minutes=minutes)).isoformat().replace("+00:00", "Z")


def user(text, uid, when=None, **flags):
    return {"type": "user", "uuid": uid, "timestamp": when or ts(), "message": {"role": "user", "content": text}, **flags}


def title(t):
    return {"type": "custom-title", "customTitle": t, "sessionId": "s"}


def folder(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.project = root / "proj"
        (self.project / "sub").mkdir(parents=True)
        self.claude = root / "claude"

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, name, entries, cwd="project", dirname=None, raw=b""):
        """Write one compact-JSON record the way Claude Code does; cwd goes on every entry unless None."""
        d = self.claude / "projects" / (dirname or folder(self.project))
        d.mkdir(parents=True, exist_ok=True)
        where = str(self.project) if cwd == "project" else cwd
        lines = [json.dumps(dict(e, cwd=where) if where else e, ensure_ascii=False, separators=(",", ":")) for e in entries]
        path = d / f"{name}.jsonl"
        path.write_bytes(("\n".join(lines) + "\n").encode("utf-8") + raw)
        return path

    def titles(self):
        return {s["title"] for s in i.sessions(self.claude, self.project, SINCE)[0]}


class SessionTest(Base):
    def test_clean_prompt(self):
        self.assertEqual(i.clean_prompt("<system-reminder>x</system-reminder>hello"), "hello")
        self.assertEqual(i.clean_prompt('<pasted_content id="a">secret</pasted_content> do it'), "do it")
        self.assertEqual(i.clean_prompt("<command-name>/phro-trend:weekly</command-name><command-args>LoRA</command-args>"),
                         "/phro-trend:weekly LoRA")
        self.assertEqual(i.clean_prompt("a" * 300), "a" * 160)
        self.assertEqual(i.clean_prompt("<task-notification>x</task-notification>"), "")

    def test_reads_title_prompts_and_summary(self):
        prompts = [user(f"p{n:02d}", f"u{n}", ts(1, 100 - n)) for n in range(1, 11)]
        tool = {"type": "user", "uuid": "t1", "timestamp": ts(), "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "x", "content": "TOOL OUTPUT"}]}}
        summary = user("This session is being continued.\n\nSummary:\n1. Primary Request and Intent:\n" + "x" * 1000,
                       "c1", isCompactSummary=True)
        self.record("s1", [title("old")] + prompts + [tool, user("META", "m1", isMeta=True),
                                                     user("SIDE", "d1", isSidechain=True), summary, title("new")])
        (s,), skipped = i.sessions(self.claude, self.project, SINCE)
        self.assertEqual(s["title"], "new")
        self.assertEqual(s["prompts"], [f"p{n:02d}" for n in range(10, 2, -1)])
        self.assertTrue(s["summary"].startswith("1. Primary Request"))
        self.assertLessEqual(len(s["summary"]), 600)
        dump = json.dumps(s, default=str)
        for word in ("TOOL OUTPUT", "META", "SIDE"):
            self.assertNotIn(word, dump)
        self.assertEqual(skipped, 0)

    def test_window_and_fork_dedupe(self):
        shared = user("recent", "u1")
        self.record("a", [shared, user("ancient", "u2", ts(20))])
        fork = self.record("b", [shared, user("forked", "u3")])
        os.utime(fork, (time.time() + 60, time.time() + 60))  # the fork is the newer record
        got = sorted(p for s in i.sessions(self.claude, self.project, SINCE)[0] for p in s["prompts"])
        self.assertEqual(got, ["forked", "recent"])

    def test_subfolder_and_lookalike(self):
        self.record("m", [title("main")])
        self.record("s", [title("sub")], cwd=str(self.project / "sub"), dirname=folder(self.project / "sub"))
        lookalike = Path(str(self.project) + "-old")
        self.record("o", [title("old-proj")], cwd=str(lookalike), dirname=folder(lookalike))
        self.assertEqual(self.titles(), {"main", "sub"})

    def test_broken_lines_and_bad_bytes(self):
        bad = ('{"type":"user","uuid":"u9","timestamp":"%s","message":{"role":"user","content":"bad ' % ts()).encode()
        self.record("b", [user("good", "u1")],
                    raw=b'{"type":"user", broken\n' + bad + b'\xff\xfe bytes"}}\n')
        (s,), skipped = i.sessions(self.claude, self.project, SINCE)
        self.assertIn("good", s["prompts"])
        self.assertTrue(any(p.startswith("bad ") for p in s["prompts"]))
        self.assertGreaterEqual(skipped, 1)

    def test_record_without_cwd(self):
        self.record("plain", [title("plain")], cwd=None)
        self.record("stray", [title("stray")], cwd=None, dirname=folder(self.project) + "-old")
        self.assertEqual(self.titles(), {"plain"})

    def test_subagents_ignored(self):
        self.record("main", [title("main")])
        nested = self.claude / "projects" / folder(self.project) / "main" / "subagents"
        nested.mkdir(parents=True)
        (nested / "a.jsonl").write_text(json.dumps(title("agent"), separators=(",", ":")) + "\n", encoding="utf-8")
        self.assertEqual(self.titles(), {"main"})

    def test_old_record_skipped_by_mtime(self):
        old = self.record("old", [title("old")])
        os.utime(old, (SINCE.timestamp() - 3600, SINCE.timestamp() - 3600))
        self.assertEqual(self.titles(), set())

    @unittest.skipUnless(os.name == "nt", "Windows paths")
    def test_path_spelling(self):
        self.record("m", [title("main"), user("hello", "u1")])
        upper = Path(str(self.project).upper().replace("\\", "/"))
        self.assertEqual(i.sessions(self.claude, upper, SINCE)[0], i.sessions(self.claude, self.project, SINCE)[0])


def fake_session(n):
    return {"title": f"session {n}", "last": NOW, "prompts": ["p" * 160] * 8, "summary": "s" * 600}


class GatherTest(Base):
    def write(self, rel, text="", age_days=0, size=None):
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size if size else text.encode("utf-8"))
        when = time.time() - age_days * 86400
        os.utime(path, (when, when))
        return path

    def lines(self):
        return i.documents(self.project, datetime.now(timezone.utc) - timedelta(days=14))[0]

    def test_doc_lines(self):
        self.write("a.md", chr(10).join(["# Title", "## Part", "### Sub", "## Four", ""]))
        self.write("b.html", "<html><head><title>T</title></head><body><h1>H</h1></body></html>")
        self.write("c.pdf", "%PDF")
        lines = self.lines()
        self.assertIn("a.md: Title; Part; Sub", lines)
        self.assertIn("b.html: T; H", lines)
        self.assertIn("c.pdf", lines)

    def test_doc_exclusions(self):
        for rel in (".git/x.md", "node_modules/x.md", "__pycache__/x.md", "venv/x.md", "trend-weekly/x.html", "trend-papers/x.html"):
            self.write(rel, "# hidden")
        self.write("page.html", '<html><head><meta name="phro-kind" content="weekly"><title>W</title></head></html>')
        self.write("old.md", "# old", age_days=30)
        self.write("big.md", size=3_000_000)
        self.write("notes.py", "# not a document")
        self.assertEqual(self.lines(), [])

    def test_folder_folding(self):
        for n in range(25):
            self.write(f"data/{n}.txt", "row")
        self.assertEqual(self.lines(), ["data/ (25 files)"])

    def test_doc_limit_newest_first(self):
        for n in range(70):
            self.write(f"d{n // 10}/f{n % 10}.md", f"# T{n}", age_days=(70 - n) / 1000)
        lines = self.lines()
        self.assertEqual(len(lines), 60)
        self.assertEqual(lines[0], "d6/f9.md: T69")

    def test_render_budget(self):
        text = i.render([fake_session(n) for n in range(12)], [f"doc{n}.md: " + "x" * 200 for n in range(100)])
        self.assertLessEqual(len(text), 10_000)
        self.assertTrue(all(f"## session {n} (" in text for n in range(12)))
        self.assertIn("- " + "p" * 20, text)  # prompts survive a long summary
        self.assertIn("doc0.md", text)

    def test_gather_exit_codes(self):
        empty = self.project.parent / "empty"
        empty.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(i.main(["gather", "--project", str(empty), "--claude-dir", str(self.claude)]), 1)
        self.write("a.md", "# A")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(i.main(["gather", "--project", str(self.project), "--claude-dir", str(self.claude)]), 0)
        last = out.getvalue().splitlines()[-1]
        self.assertTrue(last.startswith("sessions 0, prompts 0, documents 1, skipped 0, "), last)


KST = timezone(timedelta(hours=9))
FIVE = {"interests": [{"topic": f"주제 {n}", "keywords": [f"kw{n}", "Whisper"], "why": "최근 세션 작업"} for n in range(5)]}


def with_interest(**change):
    data = json.loads(json.dumps(FIVE))
    data["interests"][0].update(change)
    return data


class StoreTest(Base):
    def setUp(self):
        super().setUp()
        self.home = self.project.parent / "home"

    def test_iso_week(self):
        self.assertEqual(i.iso_week(date(2026, 10, 22)), "2026-W43")
        self.assertEqual(i.iso_week(date(2027, 1, 1)), "2026-W53")

    def test_save_then_show_current(self):
        i.save(self.project, FIVE, self.home, now=datetime(2026, 10, 22, 9, tzinfo=KST))
        text = i.show(self.project, self.home, today=date(2026, 10, 24))
        self.assertTrue(text.startswith("interests 2026-W43 (current, updated 2026-10-22)"), text)
        self.assertIn("1. 주제 0 [kw0, Whisper]", text)

    def test_show_refresh_due(self):
        self.assertEqual(i.show(self.project, self.home, today=date(2026, 10, 22)), "refresh due: no interests for this folder")
        self.home.mkdir()
        (self.home / "interests.json").write_text(json.dumps({i.project_key(self.project): {
            "week": "2026-W42", "updated": "2026-10-15T09:00:00+09:00", "interests": FIVE["interests"]}}), encoding="utf-8")
        self.assertEqual(i.show(self.project, self.home, today=date(2026, 10, 22)), "refresh due: stored 2026-W42, now 2026-W43")

    def test_invalid_rejected(self):
        cases = (({"interests": FIVE["interests"][:4]}, "5 to 8"), (with_interest(keywords=["", "x"]), "keyword"),
                 (with_interest(topic="가" * 41), "topic"), (with_interest(keywords=["AI", "LLM"]), "generic"),
                 (with_interest(why="w" * 121), "why"))
        for bad, word in cases:
            with self.assertRaises(ValueError) as cm:
                i.save(self.project, bad, self.home)
            self.assertIn(word, str(cm.exception))
        self.assertFalse((self.home / "interests.json").exists())

    def test_broken_store_kept(self):
        self.home.mkdir()
        (self.home / "interests.json").write_text("{oops", encoding="utf-8")
        with self.assertRaises(ValueError):
            i.save(self.project, FIVE, self.home)
        self.assertEqual((self.home / "interests.json").read_text(encoding="utf-8"), "{oops")
        self.assertTrue(i.show(self.project, self.home).startswith("warning:"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(i.main(["show", "--project", str(self.project), "--home", str(self.home)]), 1)

    def test_cli_save_from_stdin(self):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(FIVE))), contextlib.redirect_stdout(out):
            self.assertEqual(i.main(["save", "--project", str(self.project), "--home", str(self.home), "-"]), 0)
        self.assertTrue(i.show(self.project, self.home).startswith("interests "))
        with mock.patch("sys.stdin", io.StringIO("not json")), contextlib.redirect_stdout(out):
            self.assertEqual(i.main(["save", "--project", str(self.project), "--home", str(self.home), "-"]), 1)

    @unittest.skipUnless(os.name == "nt", "Windows paths")
    def test_store_key_ignores_spelling(self):
        i.save(self.project, FIVE, self.home)
        upper = Path(str(self.project).upper().replace("\\", "/"))
        self.assertTrue(i.show(upper, self.home).startswith("interests "))


if __name__ == "__main__":
    unittest.main()

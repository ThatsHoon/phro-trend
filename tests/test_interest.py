import json, os, re, tempfile, time, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
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


class SessionTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

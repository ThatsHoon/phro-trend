import json, os, subprocess, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tests._load import load

w = load("skills/weekly/scripts/weekly.py")
KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 22, 9, tzinfo=KST)
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>One</title><link href="https://news.hada.io/topic?id=1"/><published>2026-10-22T00:00:00Z</published><content type="html">&lt;p&gt;first&lt;/p&gt;</content></entry>
<entry><title>Two</title><link href="https://news.hada.io/topic?id=2"/><published>2026-10-21T20:00:00Z</published><content type="html">&lt;p&gt;second&lt;/p&gt;</content></entry>
</feed>"""


def get(url, headers=None):
    return ATOM


def failing_get(url, headers=None):
    raise w.FetchError("요청 제한(429)")


class PullTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pull_appends_only_new(self):
        home = self.home
        self.assertEqual(w.pull(home, get, NOW), {"geeknews": 2, "arxiv-eess-AS": 2})
        self.assertEqual(w.pull(home, get, NOW + timedelta(hours=12)), {"geeknews": 0, "arxiv-eess-AS": 0})
        lines = (home / "pull" / "geeknews.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["content"], "first")
        self.assertEqual(len(w.pull_times(home, "geeknews")), 2)

    def test_pull_failure_logged(self):
        self.assertEqual(w.pull(self.home, failing_get, NOW)["geeknews"], -1)
        self.assertIn("429", (self.home / "pull" / "log.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(w.pull_times(self.home, "geeknews"), [])

    def test_prune(self):
        (self.home / "pull").mkdir()
        old = {"title": "old-item", "link": "https://news.hada.io/topic?id=0", "date": (NOW - timedelta(days=121)).isoformat()}
        (self.home / "pull" / "geeknews.jsonl").write_text(json.dumps(old) + "\n", encoding="utf-8")
        w.pull(self.home, get, NOW)
        self.assertNotIn("old-item", (self.home / "pull" / "geeknews.jsonl").read_text(encoding="utf-8"))

    def test_gaps(self):
        start, end = w.week_bounds("2026-W42", KST)
        every12 = [start + timedelta(hours=9 + 12 * i) for i in range(15)]  # Monday 09:00 to next Monday 09:00
        self.assertEqual(w.gaps(every12, start, end), [])
        hole = [t for t in every12 if not (start + timedelta(days=2, hours=9) < t < start + timedelta(days=4, hours=9))]
        self.assertEqual(w.gaps(hole, start, end), [(start + timedelta(days=2, hours=9), start + timedelta(days=3, hours=3))])
        self.assertEqual(w.gaps([], start, end), [(start, end)])

    def test_launcher_runs_newest_install_that_has_weekly(self):
        user, marker = self.home / "user", self.home / "ran.txt"
        cache = user / ".claude" / "plugins" / "cache" / "phro" / "phro-trend"
        (cache / "0.1.1" / "skills" / "ai").mkdir(parents=True)  # an install from before the weekly skill

        def plant(root, tag):
            script = root / "skills" / "weekly" / "scripts" / "weekly.py"
            script.parent.mkdir(parents=True)
            script.write_text(f"import pathlib, sys; pathlib.Path({str(marker)!r}).write_text({tag!r} + ' ' + sys.argv[1], "
                              "encoding='utf-8')", encoding="utf-8")

        plant(self.home / "plug", "fallback")
        w.schedule(self.home, sys.executable, self.home / "plug", platform="nt")
        env = dict(os.environ, HOME=str(user), USERPROFILE=str(user))
        run = lambda: subprocess.run([sys.executable, "-I", str(self.home / "pull_launcher.py")], env=env).returncode
        self.assertEqual(run(), 0)
        self.assertEqual(marker.read_text(encoding="utf-8"), "fallback pull")
        plant(cache / "0.2.0", "cache")
        self.assertEqual(run(), 0)
        self.assertEqual(marker.read_text(encoding="utf-8"), "cache pull")

    def test_schedule_writes_launcher(self):
        cmd = w.schedule(self.home, sys.executable, Path("C:/plug"), platform="nt")
        self.assertIn("Register-ScheduledTask", cmd)
        self.assertIn("StartWhenAvailable", cmd)
        self.assertIn("09:00", cmd)
        self.assertIn("21:00", cmd)
        self.assertIn(r"C:/plug", (self.home / "pull_launcher.py").read_text(encoding="utf-8"))
        self.assertIn("crontab", w.schedule(self.home, "/usr/bin/python3", Path("/p"), platform="posix"))

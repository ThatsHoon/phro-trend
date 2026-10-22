import json, tempfile, unittest
from pathlib import Path
from tests._load import load
from tests._samples import weekly_page

w = load("skills/weekly/scripts/weekly.py")


class MarkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_mark_and_idempotent(self):
        f = self.dir / "2026-W42.html"
        f.write_text(weekly_page(), encoding="utf-8")
        rec = self.dir / "weekly.json"
        self.assertEqual(w.mark(f, rec), 7)  # 3 top stories + 2 themes x 2 brief items
        w.mark(f, rec)
        data = json.loads(rec.read_text(encoding="utf-8"))
        self.assertEqual(list(data), ["2026-W42"])
        stories = data["2026-W42"]["stories"]
        self.assertEqual(len(stories), 7)
        self.assertEqual({s["kind"] for s in stories}, {"top", "brief"})
        self.assertEqual((stories[0]["id"], stories[0]["title"], stories[0]["url"], stories[0]["stage"], stories[0]["label"]),
                         ("2610.00001", "① 결과 문장 1", "https://huggingface.co/papers/2610.00001", "학습", "시험해 볼 것"))
        self.assertEqual((stories[3]["title"], stories[3]["url"]), ("짧은 결과 0-0.", "https://example.com/0/0"))

    def test_other_weeks_kept(self):
        f = self.dir / "2026-W42.html"
        f.write_text(weekly_page(), encoding="utf-8")
        rec = self.dir / "weekly.json"
        rec.write_text('{"2026-W41": {"stories": []}}', encoding="utf-8")
        w.mark(f, rec)
        self.assertEqual(sorted(json.loads(rec.read_text(encoding="utf-8"))), ["2026-W41", "2026-W42"])

    def test_corrupt_record_is_not_overwritten(self):
        f = self.dir / "2026-W42.html"
        f.write_text(weekly_page(), encoding="utf-8")
        rec = self.dir / "weekly.json"
        broken = '{"2026-W41": {"stories": []},}'
        rec.write_text(broken, encoding="utf-8")
        with self.assertRaises(ValueError):
            w.mark(f, rec)
        self.assertEqual(rec.read_text(encoding="utf-8"), broken)

    def test_missing_week_meta(self):
        f = self.dir / "x.html"
        f.write_text("<html></html>", encoding="utf-8")
        with self.assertRaises(ValueError):
            w.mark(f, self.dir / "weekly.json")

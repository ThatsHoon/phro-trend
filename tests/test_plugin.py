import json, re, unittest
from tests._load import ROOT, load


class PluginTest(unittest.TestCase):
    def test_version_sync(self):
        meta = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["version"], load("skills/weekly/scripts/weekly.py").VERSION)

    def test_skill_commands_exist(self):
        for skill in ("ai", "weekly", "interest"):
            text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            paths = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w/.-]+\.py)", text)
            self.assertTrue(paths, skill)
            self.assertEqual([p for p in paths if not (ROOT / p).exists()], [], skill)

    def test_skill_says_where_data_id_comes_from(self):
        text = (ROOT / "skills/weekly/SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"data-id.{0,60}items\.json")

    def test_interests_never_drop_big_changes(self):
        text = (ROOT / "skills/weekly/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Interests add weight and never filter", text)
        self.assertIn("big changes outside the interests", text)

    def test_weekly_refreshes_interests_first(self):
        text = (ROOT / "skills/weekly/SKILL.md").read_text(encoding="utf-8")
        for needle in ("interest.py show", "refresh due", "--project", "--keywords", "관심사(자동"):
            self.assertIn(needle, text)

    def test_pick_rules_fill_slots(self):
        text = (ROOT / "skills/weekly/SKILL.md").read_text(encoding="utf-8")
        for needle in ("When more than 10 stories pass", "fewer than 3 stories pass the bar", "English news terms"):
            self.assertIn(needle, text)

    def test_version_is_030(self):
        self.assertEqual(load("skills/weekly/scripts/weekly.py").VERSION, "0.3.0")

    def test_constants_agree(self):
        c, w = load("scripts/check.py"), load("skills/weekly/scripts/weekly.py")
        self.assertEqual((c.STAGES, c.LABELS, c.EVIDENCE), (w.STAGES, w.LABELS, w.EVIDENCE))

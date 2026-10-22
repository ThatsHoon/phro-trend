import json, re, unittest
from tests._load import ROOT, load


class PluginTest(unittest.TestCase):
    def test_version_sync(self):
        meta = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["version"], load("skills/weekly/scripts/weekly.py").VERSION)

    def test_skill_commands_exist(self):
        for skill in ("ai", "weekly"):
            text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            paths = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w/.-]+\.py)", text)
            self.assertTrue(paths, skill)
            self.assertEqual([p for p in paths if not (ROOT / p).exists()], [], skill)

    def test_constants_agree(self):
        c, w = load("scripts/check.py"), load("skills/weekly/scripts/weekly.py")
        self.assertEqual((c.STAGES, c.LABELS, c.EVIDENCE), (w.STAGES, w.LABELS, w.EVIDENCE))

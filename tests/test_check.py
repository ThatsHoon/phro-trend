import unittest
from tests._load import load

check = load("scripts/check.py")
LONG = "기존 방식은 질문마다 문서를 통째로 넣었고 이 논문은 필요한 쪽만 골라 넣어서 입력 길이를 크게 줄였다. "


def ai_page(drop=None):
    secs = "".join(f"<h3>{s}</h3><p>{LONG * 2}</p>" for s in check.SECTIONS if s != drop)
    paper = f'<section class="paper">{secs}<pre class="mermaid">flowchart LR</pre><table></table></section>'
    return "<html><body>" + paper * 3 + "</body></html>"


class KindTest(unittest.TestCase):
    def test_kind_defaults_to_ai(self):
        self.assertEqual(check.kind_of("<html></html>"), "ai")

    def test_kind_weekly(self):
        self.assertEqual(check.kind_of('<meta name="phro-kind" content="weekly">'), "weekly")

    def test_ai_page_passes(self):
        self.assertEqual(check.check(ai_page()), [])

    def test_ai_missing_section_fails(self):
        self.assertTrue(any("missing" in m for m in check.check(ai_page(drop="예시"))))

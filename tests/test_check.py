import unittest
from tests._load import ROOT, load

check = load("scripts/check.py")
LONG = "기존 방식은 질문마다 문서를 통째로 넣었고 이 논문은 필요한 쪽만 골라 넣어서 입력 길이를 크게 줄였다. "
KO = "이 방법은 긴 문서를 다룰 때 필요한 쪽만 골라 넣어서 같은 GPU에서 더 긴 입력을 처리한다. "


def page(body):
    return f"<html><body>{body}</body></html>"


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


class StyleTest(unittest.TestCase):
    def test_clean_text_passes(self):
        self.assertEqual(check.check_style(page("<p>" + KO * 20 + "</p>")), [])

    def test_hard_phrase(self):
        self.assertTrue(any("결론적으로" in m for m in check.check_style(page("<p>결론적으로 좋다.</p>"))))

    def test_orig_and_appendix_ignored(self):
        body = '<p class="orig">혁신적 Title</p><details id="appendix"><ul><li>획기적 도구</li></ul></details>'
        self.assertEqual(check.check_style(page(body)), [])

    def test_decor_but_circled_digits_ok(self):
        self.assertTrue(check.check_style(page("<p>좋다 \u2705</p>")))
        self.assertEqual(check.check_style(page("<h3>\u2460 결과</h3>")), [])

    def test_dash(self):
        self.assertTrue(any("em dash" in m for m in check.check_style(page("<p>a \u2014 b</p>"))))

    def test_translationese_density(self):
        self.assertTrue(any(m.startswith("번역투") for m in check.check_style(page("<p>" + KO * 20 + "이를 통해 " * 6 + "</p>"))))
        self.assertEqual(check.check_style(page("<p>" + KO * 20 + "이를 통해 " * 3 + "</p>")), [])

    def test_openers(self):
        self.assertTrue(any("또한" in m for m in check.check_style(page("<p>" + f"또한 {KO}" * 4 + "</p>"))))
        self.assertEqual(check.check_style(page("<p>" + f"또한 {KO}" * 3 + "</p>")), [])

    def test_rhetorical_question(self):
        self.assertTrue(check.check_style(page("<p>정말일까요? 그럴까요?</p>")))
        self.assertEqual(check.check_style(page("<p>정말일까요?</p>")), [])

    def test_bold_lead_in_exempt(self):
        self.assertEqual(check.check_style(page('<p class="item"><strong>결과.</strong> 설명.</p>' * 5)), [])
        self.assertTrue(any("굵은" in m for m in check.check_style(page("<p><strong>a</strong></p>" * 4))))

    def test_reading_minutes(self):
        self.assertEqual(check.reading_minutes(page("<p>" + "가" * 1001 + "</p>")), 3)

    def test_style_md_lists_every_rule(self):
        text = (ROOT / "STYLE.md").read_text(encoding="utf-8")
        words = check.HARD_PHRASES + [w for ws, _ in check.DENSITY.values() for w in ws] + check.OPENERS
        self.assertEqual([w for w in words if w not in text], [])

    def test_head_is_not_prose(self):
        self.assertNotIn("TITLE", check.style_text("<html><head><title>TITLE</title></head><body><p>x</p></body></html>"))

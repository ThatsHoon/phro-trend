"""Check a phro-trend result HTML: watermark-free, natural prose, and the parts its kind requires.

  python check.py RESULT.html
The kind comes from <meta name="phro-kind" content="ai|weekly">; pages without it are ai briefs.
The style lists below are the ones STYLE.md explains to the writer; keep the two in step.
Exit 1 and list problems if anything fails.
"""
import html as htmllib, math, re, sys

SECTIONS = ["한 줄로", "기존에는", "무엇이 문제였나", "이 논문은 이렇게 바꿨다",
            "얼마나 좋아졌나", "어디에 쓰면 좋나", "예시", "바로 써보려면"]

# One hit fails (STYLE.md "바로 실패하는 것"). Model names used as paper baselines are fine.
HARD_PHRASES = ["Generated with", "Co-Authored-By", "Written by Claude", "Claude가 작성", "AI가 작성",
                "AI 요약", "AI-generated", "as an AI", "언어 모델로서", "ai_summary",
                "알아보겠습니다", "살펴보겠습니다", "알아봅시다", "살펴봅시다", "소개해 드리겠습니다", "소개하겠습니다",
                "결론적으로", "요약하자면", "정리하자면", "귀추가 주목", "앞으로가 기대",
                "혁신적", "획기적", "게임 체인저", "게임체인저", "판도를 바꾸", "패러다임 전환", "새로운 지평",
                "되어지", "되어진"]
DECOR = re.compile("[\U0001F000-\U0001FAFF☀-➿■-◿⬀-⯿️]")
# Natural words that read machine-made only when they pile up (STYLE.md "몰리면 실패하는 것").
DENSITY = {  # 이름: (표현들, 본문 1000자당 최대 횟수)
    "번역투": (["를 통해", "을 통해", "에 대해", "에 대한", "에 있어", "함으로써"], 4.0),
    "빈 수식어": (["다양한", "효과적", "효율적", "강력한", "원활한", "최적의", "중요한 역할"], 2.0),
}
PER_DOC = {  # 이름: (정규식, 문서당 최대 횟수)
    "안내 문장": (r"다음과 같", 1),
    "수사 의문문": (r"까요?\?", 1),
    "화살표": (r"→|⇒|->", 2),
}
OPENERS = ["또한", "특히", "이처럼", "따라서", "즉"]  # 같은 말로 시작하는 문장은 문서당 3개까지
MAX_BOLD = 3  # <p class="item"> 머리말 밖의 <strong>, <b>


def kind_of(html):
    m = re.search(r'<meta\s+name="phro-kind"\s+content="([a-z]+)"', html)
    return m.group(1) if m else "ai"


def check(html):
    structure = check_ai(html) if kind_of(html) == "ai" else ["weekly: structure check not implemented"]
    return check_style(html) + structure


def _drop(pattern, s):
    return re.sub(pattern, " ", s, flags=re.S | re.I)


def style_text(html):
    """Visible prose the writer is responsible for: no code, diagrams, appendix, original titles or URLs."""
    s = html
    for tag in ("head", "script", "style", "pre", "code"):
        s = _drop(rf"<{tag}\b.*?</{tag}>", s)
    s = _drop(r'<details id="appendix".*?</details>', s)
    s = _drop(r'<p class="orig"[^>]*>.*?</p>', s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"https?://\S+", " ", s)
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def _nonspace(s):
    return len(re.sub(r"\s", "", s))


def reading_minutes(html):
    return math.ceil(_nonspace(style_text(html)) / 500)


def check_style(html):
    bad = []
    for ch, name in (("—", "em dash"), ("–", "en dash")):
        if ch in html:
            bad.append(f"{name} x{html.count(ch)}")
    symbols = sorted(set(DECOR.findall(_drop(r"<script\b.*?</script>", html))))
    if symbols:
        bad.append(f"emoji or symbol: {symbols}")
    text = style_text(html)
    for w in HARD_PHRASES:
        if w.lower() in text.lower():
            bad.append(f"banned phrase: {w}")
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if s]
    per = max(_nonspace(text) / 1000, 1)
    for name, (words, limit) in DENSITY.items():
        n = sum(text.count(w) for w in words)
        if n / per > limit:
            hits = [s[:40] for s in sents if any(w in s for w in words)][:3]
            bad.append(f"{name} {n}회, 1000자당 {n / per:.1f} (기준 {limit}): {' / '.join(hits)}")
    for name, (pattern, limit) in PER_DOC.items():
        n = len(re.findall(pattern, text))
        if n > limit:
            hits = [s[:40] for s in sents if re.search(pattern, s)][:3]
            bad.append(f"{name} {n}회 (기준 {limit}): {' / '.join(hits)}")
    for w in OPENERS:
        n = sum(1 for s in sents if re.match(rf"{w}[\s,]", s))
        if n > 3:
            bad.append(f"같은 말로 시작하는 문장 '{w}' {n}개 (기준 3)")
    rest = _drop(r'<p class="item"[^>]*>.*?</p>', _drop(r'<details id="appendix".*?</details>', html))
    bold = len(re.findall(r"<(?:strong|b)[\s>]", rest))
    if bold > MAX_BOLD:
        bad.append(f"굵은 글씨 {bold}개 (기준 {MAX_BOLD})")
    return bad


def check_ai(html):
    bad = []
    papers = re.findall(r'<section class="paper".*?</section>', html, flags=re.S)
    if len(papers) != 3:
        bad.append(f"paper sections: {len(papers)} (want 3)")
    for i, sec in enumerate(papers, 1):
        missing = [s for s in SECTIONS if not re.search(rf"<h3[^>]*>\s*{re.escape(s)}", sec)]
        if missing:
            bad.append(f"paper {i} missing: {missing}")
        if 'class="mermaid"' not in sec:
            bad.append(f"paper {i}: no mermaid diagram")
        if "<table" not in sec:
            bad.append(f"paper {i}: no before/after table")
        if re.search(r"<[uo]l[\s>]", sec):
            bad.append(f"paper {i}: bullet list, write prose paragraphs")
        paras = [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<p>(.*?)</p>", sec, flags=re.S)]
        short = [x for x in paras if len(x.strip()) < 80]
        if paras and len(short) > len(paras) / 3:
            bad.append(f"paper {i}: {len(short)}/{len(paras)} paragraphs under 80 chars, join them into prose")
    return bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    problems = check(open(sys.argv[1], encoding="utf-8").read())
    print("\n".join(problems) or "ok")
    sys.exit(1 if problems else 0)

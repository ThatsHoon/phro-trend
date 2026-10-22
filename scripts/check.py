"""Check a phro-trend result HTML: watermark-free, natural prose, and the parts its kind requires.

  python check.py RESULT.html
The kind comes from <meta name="phro-kind" content="ai|weekly">; pages without it are ai briefs.
The style lists below are the ones STYLE.md explains to the writer; keep the two in step.
Exit 1 and list problems if anything fails.
"""
import html as htmllib, re, sys

SECTIONS = ["한 줄로", "기존에는", "무엇이 문제였나", "이 논문은 이렇게 바꿨다",
            "얼마나 좋아졌나", "어디에 쓰면 좋나", "예시", "바로 써보려면"]

# One hit fails (STYLE.md "바로 실패하는 것"). Model names used as paper baselines are fine.
HARD_PHRASES = ["Generated with", "Co-Authored-By", "Written by Claude", "Claude가 작성", "AI가 작성",
                "AI 요약", "AI-generated", "as an AI", "언어 모델로서", "ai_summary",
                "알아보겠습니다", "살펴보겠습니다", "알아봅시다", "살펴봅시다", "소개해 드리겠습니다", "소개하겠습니다",
                "결론적으로", "요약하자면", "정리하자면", "귀추가 주목", "앞으로가 기대",
                "혁신적", "획기적", "게임 체인저", "게임체인저", "판도를 바꾸", "패러다임 전환", "새로운 지평",
                "되어지", "되어진"]
DECOR = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27bf\u25a0-\u25ff\u2b00-\u2bff\ufe0f]")
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

# weekly pages (must match skills/weekly/scripts/weekly.py)
STAGES = ["모델 공개", "데이터", "학습", "평가", "경량화·추론", "응용"]
LABELS = ["바로 써 볼 것", "시험해 볼 것", "지켜볼 것"]
EVIDENCE = ["논문 주장", "코드 공개", "재현 후기 있음"]
SLOTS = ["무엇이 달라졌나", "어디까지 믿나", "적용 고리", "해보려면"]
WEEKLY_PARTS = ['<section id="glance"', '<section id="top"', '<section id="brief"',
                '<section id="flow"', '<section id="try"', '<details id="appendix"']
MAX_BODY = 5000  # 본문 글자 수(공백 제외) 상한: 분당 500자로 10분


def kind_of(html):
    m = re.search(r'<meta\s+name="phro-kind"\s+content="([a-z]+)"', html)
    return m.group(1) if m else "ai"


def check(html):
    structure = check_ai(html) if kind_of(html) == "ai" else check_weekly(html)
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


def check_style(html):
    bad = []
    shown = htmllib.unescape(html)  # entities such as &ndash; reach the reader as the characters themselves
    for ch, name in (("\u2014", "em dash"), ("\u2013", "en dash")):
        if ch in shown:
            bad.append(f"{name} x{shown.count(ch)}")
    symbols = sorted(set(DECOR.findall(htmllib.unescape(_drop(r"<script\b.*?</script>", html)))))
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


def _plain(s):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _section(html, sid):
    m = re.search(rf'<section id="{sid}"[^>]*>(.*?)</section>', html, flags=re.S)
    return m.group(1) if m else ""


def _attrs(s):
    return dict(re.findall(r'(data-[a-z]+)="([^"]*)"', s))


def check_weekly(html):
    pos = [html.find(x) for x in WEEKLY_PARTS]
    if -1 in pos or pos != sorted(pos):
        missing = [x.split('"')[1] for x, p in zip(WEEKLY_PARTS, pos) if p == -1]
        return [f"sections: missing {missing}" if missing else "sections: out of order"]
    bad = []
    glance = _section(html, "glance")
    lines = [_plain(b) for a, b in re.findall(r"<p(\s[^>]*)?>(.*?)</p>", glance, flags=re.S) if "legend" not in a]
    if not 1 <= len([x for x in lines if x]) <= 3:
        bad.append(f"glance: {len(lines)} sentences (want 1~3)")
    if glance.count('class="mermaid"') != 1:
        bad.append("glance: needs exactly one mermaid map")
    stories = re.findall(r'<article class="story"([^>]*)>(.*?)</article>', _section(html, "top"), flags=re.S)
    if not 1 <= len(stories) <= 3:
        bad.append(f"story count: {len(stories)} (want 1~3)")
    for i, (attrs, body) in enumerate(stories, 1):
        a = _attrs(attrs)
        if not a.get("data-id"):
            bad.append(f"story {i}: empty data-id")
        if a.get("data-stage") not in STAGES:
            bad.append(f"story {i}: data-stage {a.get('data-stage')!r} not in {STAGES}")
        label = a.get("data-label")
        if label not in LABELS:
            bad.append(f"story {i}: data-label {label!r} not in {LABELS}")
        sig = re.search(r'<p class="signal"[^>]*>(.*?)</p>', body, flags=re.S)
        sig_text = _plain(sig.group(1)) if sig else ""
        if not label or label not in sig_text or not any(e in sig_text for e in EVIDENCE):
            bad.append(f"story {i}: signal line needs the label and one of {EVIDENCE}")
        slots = [_plain(x) for x in re.findall(r"<h4[^>]*>(.*?)</h4>", body, flags=re.S)]
        if slots != SLOTS:
            bad.append(f"story {i}: slots {slots} (want {SLOTS})")
        if 'href="http' not in body:
            bad.append(f"story {i}: no link")
        paras = [_plain(x) for x in re.findall(r"<p>(.*?)</p>", body, flags=re.S)]
        short = [x for x in paras if len(x) < 80]
        if paras and len(short) > len(paras) / 3:
            bad.append(f"story {i}: {len(short)}/{len(paras)} paragraphs under 80 chars, write prose")
    themes = re.findall(r'<div class="theme"[^>]*>(.*?)</div>', _section(html, "brief"), flags=re.S)
    if not 1 <= len(themes) <= 4:
        bad.append(f"brief: {len(themes)} themes (want 1~4)")
    for j, theme in enumerate(themes, 1):
        head = re.search(r"<h3[^>]*>(.*?)</h3>", theme, flags=re.S)
        if not head or _plain(head.group(1)) not in STAGES:
            bad.append(f"brief theme {j}: heading must be one of {STAGES}")
        items = re.findall(r'<p class="item"([^>]*)>(.*?)</p>', theme, flags=re.S)
        if not 1 <= len(items) <= 4:
            bad.append(f"brief theme {j}: {len(items)} items (want 1~4)")
        for k, (attrs, body) in enumerate(items, 1):
            a = _attrs(attrs)
            if not a.get("data-id") or a.get("data-stage") not in STAGES or a.get("data-label") not in LABELS \
                    or 'href="http' not in body:
                bad.append(f"brief theme {j} item {k}: needs data-id, data-stage, data-label and a link")
    for sid in ("flow", "try"):
        if not any(_plain(x) for x in re.findall(r"<p(?:\s[^>]*)?>(.*?)</p>", _section(html, sid), flags=re.S)):
            bad.append(f"{sid}: empty")
    if re.search(r"<[uo]l[\s>]", re.sub(r'<details id="appendix".*?</details>', "", html, flags=re.S)):
        bad.append("list outside appendix: write prose")
    n = _nonspace(style_text(html))
    if n > MAX_BODY:
        bad.append(f"body: 본문 {n}자, {MAX_BODY}자 안으로 줄인다")
    return bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    problems = check(open(sys.argv[1], encoding="utf-8").read())
    print("\n".join(problems) or "ok")
    sys.exit(1 if problems else 0)

"""Check a phro-trend result HTML: watermark-free, prose paragraphs, and the parts its kind requires.

  python check.py RESULT.html
The kind comes from <meta name="phro-kind" content="ai|weekly">; pages without it are ai briefs.
Exit 1 and list problems if anything fails.
"""
import re, sys

SECTIONS = ["한 줄로", "기존에는", "무엇이 문제였나", "이 논문은 이렇게 바꿨다",
            "얼마나 좋아졌나", "어디에 쓰면 좋나", "예시", "바로 써보려면"]
# Attribution and AI-style phrasing only. Model names (GPT-4, Claude) as paper baselines are fine.
BANNED = ["Generated with", "Co-Authored-By", "Written by Claude", "Claude가 작성", "as an AI",
          "AI가 작성", "AI 요약", "AI-generated", "ai_summary", "혁신적", "획기적",
          "알아보겠습니다", "살펴보겠습니다", "결론적으로"]
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


def kind_of(html):
    m = re.search(r'<meta\s+name="phro-kind"\s+content="([a-z]+)"', html)
    return m.group(1) if m else "ai"


def check(html):
    if kind_of(html) == "ai":
        return check_ai(html)
    return ["weekly: structure check not implemented"]


def check_ai(html):
    bad = []
    text = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    for ch, name in (("\u2014", "em dash"), ("\u2013", "en dash")):
        if ch in html:
            bad.append(f"{name} x{html.count(ch)}")
    if EMOJI.search(text):
        bad.append(f"emoji: {sorted(set(EMOJI.findall(text)))}")
    for w in BANNED:
        if w.lower() in text.lower():
            bad.append(f"banned phrase: {w}")
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

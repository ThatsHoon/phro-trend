"""Hand-built result pages for checker and mark tests, shaped like skills/weekly/assets/template.html."""
from tests._load import load

check = load("scripts/check.py")
KO = "이 방법은 긴 문서를 다룰 때 필요한 쪽만 골라 넣어서 같은 GPU에서 더 긴 입력을 처리한다. "
SLOTS = ["무엇이 달라졌나", "어디까지 믿나", "적용 고리", "해보려면"]


def weekly_page(slots=None, label="시험해 볼 것", themes=2, list_outside=False, minutes_off=0, story_link=True,
                drop_item_label=False):
    stories = []
    for i in range(1, 4):
        link = f' <a href="https://huggingface.co/papers/2610.0000{i}">논문 페이지</a>' if story_link else ""
        cells = "".join(f"<h4>{s}</h4>\n<p>{KO * 3}{link if n == 3 else ''}</p>\n" for n, s in enumerate(slots or SLOTS))
        stories.append(
            f'<article class="story" id="s{i}" data-id="2610.0000{i}" data-stage="학습" data-label="{label}">\n'
            f'<h3>{"①②③"[i - 1]} 결과 문장 {i}</h3>\n'
            f'<p class="signal"><span class="label">{label}</span> 코드 공개 · 2곳에서 화제</p>\n'
            f'<p class="orig">Original title {i} · HF Daily Papers</p>\n{cells}</article>')
    blocks = []
    for j in range(themes):
        stage = check.STAGES[j % len(check.STAGES)]
        items = []
        for k in range(2):
            lab = "" if (drop_item_label and j == 0 and k == 0) else ' data-label="지켜볼 것"'
            items.append(f'<p class="item" data-id="brief-{j}-{k}" data-stage="{stage}"{lab}><strong>짧은 결과 {j}-{k}.</strong> '
                         f'{KO}<span class="label">지켜볼 것</span> <a href="https://example.com/{j}/{k}">출처</a></p>')
        blocks.append(f'<div class="theme">\n<h3>{stage}</h3>\n' + "\n".join(items) + "\n</div>")
    extra_list = "<ul><li>목록</li></ul>" if list_outside else ""
    body = f"""<main>
<h1>2026년 42주차 AI 소식</h1>
<p class="meta">10.12~10.18 · 읽는 데 약 MINUTES분 · 훑은 글 500개 중 13개 · 소스 12곳</p>
<section id="glance">
<h2>이번 주 한눈에</h2>
<p><a href="#s1">{KO}</a></p>
<p><a href="#s2">{KO}</a></p>
<p><a href="#s3">{KO}</a></p>
<pre class="mermaid">
flowchart LR
  M["모델 공개"] --> T["학습 ① ② ③"]
  classDef hot fill:#d6f5e0,stroke:#1f8a4c
</pre>
<p class="legend muted">바로 써 볼 것은 지금 구조에 넣어 볼 만한 것, 시험해 볼 것은 작은 실험으로 확인할 것, 지켜볼 것은 아직 이르지만 알아 둘 흐름이다.</p>
</section>
<section id="top">
<h2>이번 주 3가지</h2>
{chr(10).join(stories)}
</section>
<section id="brief">
<h2>짧게 보는 소식</h2>
{chr(10).join(blocks)}
</section>
<section id="flow">
<h2>흐름</h2>
<p>{KO * 2}</p>{extra_list}
</section>
<section id="try">
<h2>이번 주 해볼 것 하나</h2>
<p>{KO * 2}</p>
</section>
<details id="appendix">
<summary>고르지 않은 글 전체와 수집 현황</summary>
<h3>소스별 글</h3>
<h4>HF Daily Papers</h4>
<ul><li><a href="https://huggingface.co/papers/2610.09999">Other paper</a></li></ul>
<h3>수집 현황</h3>
<table><tr><th>소스</th><th>받은 글</th><th>상태</th></tr></table>
</details>
</main>"""
    head = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="phro-kind" content="weekly">'
            '<meta name="phro-week" content="2026-W42"><title>주간 AI 소식 2026-W42</title></head><body>')
    page = head + body + "</body></html>"
    return page.replace("MINUTES", str(check.reading_minutes(page.replace("MINUTES", "0")) + minutes_off))

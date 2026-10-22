# Style rules

Every phro-trend skill (`ai`, `weekly`) follows these rules when it writes a page. `scripts/check.py` checks pages against the same lists, so change both together.

## Goal

A page should read like a colleague explaining something. Removing tool attributions is not enough: machine-written text gives itself away through habits that pile up, such as inflated words, progress announcements, translated phrasing and sentences that all start the same way. Readers who notice the tone doubt the content before they use it, so the attributions and the habits both go.

Write plain Korean declarative sentences (~다). Keep sentences short, and let them connect inside a paragraph. Explain a technical term in parentheses the first time it appears.

## Fails on one hit

One occurrence fails the check. The appendix, the original-title line (`class="orig"`), code, diagrams and URLs are not checked; dashes and emoji are checked everywhere.

- Tool attributions: `Generated with`, `Co-Authored-By`, `Written by Claude`, `Claude가 작성`, `AI가 작성`, `AI 요약`, `AI-generated`, `as an AI`, `언어 모델로서`.
- Characters: emoji and decorative symbols (check marks, stars, squares, circles, triangles), the em dash (U+2014) and the en dash (U+2013). Write ranges with a tilde between numbers or with "에서", and join sentences with commas or periods. Circled digits (①②③) used as story numbers on the map are fine.
- Progress phrases: `알아보겠습니다`, `살펴보겠습니다`, `알아봅시다`, `살펴봅시다`, `소개해 드리겠습니다`, `소개하겠습니다`. Closers: `결론적으로`, `요약하자면`, `정리하자면`, `귀추가 주목`, `앞으로가 기대`. Hype: `혁신적`, `획기적`, `게임 체인저`, `게임체인저`, `판도를 바꾸`, `패러다임 전환`, `새로운 지평`.
- Double passive: `되어지`, `되어진`. Write "개선된다", not "개선되어진다".
- The `ai_summary` Hugging Face attaches to papers: never copy it, since a machine summary is itself a trace.

## Fails when they pile up

Each of these is natural Korean, and banning them would stiffen the prose; the machine tone comes from clusters. The check counts them and, past the limit, shows up to three offending sentence openings.

| Group | Expressions | Limit |
|---|---|---|
| Translationese | `를 통해`, `을 통해`, `에 대해`, `에 대한`, `에 있어`, `함으로써` | 4 per 1,000 body characters |
| Empty modifiers | `다양한`, `효과적`, `효율적`, `강력한`, `원활한`, `최적의`, `중요한 역할` | 2 per 1,000 body characters |
| Signpost sentence | openers like "다음과 같습니다" (`다음과 같`) | 1 per page |
| Rhetorical question | "~일까요?", "~할까?" | 1 per page |
| Arrows | →, ⇒ and -> in the body | 2 per page |
| Same opener | sentences starting with `또한`, `특히`, `이처럼`, `따라서`, `즉` | 3 per word per page |
| Bold | `<strong>` or `<b>` outside the short-news lead | 3 per page |

Body characters exclude spaces; a body shorter than 1,000 counts as 1,000.

## How to write

Writing like a person from the start is faster than steering around the lists.

- **Names and numbers, not vague words.** Bad: "다양한 모델에서 효과적인 성능 향상을 보였다." Good: "Qwen3 8B와 Llama 4에서 정확도가 62%에서 71%로 올랐다(A100 한 장 기준)."
- **Vary sentence length and openings.** Bad: "또한 메모리를 줄였다. 또한 속도를 높였다. 또한 코드를 공개했다." Good: "메모리를 절반으로 줄였고, 같은 GPU에서 속도도 1.4배 빨라졌다. 코드는 저장소에 공개돼 있다."
- **One idea per paragraph.** Bad: method, results, limits and setup in one paragraph. Good: the method paragraph follows the input to the output, and the limits get a paragraph of their own.
- **Back every claim, or drop it.** Bad: "실무에서 큰 도움이 될 것이다." Good: "사내 문서 검색처럼 질문 하나에 문단이 여러 개 필요한 경우, 붙이는 문단을 10개에서 3개로 줄였다(저자 실험, 영어 데이터)."
- **Do not restate at the end of a paragraph.** Bad: "...토큰을 1/5로 줄였다. 즉, 이 방법은 토큰을 크게 줄이는 방법이다." Good: end at "...토큰을 1/5로 줄였다."
- **Rewrite other people's text in your own words.** Do not copy source sentences. When a quote is essential, use one quote under 15 words per item (story or paper), in quotation marks with its source.

Model names a paper compares against (GPT-4, Claude and so on) are fine. What is blocked is authorship marks and machine-made style.

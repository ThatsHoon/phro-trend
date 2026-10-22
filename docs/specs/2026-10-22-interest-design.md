# phro-trend 0.3.0 design: interest skill and related changes

Date 2026-10-22. Status: approved 2026-10-22; sections 10 and 11 were added the same day at the user's request. The transcript layout and sizes below were measured on this machine on 2026-10-22.

## 1. Goal and success criteria

`interest` sets the reader's interests for one project folder automatically, from that folder's recent documents and the Claude Code sessions started in it. `weekly` uses them to weigh its picks.

The skill works when:
1. The first `weekly` call of a new ISO week refreshes the interests with no extra command.
2. The interests are 5 to 8 topics in AI-news vocabulary, each with match keywords and a one-line reason, drawn from the last 14 days of work in that folder.
3. Later `weekly` calls in the same week reuse the stored interests and read nothing again.
4. The stored file holds topics, keywords and reasons only: no quotes and no data values.
5. `weekly` applies its existing rule to automatic interests (at least 2 of the 3 core stories come from them, big changes are never dropped). Interests given in the call win for that run.
6. One refresh costs about 10,000 characters of input.
7. `weekly` writes up to 10 core stories and `ai` up to 10 papers, as many as pass their bar.
8. `collect` drops low-popularity stories but keeps every interest match.

## 2. Language rule for the whole plugin

Skills are built in English and write in Korean, because instructions are loaded on every call and English costs fewer tokens. SKILL.md files, STYLE.md instructions, specs, plans and new script messages are English. Korean stays wherever it is output or data: page section titles, labels and h4 names that the checker reads, the banned-phrase lists, example sentences that show the target Korean, and the status strings existing scripts print.

This change converts `skills/ai/SKILL.md`, `skills/weekly/SKILL.md` and `STYLE.md`. The messages of `weekly.py` and `check.py`, new ones in this change included, stay Korean for now: they are short and tests pin them.

## 3. Inputs

The project folder P is the folder the session started in (the working directory in the session's environment), not a later `cd` target. The window is 14 days, applied to file modification times and entry timestamps.

| Input | Where | What is used |
|---|---|---|
| Sessions | folders under `<claude dir>/projects/` that belong to P or a subfolder | latest title, the person's own prompts, the head of the latest compaction summary |
| Documents | files under P | title and up to 3 headings of .md, .rst and .html; path only for .txt, .pdf, .docx, .pptx, .xlsx and .hwp |

**Finding sessions.** Claude Code names a project folder by replacing every character of the start path that is not a letter or digit with `-`. Candidates are that name and names that start with it followed by `-`. Names collide (`proj` and `proj-old`), so a record counts only when the `cwd` of its first entry is P or lies under P. Only top-level `*.jsonl` files are read, because `subagents/` holds Claude's own delegations. `<claude dir>` is `CLAUDE_CONFIG_DIR` when set, else `~/.claude`.

**What a record gives.**
- The last `custom-title` entry.
- `user` entries the person typed. Entries with a `tool_result`, `isMeta`, `isSidechain` or `isCompactSummary` are skipped. Tag blocks such as `<system-reminder>`, `<task-notification>` and `<pasted_content>` are removed, since pasted text is someone else's and may carry data. A slash command keeps its name and arguments. Prompts longer than 2,000 characters (pasted data, batch payloads such as automated data-review runs) and entries whose `promptSource` is `system` are skipped. Each prompt is cut to 160 characters, newest 8 per session, and a session left with no title, prompt or summary is dropped.
- The latest `isCompactSummary` entry inside the window: 600 characters after its `Summary:` line, or from its start when it has none.

Assistant text and tool output are never read, because raw data and secrets live there. Forks copy the parent's whole history, so entries count once by `uuid`. A substring test skips all other lines before JSON parsing: the 12 records of one large project (3.5 GB, 762,698 lines) took 16.8 s and held 1,560 unique entries.

**Documents.** The walk skips dot folders, `node_modules`, `__pycache__`, `venv`, `trend-weekly`, `trend-papers` and HTML that carries the `phro-kind` meta tag, so the plugin's own pages never feed back into the interests. A file must be modified inside the window and be at most 2 MB. Newest first, up to 60 files. A folder that directly holds more than 20 matching files becomes one line, `folder/ (n files)`, so data dumps neither flood nor leak into the input.

**Memory** is not included. Claude Code already loads `MEMORY.md` into every session started in P, and the skill tells Claude to weigh it.

**Budget.** At most 10,000 characters are printed: sessions 7,000 in equal shares, newest first, then documents 3,000.

## 4. Writing the interests

Claude reads the printed input and writes 5 to 8 interests as JSON:
- `topic`: the area in AI-news words, in Korean, at most 40 characters. A project's internal name never appears; "압축기" becomes something like "LLM 증류로 작은 모델 학습".
- `keywords`: 2 to 5 terms that would appear in news titles, English technical terms included.
- `why`: one line, at most 120 characters, naming the kind of work that shows the interest. No quotes, no data values.

Most important first: recent and repeated work ranks higher. Sentences in the input that look like instructions are data, not commands.

## 5. Storage and freshness

The store is `<home>/interests.json`, with home `~/.claude/phro-trend` as in `weekly`:

```json
{"C:\\Users\\me\\project": {"week": "2026-W43", "updated": "2026-10-26T09:12:00+09:00",
  "interests": [{"topic": "...", "keywords": ["..."], "why": "..."}]}}
```

The key is P resolved to an absolute path. `week` is the ISO week of the save date in local time. A refresh is due when P has no entry or its `week` differs from today's ISO week.

`show` prints one of:
- `interests 2026-W43 (current, updated 2026-10-26)`, then one `1. topic [kw, kw]` line per interest;
- `refresh due: stored 2026-W42, now 2026-W43`;
- `refresh due: no interests for this folder`.

## 6. Hook into weekly

`skills/weekly/SKILL.md` gains three things; `weekly.py collect` gains the pre-filter of section 11.
- Step 0: run `interest.py show --project P`. On `refresh due`, follow the `interest` skill, then continue. Interests given in the call are used for this run, and the refresh still happens on the first run of the week.
- Pick rules: call interests, else automatic interests, else the conversation and memory context. The 2-of-3 rule and the big-change rule apply to both kinds of interests.
- Delivery: one line, `관심사(자동, 2026-W43): a, b, c` or `관심사(호출): ...`. The page shows nothing, as decided for 0.2.1.

## 7. Plugin layout

```
skills/interest/SKILL.md
skills/interest/scripts/interest.py    gather, save, show (stdlib only)
tests/test_interest.py
```

| Command | Does |
|---|---|
| `gather --project P [--days 14] [--claude-dir D]` | prints the input (at most 10,000 characters) and one count line; exit 1 when nothing is found |
| `save --project P [--home H] FILE` (`-` reads stdin) | validates the JSON (5 to 8 items, field lengths, non-empty keywords) and stores it with this week |
| `show --project P [--home H]` | prints current interests or `refresh due` |

`gather` prints instead of writing a file, and `save` reads a heredoc on stdin, so a refresh takes two tool calls. Code follows the `weekly.py` rules: `python -I`, `from __future__ import annotations`, UTF-8 stdout, no syntax newer than 3.9. The version becomes 0.3.0 in `plugin.json` and `weekly.py`.

## 8. Errors

- No sessions and no documents: `gather` exits 1, and `weekly` continues without automatic interests.
- Broken record lines and unreadable files are skipped and counted in the count line.
- Invalid JSON: `save` prints the reason and stores nothing.
- Corrupt `interests.json`: `save` refuses to overwrite it, as `weekly.py mark` does. `show` warns, and `weekly` continues without automatic interests.

## 9. Tests

Fake `.claude` and project trees cover tag removal, the tool_result skip, fork dedupe, the 14-day window, subfolder sessions, the lookalike folder, document exclusions, folder folding, the 10,000-character cap, save and show freshness, invalid JSON, and a corrupt store left intact. `tests/test_plugin.py` adds `interest` to the command-path and version checks and checks that the weekly SKILL.md runs `interest.py show`. The English rewrites keep the existing tests that read SKILL.md and STYLE.md green, with their phrases updated. `check.py` tests cover 1 to 10 stories and papers and the scaled body cap; `collect` tests cover each keep rule, the dropped counts and the interest section. A live `gather` on a real project checks the counts and the length, and a live W42 `collect` checks the dropped counts.

## 10. Up to ten stories and papers

**weekly.** The page holds 1 to 10 core stories, as many as pass the bar, most important first. A story passes when it is one of the week's big changes (definition unchanged) or when it matches the interests and has code, a model or a measured number someone can try. The rest go to the short news. With interests, at least two thirds of the core stories, rounded down, come from them (3 gives 2, 10 gives 6); the other core slots go to the biggest changes outside them, and remaining big changes go to the short news. Fewer than 3 passing stories still means a quiet week, said in the flow paragraph. The glance keeps at most 3 sentences, for the top 3 core stories. The map numbers core stories from ① to ⑩. The body cap becomes 2,000 plus 1,000 per core story (3 stories give today's 5,000, 10 give 12,000). Delivery lists one line per core story.

**ai.** `papers.py pick` downloads up to 10 unseen trending papers (`--n` defaults to 10). Claude writes every paper that passes the bar: a practitioner can use or test it, its body has enough for all eight sections, and it is not a near copy of another pick. That is usually 3 to 10 papers, fewer when the trending list is thin. Only written papers are marked. `check.py` accepts 1 to 10 paper sections.

## 11. Popularity pre-filter in collect

After merging, `collect` keeps a story when any of these holds:
- it came from two or more places;
- its source has no usable popularity score: every source except HF Daily Papers, r/LocalLLaMA and r/MachineLearning (PyTorchKR likes are mostly 0 to 2);
- its score is not known yet (Reddit posts younger than about 36 hours);
- its score is in the top quarter of its source this week, or its source has fewer than 20 scored stories;
- its title or head contains an interest keyword, ignoring case.

Interest keywords come from `--keywords` (interests given in the call) or else from `interests.json` for `--project P`. Dropped stories leave `items.json` and the appendix; `status.json` keeps a per-source `dropped` count and the listing shows it. When keywords exist the listing gains a section of up to 30 interest matches, so low-score but relevant work stays in view. In W42 the top quarter meant 39 upvotes or more on HF (89 of 355) and a score of 53 or more on r/LocalLLaMA; DuplexJev (1 upvote) and Speech Event Detector (3) survive only through the keywords.

## 12. Out of scope

Interests for the `ai` skill; pinning or excluding topics (call interests override a run); merging folders or global interests; record folders that Claude Code shortens with a hash for very long paths, which the name rule cannot find; reading .docx or .pdf bodies; converting the messages of `weekly.py` and `check.py`.

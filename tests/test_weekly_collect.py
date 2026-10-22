import contextlib, io, json, os, tempfile, unittest
from datetime import date, timedelta, timezone
from pathlib import Path
from tests._load import load

w = load("skills/weekly/scripts/weekly.py")
KST = timezone(timedelta(hours=9))
START, END = w.week_bounds("2026-W42", KST)
EMPTY_RSS = b'<?xml version="1.0"?><rss><channel></channel></rss>'


def item(source, url, ident=None, score=None, links=()):
    return {"source": source, "role": w.ROLE[source], "title": url.rsplit("/", 1)[-1], "url": url,
            "date": "2026-10-14T00:00:00+00:00", "head": "", "score": score, "comments": None,
            "links": list(links), "ident": ident or w.ident(url)}


def paper(pid, upvotes=50, title=None):
    return {"paper": {"id": pid, "title": title or f"Paper {pid}", "upvotes": upvotes, "summary": "abstract",
                      "submittedOnDailyAt": "2026-10-13T00:00:00.000Z"}, "numComments": 0}


def rss(title, when, html=""):
    return (f'<?xml version="1.0"?><rss><channel><item><title>{title}</title><link>https://example.com/{title}</link>'
            f'<pubDate>{when}</pubDate><description>{html}</description></item></channel></rss>').encode()


def make_get(fail=(), reddit_pages=None, hf=None):
    end_ts = int(END.timestamp())
    one_post = [{"id": "r1", "title": "Discussion", "score": 300, "num_comments": 40, "created_utc": end_ts - 3600,
                 "permalink": "/r/LocalLLaMA/comments/r1/x/", "url": "https://arxiv.org/abs/2610.14224",
                 "selftext": "", "_meta": {"retrieved_2nd_on": end_ts}}]
    routes = {
        "https://huggingface.co/api/daily_papers?week=2026-W42&limit=100&p=0": json.dumps(
            hf if hf is not None else [paper("2610.14224"), paper("2610.99999")]).encode(),
        "https://huggingface.co/blog/feed.xml": rss("blog-post", "Tue, 13 Oct 2026 01:00:00 GMT"),
        "https://magazine.sebastianraschka.com/feed": EMPTY_RSS,
        "https://nlp.elvissaravia.com/feed": rss("papers-of-the-week", "Sat, 17 Oct 2026 01:00:00 GMT",
                                                 "&lt;a href=&quot;https://arxiv.org/abs/2610.14224&quot;&gt;p&lt;/a&gt;"),
        "https://cameronrwolfe.substack.com/feed": EMPTY_RSS,
        "https://lilianweng.github.io/index.xml": EMPTY_RSS,
        "https://api.github.com/repos/unslothai/unsloth/releases?per_page=30": b"[]",
        "https://discuss.pytorch.kr/latest.json?order=created&page=0": json.dumps({"topic_list": {"topics": [
            {"id": 7, "slug": "kr", "title": "KR news", "created_at": "2026-10-14T03:00:00.000Z", "like_count": 3, "posts_count": 2}]}}).encode(),
        "https://discuss.pytorch.kr/latest.json?order=created&page=1": json.dumps({"topic_list": {"topics": []}}).encode(),
    }

    def get(url, headers=None):
        for key in fail:
            if key in url:
                raise w.FetchError("요청 제한(429)")
        if "subreddit=LocalLLaMA" in url:
            return json.dumps({"data": reddit_pages.pop(0) if reddit_pages else one_post}).encode()
        if "subreddit=MachineLearning" in url:
            return json.dumps({"data": []}).encode()
        if url not in routes:
            raise w.FetchError("HTTP 404")
        return routes[url]

    return get


def story(sid, source, score, title=None, n_sources=1):
    return {"id": sid, "source": source, "score": score, "n_sources": n_sources, "title": title or sid, "head": ""}


def hf(sid, score, title=None, n_sources=1):
    return story(sid, "hf_papers", score, title, n_sources)


def rd(sid, score):
    return story(sid, "r_localllama", score)


def blog(sid):
    return story(sid, "hf_blog", None)


def always_fail(url, headers=None):
    raise w.FetchError("HTTP 503")


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def run_collect(self, week="2026-W42", get=None, today=None, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = w.collect(week, self.out, get=get or make_get(), tz=KST, home=self.home, today=today, **kw)
        return code, buf.getvalue()

    def status(self):
        return json.loads((self.out / "status.json").read_text(encoding="utf-8"))

    def stories(self):
        return {x["id"]: x for x in json.loads((self.out / "items.json").read_text(encoding="utf-8"))["stories"]}

    def test_merge(self):
        hf = item("hf_papers", "https://huggingface.co/papers/2610.14224", ident="2610.14224", score=400)
        rd = item("r_localllama", "https://www.reddit.com/r/LocalLLaMA/comments/abc/x/", ident="2610.14224", score=900)
        nl = item("dair", "https://nlp.elvissaravia.com/p/w42",
                  links=["https://arxiv.org/abs/2610.14224v1", "https://arxiv.org/pdf/2610.99999"])
        other = item("hf_papers", "https://huggingface.co/papers/2610.99999", ident="2610.99999")
        s = {x["id"]: x for x in w.merge([rd, nl, hf, other])}
        self.assertEqual(s["2610.14224"]["source"], "hf_papers")
        self.assertEqual(s["2610.14224"]["n_sources"], 3)
        self.assertEqual(s["2610.99999"]["n_sources"], 2)
        self.assertIn(w.ident(nl["url"]), s)

    def test_story_keeps_arxiv_and_code_links(self):
        hf = item("hf_papers", "https://huggingface.co/papers/2610.14224", links=["https://github.com/Org/Repo", "https://proj.example"])
        kr = item("pytorchkr", "https://discuss.pytorch.kr/t/x/1", links=["https://github.com/a/b/tree/main"])
        blog = item("hf_blog", "https://huggingface.co/blog/post")
        s = {x["id"]: x for x in w.merge([hf, kr, blog])}
        paper, news = s["2610.14224"], s["https://discuss.pytorch.kr/t/x/1"]
        self.assertEqual((paper["arxiv"], paper["github"]), ("2610.14224", "https://github.com/org/repo"))
        self.assertEqual((news["arxiv"], news["github"]), (None, "https://github.com/a/b"))
        self.assertIn("[code]", w._row(paper))
        self.assertNotIn("[code]", w._row(s["https://huggingface.co/blog/post"]))

    def test_pull_failures_are_not_called_unscheduled(self):
        (self.home / "pull").mkdir()
        rows = [{"at": f"2026-10-1{d}T09:00:00+09:00", "feed": "geeknews", "ok": False, "error": "요청 제한(429)"}
                for d in (3, 4, 5)]
        (self.home / "pull" / "log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        self.run_collect()
        error = self.status()["geeknews"]["error"]
        self.assertNotEqual(error, w.UNSCHEDULED)
        self.assertIn("3회", error)
        self.assertIn("요청 제한(429)", error)
        self.assertEqual(self.status()["arxiv_eess_as"]["error"], w.UNSCHEDULED)

    def test_corrupt_record_warns_and_collects(self):
        (self.home / "weekly.json").write_text("{oops", encoding="utf-8")
        code, printed = self.run_collect()
        self.assertEqual(code, 0)
        self.assertIn("weekly.json", printed)
        self.assertTrue((self.out / "items.json").exists())

    def test_collect_partial_failure(self):
        code, _ = self.run_collect(get=make_get(fail=("subreddit=MachineLearning",)))
        self.assertEqual(code, 0)
        st = self.status()
        self.assertFalse(st["r_machinelearning"]["ok"])
        self.assertIn("429", st["r_machinelearning"]["error"])
        self.assertTrue(st["hf_papers"]["ok"])
        self.assertEqual(self.stories()["2610.14224"]["n_sources"], 3)  # HF, the Reddit link post, the DAIR roundup

    def test_collect_all_fail(self):
        self.assertEqual(self.run_collect(get=always_fail)[0], 1)

    def test_malformed_source_does_not_stop_collect(self):
        good = make_get()

        def get(url, headers=None):
            return b'{"error": "rate limited"}' if "daily_papers" in url else good(url, headers)

        code, _ = self.run_collect(get=get)
        status = self.status()
        self.assertEqual(code, 0)
        self.assertFalse(status["hf_papers"]["ok"])
        self.assertIn("AttributeError", status["hf_papers"]["error"])
        self.assertTrue(status["hf_blog"]["ok"])

    def test_collect_reports_unscheduled_pull(self):
        _, printed = self.run_collect()
        self.assertEqual(self.status()["geeknews"]["error"], "쌓기 일정 미등록")
        self.assertIn("GeekNews: 쌓기 일정 미등록", printed)
        self.assertLess(printed.index("GeekNews: 쌓기 일정 미등록"), printed.index("HF Daily Papers: 2개"))

    def test_collect_keeps_partial_reddit(self):
        end_ts = int(END.timestamp())
        page1 = [{"id": f"p{i}", "title": f"P{i}", "score": 1, "num_comments": 0, "created_utc": end_ts - 60 * (i + 1),
                  "permalink": f"/r/LocalLLaMA/comments/p{i}/x/", "url": "", "selftext": ""} for i in range(100)]
        get = make_get(reddit_pages=[page1])
        broken = lambda url, headers=None: (_ for _ in ()).throw(w.FetchError("HTTP 500")) if "before=" + str(end_ts - 6000) in url else get(url)
        self.run_collect(get=broken)
        st = self.status()["r_localllama"]
        self.assertTrue(st["ok"])
        self.assertEqual(st["count"], 100)
        self.assertTrue(st["error"].startswith("일부만 받음"))

    def test_covered_marks(self):
        (self.home / "seen.json").write_text('{"2610.14224": "2026-10-21"}', encoding="utf-8")
        (self.home / "weekly.json").write_text('{"2026-W41": {"stories": [{"id": "2610.99999"}]}}', encoding="utf-8")
        _, printed = self.run_collect()
        s = self.stories()
        self.assertEqual(s["2610.14224"]["covered_ai"], "2026-10-21")
        self.assertEqual(s["2610.99999"]["covered_weekly"], "2026-W41")
        self.assertIn("[W41]", printed)

    def test_prefilter_rules(self):
        stories = [hf(f"hf{n}", n) for n in range(1, 41)] + [hf("speech", 2, title="Speech decisions without decoding"),
                   hf("multi", 1, n_sources=2), rd("new", None), blog("b")]
        kept, dropped = w.prefilter(stories, ["speech"])
        self.assertEqual({s["id"] for s in kept}, {f"hf{n}" for n in range(30, 41)} | {"speech", "multi", "new", "b"})
        self.assertEqual(dropped, {"hf_papers": 29})
        self.assertTrue(next(s for s in kept if s["id"] == "speech")["match"])

    def test_prefilter_small_source_keeps_all(self):
        kept, dropped = w.prefilter([hf(f"hf{n}", n) for n in range(1, 20)], [])
        self.assertEqual((len(kept), dropped), (19, {}))

    def hf_rows(self):
        return [paper(f"2610.{n:05d}", upvotes=n, title="Speech event detector" if n == 2 else None) for n in range(1, 31)]

    def test_collect_drops_and_lists_matches(self):
        code, printed = self.run_collect(get=make_get(hf=self.hf_rows()), keywords=["speech"])
        self.assertEqual(code, 0)
        self.assertEqual(self.status()["hf_papers"]["dropped"], 21)
        self.assertIn("인기 하위 21개 뺌", printed)
        self.assertIn("== 관심사에 맞는 글 ==", printed)
        self.assertIn("Speech event detector", printed.split("== 관심사에 맞는 글 ==")[1])
        self.assertNotIn("2610.00001", self.stories())
        self.assertIn("2610.00002", self.stories())

    def interest_store(self, text):
        project = Path(self.tmp.name) / "proj"
        project.mkdir(exist_ok=True)
        (self.home / "interests.json").write_text(text(os.path.normcase(str(project.resolve()))), encoding="utf-8")
        return project

    def test_collect_uses_interest_store(self):
        project = self.interest_store(lambda key: json.dumps({key: {"week": "2026-W43", "updated": "", "interests": [
            {"topic": "t", "keywords": ["speech", "asr"], "why": "w"}]}}))
        _, printed = self.run_collect(get=make_get(hf=self.hf_rows()), project=project)
        self.assertIn("== 관심사에 맞는 글 ==", printed)

    def test_collect_broken_interest_store(self):
        project = self.interest_store(lambda key: "{oops")
        code, printed = self.run_collect(get=make_get(hf=self.hf_rows()), project=project)
        self.assertEqual(code, 0)
        self.assertIn("interests.json", printed)
        self.assertNotIn("== 관심사에 맞는 글 ==", printed)

    def test_default_week(self):
        self.run_collect(week=None, today=date(2026, 10, 22))
        self.assertEqual(json.loads((self.out / "items.json").read_text(encoding="utf-8"))["week"], "2026-W42")

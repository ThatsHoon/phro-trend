import json, tempfile, unittest
import urllib.parse
from datetime import timedelta, timezone
from pathlib import Path
from tests._load import load

w = load("skills/weekly/scripts/weekly.py")
KST = timezone(timedelta(hours=9))
START, END = w.week_bounds("2026-W42", KST)
FEED_URL = "https://huggingface.co/blog/feed.xml"


class FakeGet:
    """get(url) stand-in: routes is a dict url -> bytes or a function url -> bytes."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, headers=None):
        self.calls.append(url)
        body = self.routes(url) if callable(self.routes) else self.routes.get(url)
        if body is None:
            raise w.FetchError("HTTP 404")
        return body


def hf_page(ids):
    return json.dumps([{"paper": {"id": f"2610.{i:05d}", "title": f"P{i}", "upvotes": 10, "summary": "abstract",
                                  "ai_summary": "machine", "githubRepo": None, "projectPage": None,
                                  "submittedOnDailyAt": "2026-10-13T00:00:00.000Z"},
                        "numComments": 1} for i in ids]).encode()


def topic(i, day, pinned=False):
    return {"id": i, "slug": f"t{i}", "title": f"T{i}", "created_at": f"2026-10-{day:02d}T03:00:00.000Z",
            "like_count": 2, "posts_count": 3, "pinned": pinned}


class SourcesTest(unittest.TestCase):
    def test_src_hf_pages_and_no_ai_summary(self):
        base = "https://huggingface.co/api/daily_papers?week=2026-W42&limit=100&p="
        get = FakeGet({base + "0": hf_page(range(100)), base + "1": hf_page([100])})
        items = w.src_hf(get, "2026-W42")
        self.assertEqual(len(items), 101)
        self.assertEqual(items[0]["url"], "https://huggingface.co/papers/2610.00000")
        self.assertEqual((items[0]["source"], items[0]["role"], items[0]["ident"]), ("hf_papers", "발견", "2610.00000"))
        self.assertNotIn("machine", json.dumps(items))

    def test_src_feed_window(self):
        rows = [("out-before", "Sun, 11 Oct 2026 23:59:00 +0900"), ("in-start", "Mon, 12 Oct 2026 00:00:00 +0900"),
                ("in-end", "Sun, 18 Oct 2026 14:59:00 GMT"), ("out-after", "Sun, 18 Oct 2026 15:30:00 GMT"), ("undated", None)]
        xml = "".join(f"<item><title>{t}</title><link>https://huggingface.co/blog/{t}</link>"
                      + (f"<pubDate>{d}</pubDate>" if d else "") + "</item>" for t, d in rows)
        get = FakeGet({FEED_URL: f'<?xml version="1.0"?><rss><channel>{xml}</channel></rss>'.encode()})
        items, undated = w.src_feed(get, "hf_blog", FEED_URL, START, END)
        self.assertEqual([x["title"] for x in items], ["in-start", "in-end"])
        self.assertEqual(undated, 1)

    def test_src_reddit_paging_and_ident(self):
        end_ts = int(END.timestamp())
        page1 = [{"id": f"a{i}", "title": f"A{i}", "score": 5, "num_comments": 1, "created_utc": end_ts - 60 * (i + 1),
                  "permalink": f"/r/LocalLLaMA/comments/a{i}/t/", "url": f"https://www.reddit.com/r/LocalLLaMA/comments/a{i}/t/",
                  "selftext": "body"} for i in range(100)]
        low = min(p["created_utc"] for p in page1)
        page2 = [{"id": f"b{i}", "title": f"B{i}", "score": 9, "num_comments": 2, "created_utc": low - 60 * (i + 1),
                  "permalink": f"/r/LocalLLaMA/comments/b{i}/t/",
                  "url": "https://arxiv.org/abs/2610.14224" if i == 0 else "https://i.redd.it/x.png", "selftext": ""}
                 for i in range(3)]

        def route(url):
            before = int(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["before"][0])
            return json.dumps({"data": page1 if before == end_ts else page2 if before == low else []}).encode()

        get = FakeGet(route)
        items = w.src_reddit(get, "r_localllama", "LocalLLaMA", START, END)
        self.assertEqual(len(items), 103)
        self.assertIn(f"before={low}", get.calls[1])
        self.assertIn("2610.14224", [x["ident"] for x in items])
        self.assertEqual(items[0]["url"], "https://www.reddit.com/r/LocalLLaMA/comments/a0/t/")
        self.assertFalse(any(c.startswith(("https://www.reddit.com", "https://reddit.com")) for c in get.calls))

    def test_src_discourse_stops_at_window_start(self):
        base = "https://discuss.pytorch.kr"
        get = FakeGet({base + "/latest.json?order=created&page=0": json.dumps({"topic_list": {"topics": [topic(1, 20), topic(2, 18)]}}).encode(),
                       base + "/latest.json?order=created&page=1": json.dumps({"topic_list": {"topics": [topic(3, 13), topic(4, 11)]}}).encode()})
        items = w.src_discourse(get, "pytorchkr", base, START, END)
        self.assertEqual([x["url"] for x in items], [base + "/t/t2/2", base + "/t/t3/3"])
        self.assertEqual(len(get.calls), 2)

    def test_src_discourse_old_pinned_topic_does_not_stop_paging(self):
        base = "https://discuss.pytorch.kr"
        old_pinned = dict(topic(9, 1, pinned=True), created_at="2024-01-01T00:00:00.000Z")
        get = FakeGet({base + "/latest.json?order=created&page=0": json.dumps({"topic_list": {"topics": [old_pinned, topic(2, 18)]}}).encode(),
                       base + "/latest.json?order=created&page=1": json.dumps({"topic_list": {"topics": [topic(3, 13), topic(4, 11)]}}).encode()})
        self.assertEqual(len(w.src_discourse(get, "pytorchkr", base, START, END)), 2)

    def test_src_pulled(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "pull").mkdir()
            rows = [{"title": "out", "link": "https://arxiv.org/abs/2610.00001", "date": "2026-10-05T00:00:00+00:00", "announce_type": "new"},
                    {"title": "replaced", "link": "https://arxiv.org/abs/2610.00002", "date": "2026-10-14T00:00:00+00:00", "announce_type": "replace"},
                    {"title": "in", "link": "https://arxiv.org/abs/2610.00003", "date": "2026-10-14T00:00:00+00:00", "announce_type": "new"}]
            lines = [json.dumps(dict(r, content="abstract", links=[], fetched_at="2026-10-14T09:00:00+09:00")) for r in rows]
            (home / "pull" / "arxiv-eess-AS.jsonl").write_text("\n".join(lines) + "\n{broken", encoding="utf-8")
            got = w.src_pulled(home, "arxiv_eess_as", "arxiv-eess-AS", START, END)
            self.assertEqual([(x["source"], x["role"], x["title"]) for x in got], [("arxiv_eess_as", "음성", "in")])
            self.assertEqual(w.src_pulled(home, "geeknews", "geeknews", START, END), [])


def post(i, created, scored=True, url=None):
    p = {"id": f"q{i}", "title": f"Q{i}", "score": 40, "num_comments": 3, "created_utc": created,
         "permalink": f"/r/LocalLLaMA/comments/q{i}/t/", "url": url or f"https://www.reddit.com/r/LocalLLaMA/comments/q{i}/t/",
         "selftext": ""}
    if scored:
        p["_meta"] = {"retrieved_2nd_on": created + 129600}
    return p


class RedditEdgeTest(unittest.TestCase):
    def test_later_page_failure_keeps_first_page(self):
        end_ts = int(END.timestamp())
        page1 = [post(i, end_ts - 60 * (i + 1)) for i in range(100)]

        def route(url):
            if f"before={end_ts}&" in url:
                return json.dumps({"data": page1}).encode()
            raise w.FetchError("HTTP 500")

        with self.assertRaises(w.Partial) as cm:
            w.src_reddit(FakeGet(route), "r_localllama", "LocalLLaMA", START, END)
        self.assertEqual((len(cm.exception.items), cm.exception.reason), (100, "HTTP 500"))

    def test_first_page_failure_is_a_plain_fetch_error(self):
        def route(url):
            raise w.FetchError("HTTP 500")

        with self.assertRaises(w.FetchError) as cm:
            w.src_reddit(FakeGet(route), "r_localllama", "LocalLLaMA", START, END)
        self.assertNotIsInstance(cm.exception, w.Partial)

    def test_score_unknown_before_second_retrieval(self):
        end_ts = int(END.timestamp())
        get = FakeGet(lambda url: json.dumps({"data": [post(1, end_ts - 100, scored=False), post(2, end_ts - 200)]}).encode())
        items = w.src_reddit(get, "r_localllama", "LocalLLaMA", START, END)
        self.assertEqual([x["score"] for x in items], [None, 40])

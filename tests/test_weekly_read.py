import contextlib, io, json, tempfile, unittest
from pathlib import Path
from tests._load import load

w = load("skills/weekly/scripts/weekly.py")


class ReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        (self.home / "pull").mkdir(parents=True)
        self.out = Path(self.tmp.name) / "out"
        self.calls, self.headers_seen = [], {}
        self.routes = {
            "https://huggingface.co/papers/2610.14224.md": b"# Paper\n\nbody",
            "https://arctic-shift.photon-reddit.com/api/posts/ids?ids=abc123": json.dumps(
                {"data": [{"id": "abc123", "title": "Thread title", "selftext": "post body"}]}).encode(),
            "https://arctic-shift.photon-reddit.com/api/comments/tree?link_id=abc123&limit=100": json.dumps(
                {"data": [{"kind": "t1", "data": {"body": "low comment", "score": 3}},
                          {"kind": "t1", "data": {"body": "top comment", "score": 50}},
                          {"kind": "more", "data": {}}]}).encode(),
            "https://api.github.com/repos/unslothai/unsloth/readme": b"# Unsloth readme",
            "https://example.com/post/1": b"<html><body><p>Hello world</p><script>x()</script></body></html>",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, url, headers=None):
        self.calls.append(url)
        self.headers_seen[url] = dict(headers or {})
        if url not in self.routes:
            raise w.FetchError("HTTP 404")
        return self.routes[url]

    def read(self, urls, get=None):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            paths = w.read(urls, self.out, get or self.get, home=self.home)
        return paths, buf.getvalue()

    def test_routes(self):
        paths, _ = self.read(["https://arxiv.org/abs/2610.14224v2", "https://www.reddit.com/r/LocalLLaMA/comments/abc123/title/",
                              "https://github.com/unslothai/unsloth", "https://example.com/post/1"])
        self.assertEqual([p.name for p in paths],
                         ["2610.14224.md", "reddit-abc123.txt", "gh-unslothai-unsloth.md", "example-com-post-1.txt"])
        self.assertTrue(paths[0].read_text(encoding="utf-8").startswith("source: https://arxiv.org/abs/2610.14224v2\n\n"))
        reddit = paths[1].read_text(encoding="utf-8")
        self.assertIn("[50] top comment", reddit)
        self.assertLess(reddit.index("[50] top comment"), reddit.index("[3] low comment"))
        self.assertEqual(self.headers_seen["https://api.github.com/repos/unslothai/unsloth/readme"]["Accept"], "application/vnd.github.raw")
        self.assertNotIn("x()", paths[3].read_text(encoding="utf-8"))
        self.assertFalse(any(c.startswith(("https://www.reddit.com", "https://reddit.com")) for c in self.calls))

    def test_paper_without_markdown_falls_back_to_abstract(self):
        self.routes["https://huggingface.co/api/papers/2610.19789"] = json.dumps(
            {"id": "2610.19789", "title": "A Reality Check", "summary": "We compare ten methods.",
             "ai_summary": "MACHINE SUMMARY", "githubRepo": "https://github.com/aim-uofa/Self-Distillation-AgentRL"}).encode()
        paths, _ = self.read(["https://huggingface.co/papers/2610.19789"])
        self.assertEqual([p.name for p in paths], ["2610.19789.md"])
        text = paths[0].read_text(encoding="utf-8")
        self.assertIn("A Reality Check", text)
        self.assertIn("We compare ten methods.", text)
        self.assertIn("https://github.com/aim-uofa/Self-Distillation-AgentRL", text)
        self.assertNotIn("MACHINE SUMMARY", text)

    def test_geeknews_from_pull_cache_only(self):
        row = {"title": "GN story", "link": "https://news.hada.io/topic?id=1", "content": "summary text"}
        (self.home / "pull" / "geeknews.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        paths, printed = self.read(["https://news.hada.io/topic?id=1", "https://news.hada.io/topic?id=2"])
        self.assertEqual([p.name for p in paths], ["pulled-news-hada-io-topic-id-1.txt"])
        self.assertIn("summary text", paths[0].read_text(encoding="utf-8"))
        self.assertIn("skip https://news.hada.io/topic?id=2", printed)
        self.assertFalse(any("news.hada.io" in c for c in self.calls))

    def test_arxiv_link_reads_the_paper_not_the_cached_abstract(self):
        row = {"title": "Speech paper", "link": "https://arxiv.org/abs/2610.14224", "content": "cached abstract"}
        (self.home / "pull" / "arxiv-eess-AS.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        paths, _ = self.read(["https://arxiv.org/abs/2610.14224"])
        self.assertEqual([p.name for p in paths], ["2610.14224.md"])
        self.assertIn("# Paper", paths[0].read_text(encoding="utf-8"))

    def test_cached_abstract_is_the_last_resort_for_papers(self):
        row = {"title": "Speech paper", "link": "https://arxiv.org/abs/2610.00002", "content": "cached abstract"}
        (self.home / "pull" / "arxiv-eess-AS.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        paths, _ = self.read(["https://arxiv.org/abs/2610.00002"])
        self.assertEqual(len(paths), 1)
        self.assertIn("cached abstract", paths[0].read_text(encoding="utf-8"))

    def test_long_urls_do_not_share_a_file(self):
        base = "https://example.com/" + "x" * 80
        self.assertNotEqual(w._slug(base + "/one"), w._slug(base + "/two"))
        self.assertEqual(w._slug("https://example.com/post/1"), "example-com-post-1")

    def test_malformed_answer_skips_only_that_url(self):
        self.routes["https://arctic-shift.photon-reddit.com/api/posts/ids?ids=zzz999"] = b"[1, 2]"
        paths, printed = self.read(["https://www.reddit.com/r/LocalLLaMA/comments/zzz999/t/", "https://example.com/post/1"])
        self.assertEqual([p.name for p in paths], ["example-com-post-1.txt"])
        self.assertIn("skip https://www.reddit.com/r/LocalLLaMA/comments/zzz999/t/", printed)

    def test_skip_on_fetch_error(self):
        def failing_get(url, headers=None):
            raise w.FetchError("blocked by robots.txt")

        paths, printed = self.read(["https://blocked.com/x"], get=failing_get)
        self.assertEqual(paths, [])
        self.assertIn("skip https://blocked.com/x: blocked by robots.txt", printed)

import unittest
from datetime import date, timedelta, timezone
from tests._load import load

w = load("skills/weekly/scripts/weekly.py")
KST = timezone(timedelta(hours=9))
RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>A &amp; B</title><link>https://x.com/a</link><pubDate>Mon, 12 Oct 2026 01:00:00 GMT</pubDate><description>&lt;p&gt;hi&lt;/p&gt;</description></item>
<item><title>No date</title><link>https://x.com/b</link></item></channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Rel</title>
<link rel="alternate" href="https://g.com/r"/><updated>2026-10-13T00:00:00Z</updated><content type="html">&lt;a href="https://arxiv.org/abs/2610.00001"&gt;p&lt;/a&gt;</content></entry></feed>"""


class CoreTest(unittest.TestCase):
    def test_week_bounds(self):
        s, e = w.week_bounds("2026-W42", KST)
        self.assertEqual((s.isoformat(), e.isoformat()), ("2026-10-12T00:00:00+09:00", "2026-10-19T00:00:00+09:00"))

    def test_week_53(self):
        s, e = w.week_bounds("2026-W53", KST)
        self.assertEqual((s.date(), e.date()), (date(2026, 12, 28), date(2027, 1, 4)))
        with self.assertRaises(ValueError):
            w.week_bounds("2025-W53", KST)
        with self.assertRaises(ValueError):
            w.parse_week("2026-42")

    def test_last_finished_week(self):
        self.assertEqual(w.last_finished_week(date(2026, 10, 26)), "2026-W43")
        self.assertEqual(w.last_finished_week(date(2026, 10, 25)), "2026-W42")
        self.assertEqual(w.last_finished_week(date(2027, 1, 4)), "2026-W53")

    def test_parse_date(self):
        a = w.parse_date("Sun, 18 Oct 2026 15:30:00 GMT")
        self.assertEqual(a.astimezone(KST).isoformat(), "2026-10-19T00:30:00+09:00")
        self.assertEqual(w.parse_date("2026-10-18T15:30:00Z"), a)
        self.assertIsNone(w.parse_date("not a date"))

    def test_feed_entries(self):
        r = w.feed_entries(RSS)
        self.assertEqual([x["title"] for x in r], ["A & B", "No date"])
        self.assertIsNone(r[1]["date"])
        a = w.feed_entries(ATOM)[0]
        self.assertEqual(a["link"], "https://g.com/r")
        self.assertEqual(w.hrefs(a["html"]), ["https://arxiv.org/abs/2610.00001"])

    def test_feed_rejects_doctype(self):
        with self.assertRaises(ValueError):
            w.feed_entries(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><rss></rss>')

    def test_ids(self):
        for u in ["https://arxiv.org/abs/2610.14224v2", "https://arxiv.org/pdf/2610.14224",
                  "https://huggingface.co/papers/2610.14224", "https://www.alphaxiv.org/abs/2610.14224"]:
            self.assertEqual(w.arxiv_id(u), "2610.14224")
        self.assertIsNone(w.arxiv_id("https://example.com/2610.14224"))
        self.assertEqual(w.github_repo("https://github.com/UnslothAI/Unsloth/tree/main/docs"), "unslothai/unsloth")
        self.assertEqual(w.github_repo("https://github.com/org/repo.git"), "org/repo")
        self.assertIsNone(w.github_repo("https://github.com/orgs/foo"))
        self.assertEqual(w.norm_url("https://www.Example.com/a/?utm_source=x&id=3#top"), "https://example.com/a?id=3")
        self.assertEqual(w.ident("https://github.com/Org/Repo/issues/3"), "github.com/org/repo")

    def test_clean_title_and_text(self):
        self.assertEqual(w.clean_title("New model \u2014 fast \U0001F680  release"), "New model - fast release")
        t = w.html_text("<p>Hi <a href='https://a.com'>a</a></p><script>bad()</script><ul><li>one</li></ul>")
        self.assertIn("Hi a", t)
        self.assertIn("one", t)
        self.assertNotIn("bad()", t)

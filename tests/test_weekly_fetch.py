import unittest
from tests._load import load

w = load("skills/weekly/scripts/weekly.py")


class FakeOpener:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        r = self.routes.get(url, (404, b""))
        return r.pop(0) if isinstance(r, list) else r


ALLOW = (200, b"User-agent: *\nDisallow:\n")


class FetchTest(unittest.TestCase):
    def make(self, routes, t=0.0):
        self.sleeps = []
        return w.Fetcher(opener=FakeOpener(routes), sleep=self.sleeps.append, clock=lambda: t)

    def test_ua_and_robots_allow(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": (200, b"ok")})
        self.assertEqual(f.get("https://a.com/x"), b"ok")
        self.assertEqual(f.opener.calls[-1][1]["User-Agent"], "phro-trend/0.2.0 (+https://github.com/ThatsHoon/phro-trend)")

    def test_robots_disallow(self):
        f = self.make({"https://a.com/robots.txt": (200, b"User-agent: *\nDisallow: /\n")})
        with self.assertRaisesRegex(w.FetchError, "robots.txt"):
            f.get("https://a.com/x")

    def test_robots_404_allows(self):
        f = self.make({"https://a.com/x": (200, b"ok")})
        self.assertEqual(f.get("https://a.com/x"), b"ok")

    def test_backoff_then_fail(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": [(429, b"")] * 4})
        with self.assertRaisesRegex(w.FetchError, "429"):
            f.get("https://a.com/x")
        self.assertEqual(self.sleeps, [2, 4, 8])

    def test_backoff_then_success(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": [(422, b""), (200, b"ok")]})
        self.assertEqual(f.get("https://a.com/x"), b"ok")
        self.assertEqual(self.sleeps, [2])

    def test_pacing(self):
        u = "https://arctic-shift.photon-reddit.com/api/x"
        f = self.make({"https://arctic-shift.photon-reddit.com/robots.txt": ALLOW, u: (200, b"1")})
        f.get(u)
        f.get(u)
        self.assertEqual(self.sleeps, [0.5])

    def test_size_cap(self):
        f = self.make({"https://a.com/x": (200, b"a" * (w.MAX_BYTES + 10))})
        self.assertEqual(len(f.get("https://a.com/x")), w.MAX_BYTES)

    def test_server_error_retried_then_success(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": [(500, b""), (200, b"ok")]})
        self.assertEqual(f.get("https://a.com/x"), b"ok")
        self.assertEqual(self.sleeps, [2])

    def test_server_error_gives_up(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": [(503, b"")] * 4})
        with self.assertRaisesRegex(w.FetchError, "HTTP 503"):
            f.get("https://a.com/x")
        self.assertEqual(self.sleeps, [2, 4, 8])

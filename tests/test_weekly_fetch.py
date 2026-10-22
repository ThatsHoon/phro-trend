import http.server, threading, unittest
from tests._load import load

w = load("skills/weekly/scripts/weekly.py")


class FakeOpener:
    """routes: url -> (status, body) or (status, body, location), or a list of those for successive calls."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        r = self.routes.get(url, (404, b""))
        r = r.pop(0) if isinstance(r, list) else r
        return r if len(r) == 3 else (*r, None)


ALLOW = (200, b"User-agent: *\nDisallow:\n")


class FetchTest(unittest.TestCase):
    def make(self, routes, t=0.0):
        self.sleeps = []
        return w.Fetcher(opener=FakeOpener(routes), sleep=self.sleeps.append, clock=lambda: t)

    def test_ua_and_robots_allow(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": (200, b"ok")})
        self.assertEqual(f.get("https://a.com/x"), b"ok")
        self.assertEqual(f.opener.calls[-1][1]["User-Agent"], f"phro-trend/{w.VERSION} (+https://github.com/ThatsHoon/phro-trend)")

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

    def test_redirect_checks_robots_of_the_new_host(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": (302, b"", "https://b.com/y"),
                       "https://b.com/robots.txt": (200, b"User-agent: *\nDisallow: /\n")})
        with self.assertRaisesRegex(w.FetchError, "막음"):
            f.get("https://a.com/x")
        self.assertNotIn("https://b.com/y", [u for u, _ in f.opener.calls])

    def test_relative_redirect_followed(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": (301, b"", "/z"), "https://a.com/z": (200, b"ok")})
        self.assertEqual(f.get("https://a.com/x"), b"ok")

    def test_redirect_to_other_scheme_refused(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": (302, b"", "ftp://a.com/f")})
        with self.assertRaisesRegex(w.FetchError, "ftp"):
            f.get("https://a.com/x")

    def test_redirect_loop_stops(self):
        f = self.make({"https://a.com/robots.txt": ALLOW, "https://a.com/x": (302, b"", "https://a.com/x")})
        with self.assertRaises(w.FetchError):
            f.get("https://a.com/x")
        self.assertLessEqual(len(f.opener.calls), 10)

    def test_robots_redirect_followed(self):
        f = self.make({"https://a.com/robots.txt": (301, b"", "https://www.a.com/robots.txt"),
                       "https://www.a.com/robots.txt": (200, b"User-agent: *\nDisallow: /\n")})
        with self.assertRaisesRegex(w.FetchError, "막음"):
            f.get("https://a.com/x")


class RealOpenerTest(unittest.TestCase):
    def test_urlopen_hands_redirects_back(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/r":
                    self.send_response(302)
                    self.send_header("Location", "/t")
                    self.end_headers()
                elif self.path == "/t":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://127.0.0.1:{srv.server_port}"
        res = w._urlopen(base + "/r", {})
        self.assertEqual(res[0], 302)
        self.assertEqual(res[2], "/t")
        self.assertEqual(w.Fetcher().get(base + "/r"), b"ok")

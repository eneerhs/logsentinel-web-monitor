import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import cli
from demo_server import DemoHandler
from monitor import classify, extract_page, fetch_page, validate_url

ROOT = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def running_server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.request_count = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/missing":
            self.send_error(404)
            return
        body = b"<title>Example &amp; Test</title><h1>OK</h1>"
        content_type = "text/html; charset=utf-8"
        if self.path == "/plain":
            content_type = "text/plain"
        elif self.path == "/charset":
            content_type = "text/html; charset=not-a-real-encoding"
        elif self.path == "/binary":
            body = b"<title>A\xffB</title>"
        elif self.path == "/large":
            body = b"x" * 300
        elif self.path == "/empty":
            body = b""
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/html")
        else:
            self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body) + (10 if self.path == "/short" else 0)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class ParserTests(unittest.TestCase):
    def test_title_entities_and_ignored_scripts(self):
        title, digest = extract_page("<title>A &amp; B</title><h1>Hello</h1><script>bad</script>")
        self.assertEqual(title, "A & B")
        self.assertEqual(digest, extract_page("<title>A &amp; B</title><p>Hello</p><script>different</script>")[1])

    def test_whitespace_is_normalized_but_real_text_changes(self):
        self.assertEqual(extract_page("<p>Hello   world</p>")[1], extract_page("<p>Hello\nworld</p>")[1])
        self.assertNotEqual(extract_page("<p>Hello</p>")[1], extract_page("<p>Goodbye</p>")[1])

    def test_empty_and_long_titles(self):
        self.assertEqual(extract_page("")[0], "(untitled)")
        self.assertEqual(len(extract_page("<title>" + "x" * 200 + "</title>")[0]), 120)

    def test_urls_reject_unsupported_schemes_credentials_ports_and_spaces(self):
        for value in ["file:///tmp/x", "javascript:alert(1)", "https:///x", "http://u:p@host/",
                      "http://host:bad/", "http://host:70000/", "http://host:0/", "http://host/a b", "http://[bad"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_url(value)
        self.assertEqual(validate_url("https://example.com/"), "https://example.com/")


class ClassificationTests(unittest.TestCase):
    def test_all_six_events(self):
        up = {"available": True, "fingerprint": "a"}
        changed = {"available": True, "fingerprint": "b"}
        down = {"available": False, "fingerprint": None}
        for previous, current, expected in [(None, up, "BASELINE"), (up, up, "UNCHANGED"),
                (up, changed, "CONTENT_CHANGED"), (up, down, "UNAVAILABLE"),
                (None, down, "UNAVAILABLE"), (down, down, "STILL_UNAVAILABLE"),
                (down, up, "RECOVERED")]:
            with self.subTest(expected=expected):
                self.assertEqual(classify(previous, current), expected)


class FetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_context = running_server(FixtureHandler)
        cls.url = cls.server_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.server_context.__exit__(None, None, None)

    def test_real_http_html_and_redirect(self):
        for path in ["/html", "/redirect"]:
            with self.subTest(path=path):
                result = fetch_page(self.url + path, 2)
                self.assertTrue(result["available"])
                self.assertEqual(result["status"], 200)
                self.assertEqual(result["title"], "Example & Test")

    def test_http_error_keeps_status(self):
        result = fetch_page(self.url + "/missing", 2)
        self.assertFalse(result["available"])
        self.assertEqual(result["status"], 404)

    def test_non_html_unknown_encoding_and_truncated_body(self):
        for path in ["/plain", "/charset", "/short"]:
            with self.subTest(path=path):
                result = fetch_page(self.url + path, 2)
                self.assertFalse(result["available"])
                self.assertTrue(result["error"])

    def test_size_limit(self):
        with patch("monitor.MAX_BYTES", 100):
            result = fetch_page(self.url + "/large", 2)
        self.assertFalse(result["available"])
        self.assertIn("1 MiB", result["error"])

    def test_bad_utf8_replaced_and_empty_html_allowed(self):
        self.assertTrue(fetch_page(self.url + "/binary", 2)["available"])
        self.assertEqual(fetch_page(self.url + "/empty", 2)["title"], "(untitled)")

    def test_timeout_becomes_a_result(self):
        with patch("monitor.urlopen", side_effect=TimeoutError("timed out")):
            result = fetch_page(self.url + "/html", 0.1)
        self.assertFalse(result["available"])
        self.assertIn("timed out", result["error"])


class CliTests(unittest.TestCase):
    def command(self, *args):
        return subprocess.run([sys.executable, "cli.py", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=15)

    def test_help(self):
        result = self.command("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--interval", result.stdout)

    def test_invalid_arguments(self):
        for option, value in [("--checks", "0"), ("--checks", "1.5"), ("--checks", "101"),
                              ("--interval", "nan"), ("--interval", "-1"), ("--timeout", "inf"),
                              ("--checks", "9" * 1000)]:
            with self.subTest(option=option, value=value):
                result = self.command("--url", "https://example.com", option, value)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.command("--url", "ftp://example.com").returncode, 2)

    def test_single_success_returns_zero(self):
        with running_server(FixtureHandler) as url:
            result = self.command("--url", url + "/html")
        self.assertEqual(result.returncode, 0)
        self.assertIn("BASELINE", result.stdout)

    def test_demo_actual_cli_and_json_report(self):
        with running_server(DemoHandler) as url, tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            result = self.command("--url", url + "/", "--checks", "4", "--interval", "1",
                                  "--output", str(path))
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 2)
        self.assertEqual([r["event"] for r in data["checks"]],
                         ["BASELINE", "CONTENT_CHANGED", "UNAVAILABLE", "RECOVERED"])
        self.assertEqual(result.stdout.count("ALERT:"), 3)
        self.assertNotIn("Traceback", result.stderr)

    def test_changed_only_returns_one_and_scheduler_sleeps_between_checks(self):
        with running_server(DemoHandler) as url, patch("cli.time.sleep") as sleep:
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["--url", url, "--checks", "2", "--interval", "3"])
        self.assertEqual(code, 1)
        sleep.assert_called_once_with(3)

    def test_existing_output_is_preserved_before_network_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "existing.txt"
            path.write_text("keep", encoding="utf-8")
            with patch("cli.fetch_page") as fetch, contextlib.redirect_stderr(io.StringIO()):
                code = cli.main(["--url", "http://example.com", "--output", str(path)])
            self.assertEqual(code, 2)
            fetch.assert_not_called()
            self.assertEqual(path.read_text(), "keep")

    def test_missing_output_folder_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.command("--url", "https://example.com", "--output", str(Path(folder)/"no"/"out.json"))
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_keyboard_interrupt(self):
        with patch("cli.fetch_page", side_effect=KeyboardInterrupt), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["--url", "https://example.com"]), 130)

    def test_terminal_control_characters_are_escaped(self):
        fake = {"available": True, "status": 200, "title": "\x1b[31mred", "fingerprint": "a"}
        output = io.StringIO()
        with patch("cli.fetch_page", return_value=fake), contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(["--url", "https://example.com"]), 0)
        self.assertNotIn("\x1b", output.getvalue())
        self.assertIn("\\u001b", output.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Loopback-only classroom demo: healthy, changed, unavailable, recovered."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        self.server.request_count += 1
        sequence = [(200, "Operational"), (200, "Maintenance"),
                    (503, "Unavailable"), (200, "Operational")]
        status, title = sequence[min(self.server.request_count - 1, 3)]
        body = f"<!doctype html><html><title>{title}</title><body><h1>{title}</h1></body></html>".encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        with ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler) as server:
            server.request_count = 0
            print(f"Demo ready: http://127.0.0.1:{args.port}/ (Ctrl+C to stop)", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

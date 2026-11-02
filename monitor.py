"""Fetch HTML, extract text, and classify changes using the standard library."""

import hashlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_BYTES = 1024 * 1024


def validate_url(value):
    try:
        parts = urlsplit(value)
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError("Invalid port")
    except ValueError as error:
        raise ValueError("URL has an invalid host or port") from error
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("URL must start with http:// or https:// and include a host")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URLs containing login credentials are not supported")
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError("URL must not contain spaces or control characters")
    return value


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.text_parts = []
        self.in_title = False
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.ignored += 1
        if tag == "title" and not self.ignored:
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.ignored = max(0, self.ignored - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if not self.ignored:
            self.text_parts.append(data)
            if self.in_title:
                self.title_parts.append(data)


def extract_page(html):
    parser = PageParser()
    parser.feed(html)
    parser.close()
    title = " ".join(" ".join(parser.title_parts).split())[:120] or "(untitled)"
    text = " ".join(" ".join(parser.text_parts).split())
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return title, fingerprint


def fetch_page(url, timeout):
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "available": False, "status": None, "title": "",
        "fingerprint": None, "error": None,
    }
    try:
        request = Request(url, headers={"User-Agent": "LogSentinelWebMonitor/1.0",
                                        "Accept": "text/html, application/xhtml+xml"})
        with urlopen(request, timeout=timeout) as response:
            result["status"] = response.status
            if not 200 <= response.status < 300:
                raise ValueError(f"HTTP status {response.status}")
            if response.headers.get_content_type() not in ("text/html", "application/xhtml+xml"):
                raise ValueError("Response is not HTML")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("Page is larger than the 1 MiB limit")
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) != len(body):
                raise ValueError("Incomplete or invalid response body length")
            charset = response.headers.get_content_charset() or "utf-8"
            result["title"], result["fingerprint"] = extract_page(
                body.decode(charset, errors="replace")
            )
            result["available"] = True
    except HTTPError as error:
        result["status"] = error.code
        result["error"] = f"HTTP {error.code}"
        error.close()
    except (URLError, OSError, ValueError, LookupError, HTTPException) as error:
        result["error"] = str(error)
    return result


def classify(previous, current):
    if not current["available"]:
        return "UNAVAILABLE" if previous is None or previous["available"] else "STILL_UNAVAILABLE"
    if previous is None:
        return "BASELINE"
    if not previous["available"]:
        return "RECOVERED"
    if current["fingerprint"] != previous["fingerprint"]:
        return "CONTENT_CHANGED"
    return "UNCHANGED"

"""CLI: scheduled HTML checks and terminal notifications."""

import argparse
import json
import math
import sys
import time
from pathlib import Path

from monitor import classify, fetch_page, validate_url

ALERT_EVENTS = {"CONTENT_CHANGED", "UNAVAILABLE", "RECOVERED"}


def bounded_number(value, minimum, maximum, integer=False):
    try:
        number = int(value) if integer else float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected a number") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise argparse.ArgumentTypeError(f"Value must be between {minimum} and {maximum}")
    return number


def url_argument(value):
    try:
        return validate_url(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def build_parser():
    parser = argparse.ArgumentParser(description="Monitor a web page and print change/failure alerts.")
    parser.add_argument("--url", required=True, type=url_argument, help="HTTP(S) page URL")
    parser.add_argument("--checks", type=lambda v: bounded_number(v, 1, 100, True), default=1,
                        help="Number of checks, 1..100 (default: 1)")
    parser.add_argument("--interval", type=lambda v: bounded_number(v, 1, 3600), default=60,
                        help="Seconds to wait between completed checks (default: 60)")
    parser.add_argument("--timeout", type=lambda v: bounded_number(v, 0.1, 30), default=5,
                        help="Network-operation timeout in seconds (default: 5)")
    parser.add_argument("--output", help="Save JSON to a NEW file; existing files are never replaced")
    return parser


def run_checks(args):
    results = []
    previous = None
    for index in range(args.checks):
        current = fetch_page(args.url, args.timeout)
        current["event"] = classify(previous, current)
        results.append(current)
        status = current["status"] if current["status"] is not None else "NETWORK_ERROR"
        detail = current["title"] if current["available"] else current["error"]
        # Escape page-controlled text so terminal control sequences cannot execute.
        print(f"CHECK {index + 1}: HTTP {status} {current['event']} {json.dumps(detail, ensure_ascii=True)}")
        if current["event"] in ALERT_EVENTS:
            print(f"ALERT: {current['event']}")
        previous = current
        if index + 1 < args.checks:
            time.sleep(args.interval)
    return results


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.output:
            target = Path(args.output).expanduser()
            if target.exists():
                raise ValueError("Output already exists; choose a new filename")
            if not target.parent.is_dir():
                raise ValueError("Output parent folder does not exist")
        results = run_checks(args)
        if args.output:
            report = {"url": args.url, "interval_seconds": args.interval, "checks": results}
            with target.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
            print(f"SAVED: {args.output}")
        if any(not item["available"] for item in results):
            return 2
        return 1 if any(item["event"] in ALERT_EVENTS for item in results) else 0
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Stopped. Incomplete runs are not saved.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

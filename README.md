# LogSentinel Web Monitor

COE203 – Advanced Programming with Python, Istinye University. Project 2: Web Monitoring. Group: **Programmers**. Presentation: 4 November 2026.

## Business problem and scope

Operations staff should not have to repeatedly open a business website to notice a service failure or content update. This CLI fetches one HTML page, extracts its title/text, compares successive checks, and prints terminal alerts for changed content, failure, or recovery. It can save the completed run as JSON. This is a small course project, separate from Project 1's local log analyzer.

It demonstrates web requests, scraping/data extraction, automation, fixed-delay scheduling, notifications, functions, loops, dictionaries, conditionals, inheritance, context managers, hashing, JSON file I/O, argparse, and error handling. It uses Python's HTTP and HTML APIs, not an external JSON data API. Notifications are terminal messages, not email or push notifications.

## Installation

Install Python 3.9 or newer. Download/extract this repository or clone it, then open a terminal **inside this folder**. There are no third-party packages and no pip installation step.

```console
python --version
python cli.py --help
```

On Windows, replace `python` with `py` if needed. The classroom computer needs Python only for a live code demonstration; PowerPoint works independently.

## Every file

| File/folder | Purpose |
|---|---|
| `cli.py` | Validates CLI options, schedules checks, prints alerts, writes optional JSON, sets exit status |
| `monitor.py` | URL validation, HTTP fetch, HTMLParser subclass, text normalization, SHA-256 fingerprint, change classification |
| `demo_server.py` | Localhost-only synthetic server for repeatable offline demonstration |
| `tests/test_monitor.py` | 20 unit and integration tests, including local HTTP requests and real CLI subprocesses |
| `contributions/` | Identity-filled member records; members must confirm their actual Project 2 work before submission |
| `contributions/Anir_N_T_Elhasairi_2309116564_eneerhs.md` | Anir's preparation/assistance record |
| `contributions/Çınar_Sabancı_2409115637_cyh77.md` | Çınar's Project 2 record requiring actual-work confirmation |
| `contributions/Asaad_Asaad_2409115584_asaadalabsi.md` | Asaad's Project 2 record requiring actual-work confirmation |
| `contributions/Bashir_Alzoubi_2409115364_GITHUB_USERNAME_PENDING.md` | Bashir's record; GitHub username and actual work need confirmation |
| `.gitignore` | Keeps caches, local environments, credentials, archives, and generated report files out of Git |
| `README.md` | Setup, commands, behavior, demonstration, tests, and limits |

The PowerPoint, speaking script, Q&A, study guide, and submission checklist are delivered separately to keep the implementation repository concise.

## Commands

```console
python cli.py --url https://example.com/
python cli.py --url https://example.com/ --checks 3 --interval 60 --timeout 5
python cli.py --url https://example.com/ --checks 3 --interval 60 --output report.json
```

| Argument | Meaning | Default / allowed values |
|---|---|---|
| `--url` | Page to fetch | Required HTTP(S) URL; embedded login credentials and spaces/control characters rejected |
| `--checks` | Finite number of checks | 1; integer 1–100 |
| `--interval` | Wait after each completed check except the last | 60 seconds; finite number 1–3600 |
| `--timeout` | Network-operation timeout | 5 seconds; finite number 0.1–30 |
| `--output` | Save the completed run as JSON | Optional **new** file; parent directory must exist |
| `--help` | Describe arguments | Exit 0 |

Quote paths or URLs containing shell-special characters. Use a URL you are allowed to monitor and a considerate interval. Start with a single check. Reports can contain URLs and page titles, so do not commit real reports containing private information.

## How it works

1. Argparse converts and checks arguments before the first request. Existing output paths or missing output parent directories are rejected before fetching.
2. `fetch_page()` sends a GET request using `urllib.request`. Standard-library redirect handling applies. TLS certificate verification stays enabled. Network/HTTP errors become structured results so later scheduled checks can still run.
3. A usable check requires a successful 2xx HTML/XHTML response with a body of at most **1 MiB (1,048,576 bytes)**. A non-HTML response is unavailable for this tool even if its HTTP status is 200. A supplied Content-Length must match the downloaded body.
4. `PageParser`, a subclass of `HTMLParser`, extracts title/text while ignoring script, style, and noscript data. Text whitespace is normalized. SHA-256 produces a repeatable content fingerprint. It detects extracted-text changes, not HTML attribute/layout changes.
5. `classify()` compares the current result with the previous result in the **same run**. Availability is checked before comparing fingerprints.
6. `run_checks()` prints a summary and selected alert events. `time.sleep()` waits between completed checks, so check duration adds to the interval. This is fixed-delay scheduling, not a clock-precise background scheduler.
7. A completed run can be saved as JSON using exclusive `x` mode. Existing files are never replaced. Files are closed with context managers.

### Events and notifications

| Event | Meaning | ALERT line? |
|---|---|---|
| `BASELINE` | First usable check; establishes reference content | No |
| `UNCHANGED` | Usable page with the same extracted-text fingerprint | No |
| `CONTENT_CHANGED` | Usable page with a different fingerprint | Yes |
| `UNAVAILABLE` | First failed check, or transition from usable to failed | Yes |
| `STILL_UNAVAILABLE` | Another failed check after failure | No, suppresses repeated failure alerts |
| `RECOVERED` | Usable check immediately after failure | Yes |

Exit codes: **0** = all checks usable, no alert events; **1** = all checks usable, with a content-change alert; **2** = any unavailable check, argument error, or report/file error; **130** = Ctrl+C. A run with a failed check returns 2 even if a later check recovers. Report results distinguish a simulated server failure from a programming crash.

## Offline classroom demo (two terminals)

Open two terminals in this project folder. In terminal 1:

```console
python demo_server.py
```

Leave it running. In terminal 2:

```console
python cli.py --url http://127.0.0.1:8765/ --checks 4 --interval 1 --output demo-report.json
```

On a **freshly started** demo server this produces:

```text
CHECK 1: HTTP 200 BASELINE "Operational"
CHECK 2: HTTP 200 CONTENT_CHANGED "Maintenance"
ALERT: CONTENT_CHANGED
CHECK 3: HTTP 503 UNAVAILABLE "HTTP 503"
ALERT: UNAVAILABLE
CHECK 4: HTTP 200 RECOVERED "Operational"
ALERT: RECOVERED
SAVED: demo-report.json
```

Three alerts are expected. Exit code 2 is intentional because check 3 simulates HTTP 503. The server is synthetic and binds only to 127.0.0.1. It advances on every GET of `/`, so do not open that page in a browser before the run. Restart the server with Ctrl+C and `python demo_server.py` before repeating the sequence. If the output already exists, choose `demo-report-2.json`. If port 8765 is occupied, start with `python demo_server.py --port 8766` and use that port in the monitor URL.

## Tests

```console
python -m unittest discover -s tests -v
```

**20 tests passed** during preparation on 2 November 2026. They cover parser extraction, normalization, signatures, URL validation, all six event states, HTML requests/redirects, HTTP failures, page-size cap, malformed encodings, incomplete response length, CLI options, real scheduled demo runs/JSON output, all normal exit codes, output preservation, Ctrl+C, and escaping page-controlled terminal text. A timeout is injected in one test; the real local-server integration tests do not require internet.

The actual two-terminal demo commands were also run successfully. A separate HTTPS smoke check to example.com reported a certificate-trust failure on the preparation computer; the CLI safely recorded it as unavailable. A successful live HTTPS check was not confirmed there. Do not bypass certificate verification; use a Python installation with the appropriate trusted CA certificates, or use the offline demo for presentation.

## Limitations

- One URL per run, no JavaScript rendering, login sessions, external API credentials, or browser automation.
- First check starts a new baseline. Previous reports are not loaded as state. Current results stay in memory until a completed run is saved.
- Terminal notifications need an open process. There is no email/SMS delivery or operating-system job installation.
- Body bytes are bounded, but parsed strings/results use additional memory. The timeout applies to network operations, not a guaranteed total wall-clock deadline for an entire check.
- HTTP/charset/content failures are handled, but a heuristic text hash is not proof of an attack, a reliable uptime percentage, or a production monitoring service. Whitespace-only changes are normalized; dynamic page text can cause benign alerts.
- JSON creation protects existing files but is not an atomic write; an interrupted disk write can leave an incomplete **new** report.

## Team and submission

The finalized Members P2 course roster lists group **Programmers**: Çınar Sabancı (2409115637), Bashir Alzoubi (2409115364), Anir N T Elhasairi (2309116564), Asaad Asaad (2409115584). Anir is the planned solo presenter. Code, tests, documentation, and slides were prepared with Codex assistance; no individual member authorship is invented. Member contribution drafts must be completed truthfully and supported with actual work/commits. Bashir's GitHub username must be filled in and his file renamed to the professor's naming format.

The repository is being prepared as `eneerhs/logsentinel-web-monitor`. It must be public for submission after owner approval. Blackboard shows **4 November 2026, 14:00 (UTC+3)** as the P2 deadline, with late submissions disabled, and requests the GitHub URL plus PowerPoint. One primary submitter submits for the group. Keep this Project 2 separate from Project 1.

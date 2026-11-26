#!/usr/bin/env python3
"""Regression check for the 18+ age gate on App Lab cards.

For each live card, ticking #age-<slug> must remove is-disabled from every
.js-gated button (Join, Become a tester, Install, and I've joined & opted in),
and unticking must restore it.

Usage (from the repo root):

    python3 tests/age-gate.py

Optional:

    python3 tests/age-gate.py --root /path/to/site
    python3 tests/age-gate.py --port 0

Requires Python Playwright (pip install playwright && playwright install chromium).
This script is for local / CI use. It is not linked from the site.
"""

from __future__ import annotations

import argparse
import http.server
import os
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

LIVE_SLUGS = [
    "shrinkpro",
    "sparkquest-date-co-op-quests",
    "whispers-warnings",
    "oraculum-sacred-ai-tarot",
    "prismbook-booking-preview",
]


def launch_browser(playwright):
    """Prefer a system Chrome (this box has no bundled Playwright browser), then fall back."""
    exe = os.environ.get("CHROME_PATH")
    if exe:
        return playwright.chromium.launch(executable_path=exe, args=["--headless=new"])
    try:
        return playwright.chromium.launch(channel="chrome")
    except Exception:
        return playwright.chromium.launch()


def start_server(root: Path, port: int) -> tuple[http.server.ThreadingHTTPServer, int]:
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format, *args):
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def gated_state(page, slug: str) -> list[dict]:
    return page.evaluate(
        """(slug) => {
          const card = document.getElementById("app-" + slug);
          if (!card) return null;
          return Array.from(card.querySelectorAll(".js-gated")).map((btn) => ({
            text: (btn.textContent || "").trim(),
            disabled: btn.classList.contains("is-disabled"),
            aria: btn.getAttribute("aria-disabled")
          }));
        }""",
        slug,
    )


def assert_all(buttons: list[dict] | None, slug: str, locked: bool, when: str) -> None:
    if not buttons:
        raise AssertionError(f"{slug}: no .js-gated buttons found {when}")
    if len(buttons) < 4:
        raise AssertionError(
            f"{slug}: expected at least 4 gated controls (join, opt-in, install, check-in), "
            f"got {len(buttons)} {when}: {[b['text'] for b in buttons]}"
        )
    for btn in buttons:
        is_locked = btn["disabled"] is True and btn["aria"] == "true"
        is_unlocked = btn["disabled"] is False and btn["aria"] == "false"
        ok = is_locked if locked else is_unlocked
        if not ok:
            state = "locked" if locked else "unlocked"
            raise AssertionError(
                f"{slug}: {btn['text']!r} should be {state} {when}; "
                f"is-disabled={btn['disabled']} aria-disabled={btn['aria']!r}"
            )


def set_checkbox(page, selector: str, checked: bool) -> None:
    loc = page.locator(selector)
    if loc.count() == 0:
        raise AssertionError(f"missing checkbox {selector}")
    if checked:
        loc.check()
    else:
        loc.uncheck()


def run(root: Path, port: int) -> int:
    server, bound = start_server(root, port)
    url = f"http://127.0.0.1:{bound}/"
    failures = 0
    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector("#apps .app-card")

            for slug in LIVE_SLUGS:
                age = f"#age-{slug}"
                howto = f"#howto-{slug}-0"
                try:
                    if page.locator(age).count() == 0:
                        raise AssertionError(f"{slug}: missing {age}")
                    if page.locator(f"#app-{slug}").count() == 0:
                        raise AssertionError(f"{slug}: missing card")

                    initial = gated_state(page, slug)
                    assert_all(initial, slug, locked=True, when="on load")

                    # The howto checklist checkbox must not unlock the buttons
                    # (this was the production bug: the gate listened to the first checkbox).
                    if page.locator(howto).count():
                        set_checkbox(page, howto, True)
                        assert_all(
                            gated_state(page, slug),
                            slug,
                            locked=True,
                            when="after ticking the How-to-join checkbox",
                        )
                        set_checkbox(page, howto, False)

                    set_checkbox(page, age, True)
                    assert_all(
                        gated_state(page, slug),
                        slug,
                        locked=False,
                        when="after ticking #age-" + slug,
                    )

                    set_checkbox(page, age, False)
                    assert_all(
                        gated_state(page, slug),
                        slug,
                        locked=True,
                        when="after unticking #age-" + slug,
                    )
                    print(f"PASS  {slug}  ({len(initial)} gated controls)")
                except AssertionError as err:
                    failures += 1
                    print(f"FAIL  {slug}: {err}")

            browser.close()
    finally:
        server.shutdown()

    if failures:
        print(f"\n{failures} of {len(LIVE_SLUGS)} cards failed.")
        return 1
    print(f"\nAll {len(LIVE_SLUGS)} live cards passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Site root to serve (default: repo root)",
    )
    parser.add_argument("--port", type=int, default=0, help="Port (default: ephemeral)")
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "index.html").is_file():
        print(f"No index.html in {root}", file=sys.stderr)
        return 2
    return run(root, args.port)


if __name__ == "__main__":
    raise SystemExit(main())

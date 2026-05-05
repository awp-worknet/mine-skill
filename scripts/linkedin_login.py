"""Interactive LinkedIn login for macOS (no Xvfb needed).

Opens a real Chromium window, lets the user log in, then saves the storage
state to the same path mine-skill expects (`<output>/.sessions/linkedin.json`).
The miner's `_load_cookie_map` in crawler/platforms/linkedin.py reads from
this file and uses the `li_at` + `JSESSIONID` cookies for Voyager API calls.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


# Stable shared location read by scripts/agent_runtime.py and importable
# via `python -m crawler ... --cookies <path>`. This path persists across
# per-task output dirs, so a single login covers many runs.
DEFAULT_OUTPUT = Path.home() / ".openclaw" / "mine-skill" / "cookies" / "linkedin.json"
LOGIN_URL = "https://www.linkedin.com/login"
SUCCESS_HOST_PATHS = ("/feed", "/in/", "/mynetwork", "/jobs")


def wait_for_login(page, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        url = page.url or ""
        cookies = page.context.cookies("https://www.linkedin.com")
        has_li_at = any(c.get("name") == "li_at" and c.get("value") for c in cookies)
        if has_li_at and any(p in url for p in SUCCESS_HOST_PATHS):
            return True
        if has_li_at and "linkedin.com" in url and "/login" not in url and "/checkpoint" not in url:
            return True
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive LinkedIn login (macOS-friendly).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Where to save storage_state.json (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Seconds to wait for login (default: 600)")
    parser.add_argument("--also-write", type=Path, action="append", default=[],
                        help="Additional path(s) to copy the storage state to.")
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"[login] opening Chromium → {LOGIN_URL}")
    print(f"[login] storage will be saved to: {output}")
    print(f"[login] timeout: {args.timeout}s — login then wait for redirect to /feed")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        ok = wait_for_login(page, args.timeout)
        if not ok:
            print("[login] timeout waiting for login (no li_at cookie or wrong URL)", file=sys.stderr)
            context.close()
            browser.close()
            return 2

        context.storage_state(path=str(output))
        for extra in args.also_write:
            extra_path = extra.expanduser().resolve()
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(extra_path))
            print(f"[login] also wrote: {extra_path}")

        print(f"[login] OK — storage_state saved with li_at cookie")
        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Dreke20.github.io-app-testers
App testers

## Testing the 18+ gate

The regression check in `tests/` is for local or CI use. It is not linked from the site.

Requires Python Playwright (`pip install playwright`). The script uses a system Chrome if present (`channel=chrome`, or `CHROME_PATH`), otherwise `playwright install chromium`.

From the repo root:

    python3 tests/age-gate.py

It serves the site locally, opens each live app card, and checks that ticking `#age-<slug>` unlocks every `.js-gated` button and that unticking locks them again. It also checks that the How-to-join checklist checkbox does not unlock the buttons.

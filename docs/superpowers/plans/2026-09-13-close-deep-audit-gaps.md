# Close deep audit gaps

## Objective

Make ApplyPilot fail closed and keep working across iframe hosted forms, login redirects, and popup tabs while preserving privacy and deterministic resume identities.

## Implementation tasks

1. Add regression tests for browser frame and popup handling, platform re-detection after login, bounded stage transitions, login false positives, inspection failures, malformed filler results, and safe filler invocation.
2. Extend the Playwright page adapter to scan same-origin child frames, execute boolean detection scripts across frames, and select the newest live popup as the current page.
3. Refresh the page and application adapter after interactive handoff, and count only real stage transitions against the stage budget.
4. Make field inspection and filler results fail closed; remove TypeError based filler retries; scope searchable option selection to actual option nodes.
5. Normalize volatile job URL parameters and profile aliases before deriving IDs; redact sensitive URL parameters in audit events and snapshots.
6. Update README and the deep-audit record with the supported behavior and verification results.

## Verification

Run targeted regression tests first, then `uv run --python 3.11 pytest -q` and `uv run --python 3.14 pytest -q`, followed by compile, lock, and package checks. Commit and push the verified changes to `origin/main`.

# SkellForge packaging reconciliation — 2026-11-22

## Sources preserved

- Current `main` at `b52c5db1d8585f52b40930692de3c22fce431259` includes merged [symlink-boundary audit PR #30](https://github.com/skellyruno/skellforge/pull/30) and the root shared `AGENTS.md`.
- Cumulative strict moduleinfo/packaging source: [PR #29](https://github.com/skellyruno/skellforge/pull/29), commit `3c355da5a686167ed6eac256e6c6faf401f9fea1`, dependent on [PR #23](https://github.com/skellyruno/skellforge/pull/23).
- Independent structural AMD64 PE32+ package verifier: [PR #15](https://github.com/skellyruno/skellforge/pull/15), head `5bbbf97faf38f1def89cb91a4fa39714b51baa8c`.
- This direct-`main` draft integration does not rewrite, close or delete any source branch.

## Conflict decisions

- `skellforge/forge.py`: retain parent #23/#29 strict moduleinfo parsing, duplicate key rejection, expected factory classes and IDs, symlink/package safeguards, SHA-256 sidecar, non-overwrite/cleanup; additionally reject fake, x86, malformed or non-PE32+ binaries using structural PE validation from #15. Reject non-finite JSON constants.
- `skellforge/audit.py`: retain cumulative comment-aware parameter/range/formats migration analysis; carry forward #30's **no symlink traversal and in-root CMake** protections into `scan_parameter_ids`, `find_parameter_ranges`, `find_string_literals` and root CMake inspection. Mark string-literal scans inconclusive if paths are unsafe.
- `tests/test_forge.py`: preserve existing generated-plugin tests, #29 metadata normalization and #30 symlink tests; add fake/x86/PE32 validation cases.
- `tests/test_hardening.py` and `tests/test_uploaded_cli.py`: replace old fake binary success fixtures with **minimal non-runnable PE-shaped test fixtures**, so the stricter packager can be tested without claiming that a fake test file is a plugin.
- Root `AGENTS.md` from current main is preserved. No installed plugin code, VST3 class IDs, automation IDs, presets, user project files or existing preview ZIPs were changed.

## Acceptance

- Required: newly triggered exact-head Windows/Ubuntu CLI and generated Windows VST3 smoke CI; verify parser tests, fake/32bit rejection, symlink regression, CRC/sha256 and moduleinfo. No commercial release approval or FL Studio validation is claimed.
- Historical individual branch CI results are **not sufficient** for this synthesized aggregate.
- Preserve predecessors until the cumulative candidate is verified, and do not merge this draft automatically.

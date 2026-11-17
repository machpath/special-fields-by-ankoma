# Special Fields by Ankoma (Anki add-on)

> **Status: in development.** Not released, and not yet tested inside a real Anki install. Don't use it on a collection you care about.

Working folder for the Special Fields by Ankoma add-on: it protects users' own edits when they import an updated deck. It is built for Ankoma and works with any deck.

- Project plan (live doc): https://claude.ai/artifact/WRPTYrPKMD8wYQ9e66bSSq
- Update walkthrough (design canvas): https://claude.ai/artifact/DTSAP1wSdY24Khwi5vHxCx

## Folders

- `research/spike/`: technical investigation (2026-11-16)
  - `SPIKE_REPORT.md`: findings, the Anki version matrix and risks
  - `poc/`: prototype code and test logs. The prototype passed 18/18 checks on Anki 25.02.7, 25.07.5, 25.09.5, 26.09.4 and 26.11b1.
  - `poc/ankoma_special_fields.ankiaddon`: prototype build. **For testing only, not for release.** Try it only on a copy of an Anki profile.

**Resuming the build in a new chat? Start with `HANDOFF.md`.**

- `HANDOFF.md`: current status and how to pick the build up
- `docs/CONTRACT.md`: the spec the code is built to
- `src/special_fields_by_ankoma/`: the add-on's source
- `tests/`, `tools/`: automated tests and the scripts that run them on each Anki version

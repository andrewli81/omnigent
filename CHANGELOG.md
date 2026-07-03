# Changelog

All notable user-facing changes to omnigent are documented here. This file is
generated at release time from each PR's `## Changelog` section, tagged by the
PR's `Type of change` (e.g. `[UI]`); the concise, curated highlights live on the
website under `/releases`.

## [v0.4.0] — 2026-07-03

- [Feature] Added: automated changelog — merged PRs flow into a per-version `CHANGELOG.md` and a curated release post on the docs site (#1763)
- [UI] Changed: The delete icon for archived sessions is now red to signal it's a destructive action (#1786)
- [UI / Bug fix] Fixed: SmartRoutingCard no longer shows "· unavailable" for `sys_advise_models` calls made through the claude-sdk harness (#1797)
- [Chore] PR changelog entries are now a plain one-line description tagged by the "Type of change" boxes (e.g. `[UI]`); the section is optional and deletable when a change isn't noteworthy (#1826)
- [Chore] Manual runs of the changelog draft workflow can now preview an arbitrary commit range (`base..tag`) without a real version tag, printing the result to the run summary (#1832)
- [UI / Bug fix] Fixed: pinning a session now auto-expands the sidebar's Pinned section so the pinned chat is immediately visible (#1836)
- [Bug fix] Fixed: release draft creation no longer fails on large PR ranges, and manually-drafted dev/rc tags now produce correctly-ordered CHANGELOG.md entries (#1841)
- [Bug fix] Fixed: release-cut automation now correctly detects and enriches the draft GitHub Release (drafts are invisible to read-only tokens and unaddressable by tag) (#1845)
- [Bug fix] Comments on rendered HTML files now anchor to the copy of repeated text you actually selected, even when it appears in attributes or wraps across source lines. (#1850)
- [UI] Agent info panel now shows a subtle divider between each section, making it easier to scan session details at a glance. (#1852)
- [UI / Bug fix] Fixed: The inbox no longer shows comments you wrote yourself — only comments left by other people on shared sessions appear. (#1854)
- [UI / Bug fix] Fixed: Aligned the expanded terminal card's top edge with the workspace rail. (#1885)

## [v0.3.0] — 2026-06-26

Highlights and full notes: <https://github.com/omnigent-ai/omnigent/releases/tag/v0.3.0>

## [v0.2.0] — 2026-06-19

Highlights and full notes: <https://github.com/omnigent-ai/omnigent/releases/tag/v0.2.0>

## [v0.1.1] — 2026-06-16

Predates the automated changelog. See the Git history for `v0.1.0..v0.1.1`.

## [v0.1.0] — 2026-06-13

First tagged release.

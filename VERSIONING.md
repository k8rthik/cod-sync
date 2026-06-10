# Versioning Protocol

This project follows [Semantic Versioning](https://semver.org/) — `MAJOR.MINOR.PATCH` — with the rules below adapted to a CLI that writes files Cockatrice reads. This document is the source of truth for human and AI contributors. If a change doesn't fit cleanly into one tier, pick the higher one.

## The contract we version

Three things are part of the public surface and any change to them needs a version bump:

1. **CLI contract** — the positional grammar (`cod-sync TARGET [URL]`), flag names and shapes, exit codes, and stdout/stderr conventions that a scripted caller relies on.
2. **`.cod` file contract** — what we write into the file: card names, zone layout, source-URL marker, banner, deckname, comment markers. Cockatrice must keep reading what we write.
3. **Cache contract** — `~/.cache/cod-sync/alt_names.json` schema and the `COD_SYNC_*` env vars that control it.

Internals (module layout, function signatures, test helpers, refresh scripts) are not part of the contract and don't drive version bumps on their own.

## Bump rules

### MAJOR — breaking

Bump MAJOR when a downstream consumer following the previous documented contract will break on upgrade without changing how they call us. Examples:

- A CLI flag is removed or renamed (not added).
- A positional argument's meaning changes (e.g. `cod-sync URL` used to error on existing file, but the new behavior overwrites it silently).
- The `.cod` output changes in a way Cockatrice or a prior cod-sync version can't read.
- The alt-name cache file's schema changes incompatibly (new versions ignore old cache, or vice versa).
- A `COD_SYNC_*` env var is removed or its semantics inverted.
- Python minimum version is raised.

MAJOR bumps require a note in the commit body explaining what breaks and what users do about it. Pre-1.0 we still follow these rules — we don't hide breakage behind the `0.x` excuse.

### MINOR — user-visible additive or behavioral change

Bump MINOR when behavior the user can observe changes, but a caller following the previous contract still works. Examples:

- A new flag, subcommand, or source module.
- A bug fix that changes what gets written to disk (e.g. the DFC stripping fix — cached values flip, deck contents flip on next sync).
- A new prompt, a new printed message, a new exit code added (not removed).
- A previously-erroring path now succeeds (e.g. `cod-sync URL` now syncs the existing default-named file instead of refusing).
- New configuration knob added (env var, config field).
- New optional dependency or platform supported.

The two changes in v0.8.0 are textbook MINOR: one changes what lands in the .cod (DFC behavior fix), one changes a CLI path from error to success (bare-URL UX).

### PATCH — invisible to a careful user

Bump PATCH when behavior is unchanged from the user's perspective. Examples:

- Performance improvement with identical output.
- Internal refactor.
- Test-only changes.
- Documentation, comments, type annotations.
- Dependency bump that doesn't change behavior.
- A bug fix where the previous behavior was clearly broken (crash, malformed output) and the fix produces the obviously-correct result that anyone would expect.

The line between PATCH and MINOR bug fixes is the **expectation test**: would a reasonable user have *expected* the new behavior all along? If yes (crash → no crash; obviously-wrong output → obviously-right output), PATCH. If they had to learn the new behavior or could have built around the old one, MINOR.

## Decision tree

```
Does the change alter the CLI grammar, .cod output, or cache schema?
├─ No  → does it change any observable behavior?
│        ├─ No  → PATCH
│        └─ Yes → was the prior behavior obviously broken?
│                 ├─ Yes → PATCH
│                 └─ No  → MINOR
└─ Yes → does the prior documented usage still work?
         ├─ Yes → MINOR
         └─ No  → MAJOR
```

## Mechanics

A version bump touches **two files** and only these two:

- `pyproject.toml` — `version = "X.Y.Z"`
- `cod_sync/__init__.py` — `__version__ = "X.Y.Z"`

Both must match exactly. CI does not enforce this yet; reviewers do.

### When to bump

Bump in the same commit (or commit pair) that introduces the change. Don't accumulate unreleased changes against the current version — every push to `main` that ships user-visible work should leave the version reflecting what's on `main`.

A common pattern: the change itself in one commit, then `chore: bump version to X.Y.Z` immediately after. Both go out in one push. This keeps blame clean (the version-bump commit is trivially reviewable) and keeps `main` always describing itself accurately.

### Commit message conventions

Bumps use `chore:` prefix:

```
chore: bump version to 0.8.0
```

The body should list the user-visible changes that justify the tier. For a MAJOR bump, the body must include a migration note.

### Pre-1.0 stance

We are pre-1.0 today (`0.x.y`). We still follow the rules above — pre-1.0 is not a license to ship breaking changes silently. The path to 1.0 is when the CLI grammar and `.cod` output have settled enough that we're willing to commit to the MAJOR contract for real.

## For AI agents specifically

Before bumping, an agent must:

1. **Read the diff.** The bump tier is a function of what changed, not what the agent intended to change. Use `git diff` and classify against the rules above.
2. **Check both files.** Forgetting to update `cod_sync/__init__.py` after `pyproject.toml` (or vice versa) is the most common bug. Grep before pushing: `grep -n "0\\.[0-9]" pyproject.toml cod_sync/__init__.py`.
3. **Never bump version in the same commit as feature work** unless explicitly told to. A separate `chore: bump version` commit makes the bump easy to revert or amend if the tier turns out to be wrong.
4. **Ask, don't guess, on edge cases.** If the change sits between MINOR and PATCH, surface the tradeoff via `AskUserQuestion` rather than picking silently. The cost of asking is one round-trip; the cost of a wrong tag is permanent.
5. **Don't bump for in-progress work.** Only bump when the changes are being pushed to `main`. Bumping for a WIP branch creates phantom versions in the git history that never ship.
6. **Don't tag releases** (`git tag`) unless explicitly told. Tagging is a deliberate human action coupled to release announcements.

## Historical reference

| Version | Tier   | What changed                                                                 |
|---------|--------|------------------------------------------------------------------------------|
| 0.11.3  | PATCH  | `alt_name`'s module-level state (`_disk_cache`, `_session`, warn-once flag) is now guarded by a lock: lazy init, cache mutation, and disk writes are serialized, with the lock never held across Scryfall HTTP. Invisible to the single-threaded CLI; makes the library safe for multi-threaded embedding and unblocks parallel Scryfall batches. |
| 0.11.2  | PATCH  | Defensive guard in the `--info` quantity-column width (`max(..., default=1)`) so an empty totals set can never raise; regression test locks all-zero-quantity zone rendering. No observable behavior change. |
| 0.11.1  | PATCH  | Alt-name disk-cache write failures now warn on stderr (once per process) instead of failing silently — an unwritable cache previously re-paid the Scryfall round-trip every run with no clue why. User-confirmed PATCH: failure-path visibility fix, no contract surface touched. |
| 0.11.0  | MINOR  | Directory walk now prompts on deckname mismatches the way single-file sync already did, instead of silently ignoring them. `_sync_deck`'s per-mode policy knobs were deleted; sync, import, and walk share one identical per-deck code path. `-y` still means accept-all in every mode. |
| 0.10.0  | MINOR  | Source-fetch failures now render type-specific messages (deck-not-found, private, rate-limited, server-error, network, malformed-response, invalid-source) instead of a single collapsed "failed to fetch" line, so the message tells the user what to do about it. Exit codes unchanged. |
| 0.9.0   | MINOR  | Deck-level tags now sync from the remote into the .cod's `<tags>` block (Archidekt `deckTags`, Moxfield `hubs`), unioned with local tags so user-added tags survive. Previously the field was round-tripped but never populated from upstream. |
| 0.8.1   | PATCH  | Diff now surfaces stale "Front // Back" local entries as remove + add so pre-0.8.0 .cod files heal to the front face on next sync. Prior behavior actively suppressed the heal — qualifies as PATCH per the "obviously broken" rule. |
| 0.8.0   | MINOR  | DFC names always stripped to front face at alt_name boundary (fixes Scryfall-introduced regression); `cod-sync URL` now syncs the existing default-named file instead of refusing. |
| 0.7.x   | PATCH  | Performance work on alt_name; restored Scryfall fallback for reskins outside the bundled seed. |

Older versions predate this document.

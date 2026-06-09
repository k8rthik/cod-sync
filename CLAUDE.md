# CLAUDE.md

Instructions for AI agents working in this repo. Read before committing or bumping versions.

## Committing and pushing

### When to commit and push

Only commit when the user explicitly asks ("commit", "ship it", "push your changes"). Do not commit proactively after finishing an edit — the user often wants to review, run, or amend first.

When the user says "commit", that does not automatically include "push". When they say "push", that does include committing whatever was staged. When in doubt, ask.

### Scope: only commit your own changes

The working tree often contains parallel work that the user is doing in another session — type annotations, new flags, CI config, etc. **Do not bundle that work into your commits unless the user explicitly says to.** Before staging:

1. Run `git status` and `git diff` and identify which files you actually touched this session.
2. Stage only those files explicitly by path. Never use `git add -A`, `git add .`, or `git commit -a`.
3. If a file you edited *also* received unrelated changes from a linter or another process (common with `from typing import Any` showing up in your edited files), revert the unrelated portion via Edit before staging — your commit should contain only your change.
4. If you can't cleanly separate, ask the user via `AskUserQuestion` whether to bundle or split.

### Commit structure

- **One concern per commit.** A bug fix and an unrelated refactor are two commits, even if you discovered them in the same session.
- **Feature/fix work and version bumps are always separate commits.** Per `VERSIONING.md`, the bump is its own trivial-to-review `chore: bump version to X.Y.Z` commit immediately following the feature commit.
- **Conventional Commits prefix**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `ci:`. The body explains *why*, not what — the diff already shows what.
- **No `Co-Authored-By` attribution.** This repo's `~/.claude/settings.json` disables it globally.
- **Use a HEREDOC for multi-line messages** so formatting survives shell quoting:
  ```
  git commit -m "$(cat <<'EOF'
  fix: <short summary>

  <body>
  EOF
  )"
  ```

### Pushing

- Push only to `main` and only after the user asks.
- Never `--force` push. Never push to a branch other than `main` unless asked.
- After pushing, report the commit-range delta (`old..new`) so the user can verify what landed.

### Pre-push checklist

Before pushing, in this order:

1. `python -m ruff check` — must be clean.
2. `python -m ruff format --check` — must be clean.
3. `python -m mypy` — must be green.
4. `python -m pytest -q` — must be green. Report the count.
5. `git status` — confirm you're only pushing what you intend to push.
6. `grep -n "0\.[0-9]" pyproject.toml cod_sync/__init__.py` — confirm both version strings match.

If anything is red, fix it before pushing. Do not skip hooks (`--no-verify`) to get a push through. The pre-commit + pre-push hooks (see `.pre-commit-config.yaml`) run the same gates locally; CI re-runs them on push.

## Versioning

**Source of truth: `VERSIONING.md`.** Read it before any bump. Below is the operational summary; the protocol document is authoritative.

### When to bump

Bump in the same push as the user-visible change that justifies it — never accumulate unreleased changes against the current version. Every push to `main` that ships user-visible work should leave the version reflecting what's on `main`.

### Picking the tier

Use the decision tree in `VERSIONING.md`. Quick reference:

- **MAJOR** — breaking change to the CLI grammar, the `.cod` output format, or the `~/.cache/cod-sync/alt_names.json` schema. Anything a downstream consumer following the previous documented contract would notice as a break.
- **MINOR** — user-visible additive or behavioral change that doesn't break the contract. New flag, new source, a previously-erroring path now succeeds, a bug fix that flips what gets written to disk in a way users have to learn.
- **PATCH** — invisible to a careful user, or a fix where the prior behavior was *obviously* broken and the new behavior is what anyone would have expected.

When the tier is genuinely ambiguous (most often: is this PATCH or MINOR?), surface the tradeoff via `AskUserQuestion`. Do not guess silently — a wrong tag is permanent.

### Mechanics

A bump touches **exactly two files**:

- `pyproject.toml` — `version = "X.Y.Z"`
- `cod_sync/__init__.py` — `__version__ = "X.Y.Z"`

Both must match exactly. Verify before pushing:

```
grep -n "0\.[0-9]" pyproject.toml cod_sync/__init__.py
```

Also update the **historical reference table** at the bottom of `VERSIONING.md` with a one-line entry for the new version: tier and what changed in plain language. This is what future readers (human or AI) will scan to understand the project's release history.

### The bump commit

The bump is a separate commit, immediately after the feature/fix commit, in the same push. Message format:

```
chore: bump version to X.Y.Z

<TIER> per VERSIONING.md: <one-sentence justification referencing what
changed and why that maps to this tier>
```

Keep the body short — the feature commit explains the change in detail; the bump commit explains the tier choice.

### What not to do

- Never bump on a WIP branch that isn't about to land on `main` — phantom versions in the history that never ship.
- Never run `git tag` unsupervised — tagging is coupled to release announcements and is a deliberate human action.
- Never bump without updating both files. The most common bump bug is forgetting `cod_sync/__init__.py`.
- Never bump in the same commit as feature work. Reverting a tier mistake becomes painful if it's tangled with the fix.

## Project-specific notes

- The CLI's public contract surface is documented in `VERSIONING.md` under "The contract we version" — CLI grammar, `.cod` output, cache schema. Changes touching any of those need careful tier classification.
- The `_seed_data.py` file is a generated artifact from `scripts/refresh_seed.py`. Don't hand-edit it; if a reskin mapping needs to change, fix the generator or the runtime alt_name layer.
- DFC normalization is layered: source fetchers strip first (`cod_sync/sources/*.py`), alt_name strips again at its output (`cod_sync/alt_name.py`), and `_reconcile_dfc_names` in `cod_sync/diff.py` handles any residual mismatch between local and remote. Front-face-only is the canonical shape everywhere — Cockatrice cannot read the full `Front // Back` form.

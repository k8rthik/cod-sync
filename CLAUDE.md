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
- Multi-face name shaping is layout-aware and layered: source fetchers shape first using the deck API's per-card `layout` (`cod_sync/sources/*.py`, via `dfc.cockatrice_name`), and the alt_name layer shapes Scryfall results the same way (`cod_sync/alt_name.py`). True DFCs (transform/modal_dfc) reduce to the front face; single-face multi-part cards (split/Rooms, aftermath, adventures/omens, prepare) keep the full `A // B` name — that's Cockatrice's own shape for them. The diff layer compares names verbatim and never reshapes; a stale local shape surfaces as a remove + add pair that heals the file on sync.

## Keeping TODO.md live

`TODO.md` is a working log, not an archive. Treat it as state that's expected to change as you work:

- **Starting a task that's in TODO.md** — re-read the item before acting on it; the gap may have drifted since it was written. If the description is still accurate, proceed; if it's stale, update or split it before starting.
- **Completing a task** — remove the corresponding TODO.md item in the same commit (or in a docs-cleanup commit within the same push). Done work doesn't belong in the open-work list. The `chore` / `docs` commit that lands the cleanup is the right home.
- **Unexpected gaps discovered mid-task** — a missing test, a bug adjacent to what you were fixing, a tooling smell, a doc that's now stale, an architectural inconsistency. Add it to TODO.md before context-switching away. Capture even small items: the next session won't have your in-context observation otherwise.
- **Intermediate findings worth tracking but not worth doing now** — design tensions, risky migrations ahead, things you noticed while reading code. Add them with enough context that they're actionable cold. If the right tier (P1 / P2) is unclear, default to P2 and surface it to the user.

Follow the existing intro convention: items describe the gap and why it matters, not the implementation. That's what keeps the doc from rotting when code moves.

## Local dev environment notes

Operational gotchas you'll hit mid-session if you're not prepared for them. CONTRIBUTING.md is the human-facing tour; the items below are agent-specific.

### Pre-commit hooks are armed

`pre-commit install` has been run in this clone, so commits trigger ruff (lint + format) and mypy, and pushes additionally run pytest. When a hook **auto-fixes** a file (ruff `--fix`, end-of-file-fixer, trailing-whitespace), the commit aborts and the fixes land in the working tree. **Always re-stage the fixed paths and re-commit** — don't `--amend` (the prior commit didn't happen) and don't `--no-verify` to shove it through.

If you see "files were modified by this hook" — the hook did the work for you; just `git add` the changes and re-run the commit. The hook will pass on the second try.

### Format-version drift between local ruff and the hook

`pyproject.toml`'s dev dep is `ruff>=0.6` (floats to latest); `.pre-commit-config.yaml` pins a specific ruff version via `ruff-pre-commit`'s `rev:`. If those drift far apart, `ruff format` will produce different output between your local install and the pre-commit hook — visible as files getting reformatted back and forth across commits.

Fix: `pre-commit autoupdate` floats the pin to the latest tagged hook revision. Do this when:
- A commit hook reformats files that `ruff format --check` (run from the venv) says are clean, or vice versa.
- A new ruff release ships meaningful formatter changes.

After `autoupdate`, re-run `pre-commit run --all-files` to catch any newly-flagged style.

### Hook id naming

`ruff-pre-commit` renamed `id: ruff` to `id: ruff-check` (the old id still works as a legacy alias and emits a deprecation warning). Use `ruff-check` in `.pre-commit-config.yaml`.

### `core.hooksPath` and pre-commit installation

`pre-commit install` refuses to run when `git config core.hooksPath` is set (even if its value is the default `.git/hooks`). If you `git clone` this repo on a machine whose global git config sets `core.hooksPath`, you'll need `git config --unset-all core.hooksPath` in the local clone before `pre-commit install` succeeds. This is local-only; doesn't affect other repos.

This is the **one** sanctioned exception to "never update git config" — it's repo-local, it removes a redundant override, and the alternative is a non-functional pre-commit setup. Surface it to the user before doing it anyway.

### Release workflow validates tag vs. version

`.github/workflows/release.yml` fires on `v*` tag push and **fails the build if the tag (minus the `v`) doesn't match `pyproject.toml`'s `version`**. So the workflow for cutting a release is:

1. Feature commit + bump commit land on `main` (per the existing CLAUDE.md rules).
2. `git tag vX.Y.Z` where X.Y.Z matches the bump.
3. `git push origin vX.Y.Z`.

Tag-then-bump or tag-with-wrong-version won't ship — the release job will fail loudly and you'll have to retag.

### CI shape

`.github/workflows/ci.yml` is two jobs: `lint` (single Python 3.12, runs `ruff check` / `ruff format --check` / `mypy`) and `test` (matrix on 3.10–3.13, runs `pytest`). The pre-push checklist mirrors what `lint` enforces; if CI's `lint` is red but your local pre-commit is green, suspect a ruff version drift (see above).

### Network tests

`tests/integration/test_sources_network.py` makes live HTTP calls to Moxfield and Archidekt. Gated behind `COD_SYNC_RUN_NETWORK_TESTS=1` (wired in `tests/conftest.py`), so the default test run stays offline and fast. If you're touching either source fetcher, run them: `COD_SYNC_RUN_NETWORK_TESTS=1 pytest tests/integration -q`.

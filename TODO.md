# TODO

Open work across cod-sync, organized by priority tier. Each item describes
the gap, points at the source location, and breaks the fix into discrete
checkable tasks. The doc is a working log — close items by removing them
in the same commit that lands the fix, not by leaving stale `- [x]` boxes.

Tier guide:

- **P1** — correctness bugs, data-loss risks, or architectural blockers
  that other work routes around. Land these first.
- **P2** — real user value or design improvements that aren't urgent.
  Pick when scratching specific itches.
- **P3** — polish, micro-optimizations, docstring drift, and other
  one-line wins. Batch into cleanup commits when convenient.

---

## P1 — correctness, data-loss, architectural blockers

### Walk `stats` dict silently swallows non-keyed outcomes

`cod_sync/cli/walk.py:37` initializes `stats` with only `updated`,
`no_change`, `skipped`, `errors`, and line 105 does
`stats[stat_key] = stats.get(stat_key, 0) + 1` — any future status
(e.g. `created`) is counted internally but never shown in the hardcoded
footer at line 107. Today walk forces `is_new_file=False` so `created`
can't appear, but the shape is fragile: a refactor that lets walk
create files will lose the count silently.

- [ ] Either drive the footer off the dict keys directly, or
- [ ] Assert at the top of the loop that `outcome.status` is one of the
      four expected statuses and raise a clear `RuntimeError` otherwise.
- [ ] Add a test that monkeypatches `_sync_deck` to return a
      `SyncOutcome` with status `"created"` and asserts the new
      contract (either it appears in the footer, or the assert fires).

---

## P2 — real value, moderate urgency

### `python -m cod_sync` swallows exit codes

`cod_sync/__main__.py` calls `main()` without wrapping it in
`sys.exit(...)`, so `python -m cod_sync` exits 0 even when the CLI
reports an error (the `cod-sync` console script is unaffected — the
entry-point wrapper propagates the return value). Exit codes are part
of the documented CLI contract, so a scripted caller invoking via
`-m` silently loses failure signals. One-line fix; the interesting
part is adding a test that runs the module form in a subprocess so
the regression can't return.

### Walk error-recovery summary

The walk currently aggregates a per-status count at the end (updated,
no-change, skipped, errors). When `errors > 0` the user has to scroll
back through interleaved output to see which files failed and why.

- [ ] Collect a small `list[tuple[Path, str]]` of `(path, error_message)`
      inside `_walk_directory`.
- [ ] Print it as a footer block under the summary when non-empty.
- [ ] Test: a walk where two of three decks fail to fetch shows both
      paths and their causes under the summary.

### Local alt-name management surface

The reskin disk cache lives at a fixed path under the user cache
directory. If Scryfall returns a wrong mapping or a user wants a
one-off override, the only way to fix it is to hand-edit JSON.

- [ ] Decide whether the surface should be a positional flag
      (`cod-sync --alt-name SET "Flavor" "Canonical"`) or a separate
      dunder-prefixed entrypoint. Use `AskUserQuestion` to surface the
      tension before designing.
- [ ] Implement `list`, `set`, and `forget` operations against the
      disk cache.
- [ ] Add tests covering each operation against a tmpdir cache.
- [ ] Update README's "Reskin flavor names" paragraph to mention the
      override surface.

### More deck sources

The source layer is designed for cheap additions: each source is a
small module following the same shape. TappedOut, MTGGoldfish,
Deckstats, Decked Builder are common asks.

- [ ] Pick the next source based on actual user demand, not coverage.
- [ ] Scaffold `cod_sync/sources/<name>.py` mirroring the
      Moxfield/Archidekt shape.
- [ ] Wire the host into the dispatch table in
      `cod_sync/sources/__init__.py:_fetch_raw`.
- [ ] Tests in `tests/test_source_<name>.py` covering parse fidelity,
      DFC normalization, tag extraction, and error mapping.

### Parallelize Scryfall batches

Decks with many unknown cards split into multiple sequential network
batches. A modest thread pool would halve first-sync latency for these
edge cases. Unblocked since 0.11.3: `alt_name`'s module state is
lock-guarded and the lock is never held across network I/O.

- [ ] Replace the sequential loop in `_scryfall_batch_lookup` with a
      `ThreadPoolExecutor(max_workers=4)` mapping batches concurrently.
- [ ] Cap concurrency at 4 to stay under Scryfall's rate-limit
      guidance.
- [ ] Test with a mocked session that records request ordering.

### CHANGELOG

Commit messages are descriptive, but there's no human-readable summary
mapping versions to user-visible changes.

- [ ] Add `CHANGELOG.md` keyed to the same versions as the table at the
      bottom of `VERSIONING.md`.
- [ ] Add a release-time step in `CLAUDE.md`'s "Mechanics" section that
      appends a new entry alongside the `pyproject.toml` /
      `__init__.py` bump.
- [ ] Backfill entries for the most recent 3-5 releases so the file is
      useful immediately rather than empty.

### Maybeboard handling

Maybeboard contents are silently dropped today (see comments in
`sources/moxfield.py` and `sources/archidekt.py`). No one has asked for
them back, but it's an option that exists in both sources and isn't
represented in our model.

- [ ] Decide whether to surface as a third zone (`maybe`) or via a
      `--include-maybeboard` flag.
- [ ] Update `RemoteDeck.zones` and the parsers to carry the new zone
      conditionally.
- [ ] Cockatrice doesn't render a maybeboard, so confirm the target
      behavior end-to-end before shipping.

### Multi-printing output ordering

When a card with multiple printings gets a quantity increase, the new
bare entry is appended at the end of the zone. Some users would prefer
adjacent printings grouped together.

- [ ] Add an `--group-printings` flag (default off — current behavior is
      the documented contract).
- [ ] When set, after `_apply_zone` runs, re-sort cards so same-name
      entries cluster while preserving original relative order.
- [ ] Test: bumping a 3-printing card by 1 produces 4 adjacent entries
      under the flag, appended-at-end without it.

### Text parser edge cases

The text-source parser handles MTGA/MTGO format reasonably but isn't
tested against edge cases users actually paste.

- [ ] Add tests for parenthesized inline comments mid-line.
- [ ] Add tests for malformed quantities (e.g. `1.5x`, `--`).
- [ ] Add tests for mixed-case section headers (`MAINBOARD`, `sIdE`).
- [ ] Add tests for trailing whitespace / CRLF mixed line endings.
- [ ] Add tests for blank section headers (`Sideboard` followed by
      nothing).

### `_apply_zone` has an unreachable qty-on-missing branch

`cod_sync/cli/apply.py:79-89`: when `qty_updates` contains a name not
present in `cards` (so `indices == []`), `current_total == 0`,
`target > 0`, and execution falls into the `else` branch which appends
a fresh bare entry. The diff layer never generates `qty` for
`local_qty == 0` (`diff.py:42-47` routes that to `add`), so this branch
is unreachable in practice but silently looks identical to an `add` if
ever exercised. Either kill the dead branch or assert the invariant.

- [ ] Add `assert current_total > 0` at the top of the `qty_updates`
      loop with a comment pointing at the `diff.py` invariant.
- [ ] Remove the now-dead `len(indices) == 1` else-branch that handled
      the empty case.
- [ ] Add a test that constructs a `qty` change with `local_qty=0` by
      hand and asserts the assertion fires.

### Banner orphan recovery misses third-reskin edge cases

`cod_sync/cli/sync.py:151-159`: banner restoration uses
`{c.name for z in final_deck.zones for c in z.cards}` without
canonicalizing. A deck where the user left a *different* reskin name
(not the banner's) referring to the same canonical would silently match
the banner check too. Rare, but worth pinning behavior.

- [ ] Pre-canonicalize the post-apply card names before the membership
      check: `canonical_card_names = {alt_name.canonicalize(c.name)
      for z in final_deck.zones for c in z.cards}`.
- [ ] Test: build a deck with two reskins of the same canonical,
      banner pointed at one of them, assert banner stays put after sync.
- [ ] Test: a deck with banner = reskin A and canonical of A absent
      from zones leaves banner alone.

### `_QUIET` module-level mutable global

`cod_sync/cli/_state.py:14`: `main()` writes a process-global on every
invocation. Single-shot CLI today, but it forces any test that
exercises `main()` twice with different `--quiet` settings to reset by
hand, and makes the module unsafe for library use or parallel walks.

- [ ] Replace `_QUIET` with a `Settings` dataclass holding `quiet:
      bool` and an injectable `say: Callable[[str], None]`.
- [ ] Pass `Settings` (or just `say`) through the dispatcher entry
      points down to `_print_summary` — the only place it's actually
      consulted.
- [ ] Drop `_state.py` once the global is gone.
- [ ] Confirm `tests/test_quiet.py` still passes without manual state
      resets.

### `Zones` advertises frozen but is mutable

`cod_sync/sources/types.py:7,11-25`: `Zones = dict[str, dict[str, int]]`
is the field type of frozen `RemoteDeck`. The dataclass freeze
prevents reassignment but does nothing about dict mutation, and source
fetchers write into the dict in-place during parsing
(`sources/moxfield.py:121`).

- [ ] Either change the field type to `Mapping[str, Mapping[str, int]]`
      with a docstring noting the construction phase, **or**
- [ ] Convert to an immutable shape (`tuple[tuple[str,
      tuple[tuple[str, int], ...]], ...]`) at the end of every
      fetcher and update callers to read accordingly.
- [ ] Confirm consumers (`diff.py:_zone_to_dict`,
      `sources/__init__.py:_canonicalize`) still work against the new
      type.

### Source-canonicalization re-scans zones three times

`cod_sync/sources/__init__.py:49-64`: `_canonicalize` walks every zone
once to build `all_names`, once more for the `all(mapping.get(n, n) ==
n)` short-circuit, and a third time to build `new_zones` if any
rewrite happened.

- [ ] Fold the identity check into the build loop with a `dirty: bool`
      flag.
- [ ] Return `deck` early when `dirty is False` after the single pass.
- [ ] Confirm `tests/test_alt_name_perf.py` still meets its budget.

### `_build_new_deck` is dead code

`cod_sync/cli/apply.py:13-24` is defined and re-exported in
`cli/__init__.py:36` but has zero call sites in `cod_sync/`, `tests/`,
or `scripts/`. The function existed for a workflow that was replaced
when the bare-URL import path was funnelled through `_sync_file`
(`sync.py:284-289`).

- [ ] Delete the function from `cli/apply.py`.
- [ ] Remove the re-export line from `cli/__init__.py:36`.
- [ ] Confirm `python -m ruff check` and the test suite stay green.

### `_save_disk_cache` rewrites the entire cache on every learn

`cod_sync/alt_name.py:189-199`: each `canonicalize` /
`canonicalize_batch` call that adds entries serializes the whole dict
back to disk. Real-world sizes are tiny so this isn't a felt cost
today, but the shape is dirty and couples to the OSError-swallowing
P1 item.

- [ ] Add a module-level `_disk_cache_dirty: bool` flag.
- [ ] Set it in `canonicalize` and `canonicalize_batch` after learning
      new entries; do not call `_save_disk_cache` inline.
- [ ] Register an `atexit` handler that flushes if the dirty flag is
      set.
- [ ] Also flush from `_reset_state_for_tests` so test isolation
      doesn't lose writes.
- [ ] Test that a batch of 10 unknown lookups produces exactly one disk
      write.

### Banner check forces a canonicalize per sync

`cod_sync/cli/sync.py:152-159`: `alt_name.canonicalize(original)` runs
unconditionally for any deck with a banner. The function lazy-loads
the disk cache (cheap, once per process), but every subsequent sync
still pays a lookup, a `dfc.front_face` scan, and — if the banner is
an unknown reskin not in the seed and the cache is cold — a real
Scryfall fetch *just to check whether the banner needs flipping*.

- [ ] Pre-compute the post-apply card-name set once.
- [ ] Skip the `alt_name.canonicalize` call entirely when the banner
      name is already in the set (the common case).
- [ ] Test that a sync where the banner card is unchanged in the deck
      makes zero alt_name lookups.

---

## P3 — polish, micro-optimizations, drift cleanup

### `canonicalize` docstring lies about the fast path

`cod_sync/alt_name.py:131-147`: the comment says "Fast path: seed-only
lookup avoids the iterator/set construction" but the code checks the
disk cache first, then the seed. The comment was true before the disk
layer landed and rotted in place.

- [ ] Either rewrite the comment to reflect "disk → seed → network", **or**
- [ ] Collapse `canonicalize` into `canonicalize_batch([name])[name]`
      since the single-call wrapper buys very little once the disk
      lookup is the same cost as in the batch path.

### Redundant `dfc.front_face` calls on already-stripped values

`cod_sync/alt_name.py:104, 122, 138, 144`: every seed and cache hit
runs `dfc.front_face(v)` even though `refresh_seed.py:71-72` already
strips both flavor and canonical, and `_save_disk_cache` only writes
front-face values.

- [ ] Add a one-line assertion in `_read_disk_cache` that loaded values
      contain no ` // ` separator (or strip-and-warn on load).
- [ ] Drop the per-lookup `dfc.front_face` calls on the seed/disk hot
      paths.
- [ ] Keep the call on the Scryfall-result path (line 122) — that's the
      one source that returns full-form names.

### `_sanitize_filename` double-underscore collapse is O(n²)

`cod_sync/cli/formatting.py:87-88`: `while "__" in s: s = s.replace(...)`
rebuilds the string each iteration. Tiny in practice, textbook smell.

- [ ] Replace the while-loop with `s = re.sub(r"_+", "_", s)`.
- [ ] Add the compiled regex at module level if reused elsewhere.

### Text-source compiles one regex per line

`cod_sync/sources/text.py:47`: `re.match(r"^\s*SB:", raw)` is parsed
on every line. Python's regex cache absorbs this in practice but
`_LINE_RE` is already module-level — the inconsistency reads as
"forgotten."

- [ ] Hoist to `_SB_PREFIX_RE = re.compile(r"^\s*SB:")` next to
      `_LINE_RE`.
- [ ] Reuse in `parse()`.

### `canonicalize_batch` distinct-set construction

`cod_sync/alt_name.py:86-90`: `distinct: set[str] = set(); for n in
names: if n: distinct.add(n)` is exactly `distinct = {n for n in names
if n}`. Minor, but the explicit loop reads like the body is doing
more than it is.

- [ ] Replace with the set-comprehension form.

### Conventional Commits prefix is doc-only

`CLAUDE.md` enforces strict commit-message prefixes (`feat:` / `fix:` /
`refactor:` / ...) but nothing in `.pre-commit-config.yaml` validates
them. First-time contributors can land `Update foo.py` and learn the
rule only at review time.

- [ ] Add a `commit-msg`-stage hook (commitizen or a 5-line shell
      script) that validates the prefix against the documented set.
- [ ] Document the hook installation in `CONTRIBUTING.md`.

### `_apply` rebuilds the zone index per change-group

`cod_sync/cli/apply.py:53-58`: `next(i for i, z in enumerate(new_zones)
if z.name == zone_name)` walks zones for each group. n=2 in practice
so meaningless, but the same loop above already calls
`_get_or_create_zone` which had to find the index.

- [ ] Change `_get_or_create_zone` to return `(zone, idx)`.
- [ ] Use the returned index instead of the second scan.

### `_zone_to_dict` lookup chain in `compute`

`cod_sync/diff.py:33-48`: for each of two zones, `deck.zone(name)` is
called (linear over `deck.zones`), then `_zone_to_dict` re-iterates
cards. The same `deck.zone` lookup appears in `_show_info`
(`formatting.py:112`), `_apply` (via `_get_or_create_zone`), and
elsewhere. Tiny scale, but worth a one-time index.

- [ ] Add a cached `dict[str, Zone]` index to `Deck`, computed via
      `functools.cached_property` (or `__post_init__` if staying with
      frozen dataclass).
- [ ] Rewrite `Deck.zone` to consult the index.
- [ ] Confirm round-trip parsing tests still pass.

### `_canonicalize` early-bail re-walks `all_names`

`cod_sync/sources/__init__.py:55`: the `all(mapping.get(n, n) == n)`
check is a second walk over the same names. Folded into the build loop
under the P2 "Source-canonicalization re-scans" item above — listed
here as a cross-reference, no new work.

- [ ] Closed by the P2 item; remove this entry when that lands.

### Walk "empty input = skip" prompt accepts undocumented `s`

`cod_sync/cli/walk.py:68-77`: the input prompt advertises
`empty=skip, q=quit`, but the branching also treats lowercase `s` as
skip. Not wrong, just inconsistent — either document `s` or drop it.

- [ ] Update the prompt string to include `s=skip` if keeping the
      shortcut, **or**
- [ ] Drop the `or entered.lower() == "s"` branch and let users type
      empty for skip.

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

_No open P1 items._

---

## P2 — real value, moderate urgency

### Walk error-recovery summary

The walk currently aggregates a per-status count at the end (updated,
no-change, skipped, errors). When `errors > 0` the user has to scroll
back through interleaved output to see which files failed and why.

- [ ] Collect a small `list[tuple[Path, str]]` of `(path, error_message)`
      inside `_walk_directory`.
- [ ] Print it as a footer block under the summary when non-empty.
- [ ] Test: a walk where two of three decks fail to fetch shows both
      paths and their causes under the summary.

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

---

## P3 — polish, micro-optimizations, drift cleanup

### Archidekt side-zone match is case-insensitive but Archidekt categories are not

`sources/archidekt.py` `_parse` lowercases a card's primary category
before matching `_SIDE_CATEGORIES`. Archidekt itself treats category
names as case-sensitive (a deck can hold both a built-in `Sideboard`
and a user-made `SIdeboard` as distinct categories — observed in the
wild on deck 23409517). A card whose *primary* category is a custom
case-variant like `SIdeboard` renders in the mainboard on Archidekt
but we'd route it to `side`. Secondary-label mis-zoning was fixed by
the primary-category change; this residual case needs a real deck that
hits it before deciding whether exact-case matching is worth the
strictness.

### Text parser cannot keep Room names offline

`sources/text.py` strips every `A // B` line to the front half at parse
time because plain text carries no layout info. Online this self-heals:
the alt_name layer resolves the half-name through Scryfall and restores
the full Room/split name. With `COD_SYNC_NO_NETWORK=1`, Room names typed
in full form stay wrongly stripped. Fixing offline would need a bundled
layout (or split-name) dictionary similar to `_seed_data.py` — probably
not worth it until someone actually hits it; logged so the limitation is
a decision, not an accident.

### No test pins the `reversible_card` printing path

Reversible promo printings of omen cards (e.g. Scavenger Regent, TDM
#379) are a layout edge the pipeline handles correctly today but only
by composition — nothing pins the convergence. The design is documented
in ARCHITECTURE.md ("The reversible-printing edge case"); the gap is
test coverage only.

- [ ] Test: `cockatrice_name("A // B // A", "reversible_card")` reduces
      to `"A"`, and a mocked Scryfall canonicalize round-trip restores
      the full `"A // B"` name.

### User-Agent strings embed stale hardcoded versions

`cod_sync/alt_name.py` sends `cod-sync/0.7` and `cod_sync/sources/_http.py`
sends `cod-sync/0.1` — both frozen at whatever version the line was
written. Derive from `cod_sync.__version__` instead so the UA tracks
releases automatically (one f-string each; mind the lazy-import
boundaries).

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

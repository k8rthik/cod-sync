# Architecture

Design notes for cod-sync. This document holds the *why* behind the
code — module docstrings state what each module does and point here for
rationale. The complements: [README.md](./README.md) is the user-facing
tour, [CONTRIBUTING.md](./CONTRIBUTING.md) is dev setup, and
[VERSIONING.md](./VERSIONING.md) defines which surfaces are versioned
contract.

## Data flow

A sync is one straight pipeline:

```
cod-sync TARGET [URL]
        │
        ▼
cli/routing.py     classify the target → walk / sync / import / --info
        │
        ▼
sources/           fetch and parse the remote decklist
        │            moxfield.py · archidekt.py · text.py
        │            names shaped per card layout (dfc.py)
        ▼
alt_name.py        reskin flavor names → canonical names
        │            seed dict → disk cache → Scryfall batch lookup
        ▼
cli/sync.py        mapping control: log applied alt-name mappings,
        │            prompt once per unsettled one (skipped under -y)
        ▼
diff.py            verbatim per-zone compare → list of Change objects
        │            (cards under cod-sync-ignore: markers filtered out)
        ▼
cli/prompts.py     interactive per-change approval (skipped under -y)
        │
        ▼
cli/apply.py       pure deck mutation; printing pins preserved
        │
        ▼
cod.py             format-preserving write back to the .cod file
```

`cli/sync.py:_sync_deck` orchestrates the lower half. All three entry
modes — single-file sync, bare-URL import, directory walk — funnel into
it and behave identically once inside.

## Module map

| Module | Role |
|---|---|
| `cli/__init__.py` | argparse setup, flag wiring |
| `cli/routing.py` | target classification (dir / file / URL) and dispatch |
| `cli/sync.py` | per-deck orchestration: diff → approve → apply → save |
| `cli/walk.py` | directory iteration, per-deck stored-URL prompting |
| `cli/apply.py` | pure deck mutation (no I/O, no prompts) |
| `cli/prompts.py` | all `input()` calls live here |
| `cli/formatting.py` | ANSI rendering, change summaries, `--info` display |
| `cli/_state.py` | the `--quiet` flag and `say()` helper |
| `sources/` | one fetcher per source, shared `RemoteDeck` type |
| `sources/_http.py` | lazy, shared keep-alive HTTP session |
| `dfc.py` | multi-face name shaping (see below) |
| `alt_name.py` | reskin → canonical resolution (see below) |
| `_seed_data.py` | generated reskin dict — never hand-edit |
| `diff.py` | local-vs-remote change computation |
| `cod.py` | `.cod` parse and format-preserving write |
| `sourcetag.py` | the `cod-sync-source:` and `cod-sync-ignore:` markers in `<comments>` |
| `errors.py` | typed source-fetch errors, HTTP status classification |

## Card name shaping

Cockatrice's card database (`cards.xml`) keys multi-face cards two
ways, depending on the card's Scryfall layout:

| Group | Scryfall layouts | Cockatrice key |
|---|---|---|
| True double-faced cards | `transform`, `modal_dfc`, `meld`, `flip` | front face only (`Storm the Vault`) |
| Single-face multi-part cards | `split` (incl. Duskmourn Rooms), `aftermath`, `adventure` (incl. Tarkir omens), `prepare` | full name (`Fire // Ice`) |

`dfc.cockatrice_name(name, layout)` implements the split. The
membership of each group was verified empirically against Cockatrice's
own `cards.xml`: every `adventure`, `aftermath`, `split`, and `prepare`
entry uses the full name, and every other multi-face layout is keyed by
front face. `room` and `omen` are accepted as defensive aliases for
`split` and `adventure` in case a deck API starts reporting the
mechanic names.

Shaping is applied at every boundary where a name enters the system:

- **Source fetchers** shape using the per-card `layout` field the deck
  APIs return (`sources/moxfield.py`, `sources/archidekt.py`).
- **The alt_name layer** shapes Scryfall lookup results using the
  `layout` in the response, so resolved canonicals land in the same
  form.
- **The plain-text parser** has no layout information, so it reduces
  every `A // B` line to the front face; when the network is available,
  the alt_name Scryfall pass restores full names for the split-family
  layouts. Offline, full-form split-family names stay reduced (tracked
  in TODO.md).

`diff.py` deliberately compares names **verbatim** and never reshapes.
A stale shape in the local file (written by an older cod-sync, or by
hand) shows up as a remove + add pair, which heals the file on the next
sync. This keeps the shaping knowledge in exactly one module instead of
leaking comparison heuristics into the diff.

### The reversible-printing edge case

Some cards have *reversible* promo printings — same game object on both
faces, different art (Scryfall layout `reversible_card`). Example:
Scavenger Regent, an omen card. Its regular printing (TDM #90) is
layout `adventure`, named `Scavenger Regent // Exude Toxin`. Its
reversible promo (TDM #379) is a separate Scryfall card object named
`Scavenger Regent // Exude Toxin // Scavenger Regent` with layout
`reversible_card`.

Cockatrice's database generator gives the reversible printing its
**own entry keyed by the bare front face** (`Scavenger Regent`,
layout `reversible_card`) alongside the regular full-name entry. So the
same logical card legitimately exists under two names in `cards.xml` —
this is upstream Cockatrice data design, not something cod-sync
controls.

cod-sync converges on the canonical full-name entry either way:

- A source reporting the oracle layout (`adventure`) keeps the full
  name directly (Archidekt reports oracle-level layout).
- A source reporting the printing layout (`reversible_card`) reduces to
  the bare front face — which the alt_name Scryfall pass then resolves
  back to the full-name form.

Offline, the bare front-face name survives to the `.cod`; that still
loads in Cockatrice (via the printing-specific entry) and heals on the
next networked sync.

## Reskin (alt-name) resolution

Secret Lair drops ship cards under flavor names (`Unstable Harmonics`)
that Moxfield and Archidekt report verbatim but Cockatrice only knows
canonically (`Rhystic Study`). `alt_name.canonicalize_batch` resolves
through three layers, cheapest first:

1. **Bundled seed** (`_seed_data.SEED`) — every reskin Scryfall knew at
   release time, regenerated by `scripts/refresh_seed.py`. Pure
   in-memory dict lookup.
2. **Disk cache** (`~/.cache/cod-sync/alt_names.json`) — per-user,
   loaded once per process, grows as Scryfall resolves new names. Disk
   wins over seed so users can override entries locally.
3. **Scryfall** `/cards/collection` — one batched POST per 75 unknown
   names over a keep-alive session. Catches reskins newer than the
   bundled seed. `COD_SYNC_NO_NETWORK=1` skips this layer entirely.

Caching policy: only **definitive** answers are cached. A name Scryfall
resolves is cached canonically; a name Scryfall reports as not-found is
cached as identity (so it is never re-queried); a transport failure
(timeout, 5xx) falls back to identity *for the current run only* — one
network blip must never permanently mask a reskin.

Scryfall's collection endpoint doesn't match full `A // B` names, so
full-name misses are retried by their front half; the half resolves the
card and its layout, and shaping puts the canonical back in the right
form.

### In-flow mapping control

There is deliberately no standalone override command. Instead, control
happens where the user sees the problem: every applied mapping is
logged during sync, and a mapping not yet in the disk cache prompts
once — accept, keep the printed name, or type a replacement (e.g. for a
custom-set Cockatrice database). The answer is persisted via
`alt_name.set_override` into the disk cache, which wins over the seed,
so a name never prompts twice across any number of decks. `-y` accepts
and persists proposals silently; `--dry-run` logs without prompting or
writing. The disk cache is therefore the *settled* layer: every entry
is either user-confirmed or learned from Scryfall.

The plumbing: `sources._canonicalize` records each applied non-identity
mapping on `RemoteDeck.renames` (zone, original, canonical, the
original's own quantity, settled flag), and `cli/sync.py:
_apply_mapping_control` does the logging/prompting and — when the user
overrides — un-merges exactly the renamed quantity off the proposed
canonical, so a deck holding both the reskin and the literal canonical
stays correct.

### Cache schema

The cache file is a flat `{name: canonical}` JSON object plus one
reserved marker entry, `"__schema__": "2"`. The marker means every
value is already Cockatrice-shaped and can be trusted verbatim at read
time.

History: caches written before layout-aware shaping (pre-0.14) stored
raw Scryfall canonicals, so a true DFC could sit there under its full
`Front // Back` form — a name Cockatrice's database doesn't key.
Layouts aren't stored in the cache, so those values can't be re-shaped
offline. Loading a marker-less file therefore drops every full-form
value (the legitimate split-family ones re-resolve, correctly shaped,
on next use) and writes the healed file back with the marker — a
one-time migration per cache file.

Env vars: `COD_SYNC_CACHE_DIR` overrides the cache root,
`XDG_CACHE_HOME` is honored, default is `~/.cache`.
`COD_SYNC_NO_NETWORK=1` disables Scryfall.

## Latency design

Startup and sync latency are dominated by two costs, both deferred:

- **`requests` import** (~75ms, over half of CLI startup) is deferred
  to first network use, so `--info`, `--version`, `--help`, and
  declined prompts never pay it. Every network-touching module imports
  `requests` inside the function or under `TYPE_CHECKING`.
- **TCP+TLS handshakes** are paid once per host, not per deck: the deck
  fetchers share one keep-alive session (`sources/_http.py`), and
  alt_name keeps its own for Scryfall batches.

The alt-name disk cache is read once per process and held in memory, so
a directory walk amortizes lookups across decks: the first deck pays
any Scryfall round-trips, the rest hit memory. A fully-cached 100-card
sync resolves names in well under a millisecond.

## Thread safety

The CLI is single-threaded today; the locking exists so the library can
be embedded in multi-threaded callers and to unblock parallel Scryfall
batches (tracked in TODO.md).

`alt_name` and `sources/_http` each guard their module-level state
(memoized cache, memoized session, warn-once flag) with one lock. The
rules: mutate state and write the cache file only while holding the
lock; **never hold the lock across network I/O**, so concurrent batches
overlap their HTTP. Benign race: two threads resolving the same unknown
name may each query Scryfall once — results are identical, last write
wins. Cache reads are unlocked and rely on CPython's atomic dict
access.

## Error taxonomy

Source-fetch failures are typed (`errors.py`): one leaf class per
distinct user remedy (deck not found, private, rate-limited, server
error, network, malformed response, invalid source).
`errors.from_http_response` is the single place HTTP status codes are
classified, shared by all fetchers; `cli/formatting.py` holds one
message template per type so the error tells the user what to *do*, not
just that something failed.

## The `.cod` contract

`cod.py` writes byte-for-byte what Cockatrice itself writes:
same indentation, same attribute order, same self-closing forms. A
no-op sync produces a byte-identical file. Printing pins
(`setShortName`, `collectorNumber`, `uuid`) on cards the diff didn't
touch are carried through untouched; added cards get bare
`<card number="N" name="..."/>` entries so the user picks art in
Cockatrice. The only things cod-sync ever writes into `<comments>` are
its own marker lines (`sourcetag.py`): the single `cod-sync-source:
<url>` line and one `cod-sync-ignore: <name>` line per ignored card.
User text is preserved verbatim, and deleting an ignore line in
Cockatrice's comments box is the supported un-ignore path.

This surface is versioned — see VERSIONING.md, "The contract we
version".

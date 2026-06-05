# cod-sync

**Keep your Cockatrice decks in sync with the deckbuilder you actually use.**

`cod-sync` is a focused command-line tool that compares a local Cockatrice
`.cod` decklist against a deck on **Moxfield**, **Archidekt**, or any pasted
text decklist — shows the changes in color, lets you accept them one at a
time, and edits the file in place. Your curated printings, banner card,
tags, comments, and formatting come through untouched.

```text
2 change(s):
  [main]
    + 1x Witch-king, Sky Scourge
  [side]
    - 1x Witch-king, Sky Scourge

  [1/2] (main) + 1x Witch-king, Sky Scourge  [y/n/a=all/s=skip-rest/q=quit] y
  [2/2] (side) - 1x Witch-king, Sky Scourge  [y/n/a=all/s=skip-rest/q=quit] y
Wrote 2 change(s) to b3_witchking.cod
```

---

## Why this exists

If you build decks on Moxfield or Archidekt and play them in Cockatrice,
the two go out of sync the moment you tweak one without remembering the
other. The usual workaround — export the online list and reimport into
Cockatrice — wipes the printings you chose, drops the banner card, resets
tags, and gives you back an anonymous, freshly-shuffled file.

`cod-sync` does the minimum required to bring the local file up to date:

- Pulls the canonical list from the deckbuilder you used.
- Diffs it against your `.cod` and shows exactly what will change.
- Applies only what you approve, leaving everything else alone.

No printings are rewritten. No banner card is forgotten. No file is
touched without your sign-off.

---

## Features

- **Three sources.** Moxfield URLs, Archidekt URLs, and plain-text
  decklists (MTGA / MTGO format, with `Sideboard` headers or `SB:`
  prefixes).
- **Surgical edits.** Only quantity changes, additions, and removals are
  applied. `setShortName`, `collectorNumber`, and `uuid` pins on every
  other card are kept exactly as they were.
- **Round-trip fidelity.** Deck name, format, banner card, comments, and
  the file's exact indentation come out byte-for-byte identical when
  there are no changes.
- **Interactive review.** Walk each change with `y / n / a / s / q`
  controls; accept all at once, stop midway, or quit without writing.
- **Directory mode.** Walk every `.cod` in a folder (optionally
  recursively), prompting for a source per deck.
- **URL memory.** After the first sync, the source URL is stashed in the
  deck's `<comments>` field, so the next walk just offers it back to you.
- **Multi-printing safe.** Cards listed across several `<card>` lines
  (e.g. nine Nazgûl, each its own art) are treated as one logical card
  by the diff, and edits keep every existing pin intact.
- **DFC-aware matching.** A local `Bala Ged Recovery` matches a remote
  `Bala Ged Recovery // Bala Ged Sanctuary` automatically, whichever form
  your Cockatrice card DB happens to use.
- **No surprise writes.** `--dry-run` previews; `--yes` skips the prompts
  but never widens the scope of edits.

---

## Install

```sh
git clone https://github.com/k8rthik/cod-sync.git
cd cod-sync
pip install -e .
```

Requires Python 3.10+. The only runtime dependency is `requests`.

The CLI installs as `cod-sync`.

---

## Quick start

Sync a single deck against a Moxfield URL:

```sh
cod-sync sync my_deck.cod https://www.moxfield.com/decks/abc123
```

Walk every `.cod` in your Cockatrice decks folder:

```sh
cod-sync dir ~/Library/Application\ Support/Cockatrice/Cockatrice/decks/b3
```

Preview a diff without writing anything:

```sh
cod-sync sync my_deck.cod https://archidekt.com/decks/12345 --dry-run
```

---

## Commands

### `cod-sync sync FILE SOURCE`

Compare one `.cod` against one source.

| Argument / flag | Description |
| --- | --- |
| `FILE` | Path to a local `.cod` file. |
| `SOURCE` | A Moxfield URL, an Archidekt URL, or a path to a plain-text decklist. |
| `--dry-run`, `-n` | Print the diff but don't modify the file. |
| `--yes`, `-y` | Apply every change without prompting. |

If `SOURCE` is a URL, it's recorded in the deck's `<comments>` for later
runs (see [URL memory](#url-memory)). Text-file sources are not stored.

### `cod-sync dir [DIRECTORY]`

Walk every `.cod` in a folder, prompting for a source per file.
`DIRECTORY` defaults to `.` (the current directory).

| Argument / flag | Description |
| --- | --- |
| `DIRECTORY` | Folder to walk. Defaults to the current directory. |
| `--recursive`, `-r` | Descend into subdirectories. |
| `--dry-run`, `-n` | Show diffs but don't write any files. |
| `--yes`, `-y` | Apply every approved diff without prompting per change. |

For each deck the prompt shows:

```text
[1/15] b3_kadena.cod  — Flip The Bird
  source URL/path (empty=skip, q=quit):
```

- Enter a URL or path → diff + interactive review.
- Empty line → skip this deck (or use the stored URL — see below).
- `s` → skip this deck.
- `q` → stop the walk; any decks already written stay written.

### Interactive review keys

At each change prompt:

| key | action |
| --- | --- |
| `y` / Enter | apply this change |
| `n` | skip this change |
| `a` | apply this change and everything remaining |
| `s` | stop reviewing this deck, write what's been approved so far |
| `q` | quit this deck without writing (in `dir` mode, also stops the walk) |

---

## URL memory

The first time you sync a deck against a URL, `cod-sync` writes a single
marker line into the deck's `<comments>` field:

```text
cod-sync-source: https://archidekt.com/decks/23168622
```

Your own comments are kept; only that one marker line is managed.

On the next `cod-sync dir` walk, decks with a stored URL prompt like
this:

```text
[1/15] b3_kadena.cod  — Flip The Bird
  stored: https://archidekt.com/decks/23168622
  source URL/path (empty=use stored, s=skip, q=quit):
```

Hit Enter to reuse it, or paste a new URL to switch sources (the new URL
overwrites the marker). Text-file paths are deliberately not stored.

---

## What's preserved, what changes

| Element | Behavior |
| --- | --- |
| Card quantities | Updated to match the source. |
| Removed cards | Their `<card .../>` lines are deleted. |
| Added cards | Appended as bare `<card number="N" name="..."/>` lines so you can pick the printing in Cockatrice. |
| `setShortName` / `collectorNumber` / `uuid` on existing cards | Never altered when only quantity changes. |
| Banner card | Untouched. |
| Deck name, format | Untouched. |
| Tags element | Untouched. |
| Comments | Untouched, except for the single `cod-sync-source:` marker line. |
| Indentation, attribute order, XML formatting | Identical to what Cockatrice writes. |

When the local and remote agree, the file is not rewritten — a
no-op run leaves mtime untouched (unless the source URL marker is new).

---

## Behaviour worth knowing

- **Maybeboards are dropped.** Cards in Moxfield's maybeboard or in an
  Archidekt category with `includedInDeck: false` are ignored entirely.
- **Commanders go to `main`.** Cockatrice stores EDH commanders inside
  the `main` zone; that's where they're routed from both Moxfield's
  `commanders` board and Archidekt's "Commander" category.
- **Companions go to `main` too** (suitable for EDH; if you sync
  Constructed decks where the companion belongs in the sideboard, you'll
  need to move it manually for now).
- **DFC / split / adventure names.** When the remote returns a card as
  `Front // Back` and your local file has just `Front`, the two are
  matched automatically. New cards are added using whatever full name
  the source provided.
- **Multi-printing cards.** A card listed under multiple printings is
  treated as one logical card by the diff. Quantity increases append a
  bare delta entry rather than touching your printings; decreases
  reduce from the most recently added printing first; removes drop
  every entry of the card.

---

## Sources

### Moxfield

URLs like `https://www.moxfield.com/decks/<id>`. Uses the public v3 API
(`api2.moxfield.com/v3/decks/all/<id>`). No login or token needed for
public decks.

### Archidekt

URLs like `https://archidekt.com/decks/<id>` or
`https://archidekt.com/decks/<id>/<slug>`. Uses the documented
`archidekt.com/api/decks/<id>/` endpoint.

### Plain-text decklists

Any local file in MTGA or MTGO export format:

```text
Deck
1 Sol Ring
9 Snow-Covered Forest
1 Sol Ring (CMM) 423

Sideboard
1 Pithing Needle
```

`Deck`, `Mainboard`, `Commander`, `Sideboard`, and `Side` headers all
work; so does the MTGO-style `SB:` prefix. Lines starting with `//` or
`#` are treated as comments. Set codes and collector numbers in
parentheses are stripped.

---

## Development

```sh
pip install -e .
pytest -q
```

The codebase is intentionally small:

```text
cod_sync/
  cli.py            # argparse + interactive review + dir walk
  cod.py            # .cod parser and format-preserving writer
  diff.py           # zone-level diff with DFC reconciliation
  sourcetag.py      # URL marker stored in <comments>
  sources/
    moxfield.py
    archidekt.py
    text.py
tests/              # unit + round-trip + multi-printing coverage
```

Pull requests welcome; please add a test alongside any behavior change.

---

## Status

Early but used daily on the maintainer's own deck folder. The diff,
apply, and round-trip paths have test coverage; the Moxfield and
Archidekt fetchers are best-effort against their current public APIs and
may need updates if those change.

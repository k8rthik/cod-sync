# cod-sync

A small CLI that diffs a local Cockatrice `.cod` decklist against a remote
source (Moxfield, Archidekt, or a pasted text decklist), shows the changes
in color, and applies the ones you approve — editing the file in place.

Designed to be safe with curated decks: **only quantities, additions, and
removals are touched.** Existing `setShortName` / `collectorNumber` /
`uuid` printing pins on untouched cards are preserved byte-for-byte.

## Install

```sh
cd ~/code/cod-sync
pip install -e .
```

Requires Python 3.10+. The only runtime dependency is `requests`.

## Usage

```sh
cod-sync <local.cod> <source>
```

`<source>` is one of:

- `https://www.moxfield.com/decks/<id>`
- `https://archidekt.com/decks/<id>` (or `.../<id>/<slug>`)
- A path to a plain-text decklist (MTGA/MTGO format; `Sideboard` header
  or `SB:` line prefix both supported)

### Examples

Interactive review against a Moxfield deck:

```sh
cod-sync ~/Library/Application\ Support/Cockatrice/Cockatrice/decks/b3/b3_kadena.cod \
         https://www.moxfield.com/decks/abc123
```

Preview the diff without writing:

```sh
cod-sync my_deck.cod https://archidekt.com/decks/12345 --dry-run
```

Apply every change without prompting:

```sh
cod-sync my_deck.cod list.txt --yes
```

### Interactive keys

At each change prompt:

| key | action |
| --- | --- |
| `y` / Enter | apply this change |
| `n` | skip this change |
| `a` | apply this change and everything remaining |
| `s` | stop reviewing, write what's been approved so far |
| `q` | quit without writing anything |

## What it does and doesn't touch

- **Quantities:** updated in place; printing pins on the card are kept.
- **Removed cards:** the entire `<card .../>` line is deleted.
- **Added cards:** a new `<card number="N" name="..."/>` line is appended
  to the relevant zone, with no printing pin — you can pick the printing
  later inside Cockatrice.
- **Everything else** in the `.cod` (deckname, format, banner card,
  comments, tags, indentation) is preserved exactly.

Maybeboards from Moxfield/Archidekt are ignored. The commander goes into
the `main` zone (which is how Cockatrice stores it for EDH decks).

## Tests

```sh
pytest -q
```

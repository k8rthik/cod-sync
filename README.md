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

Two subcommands:

```sh
cod-sync sync <local.cod> <source>      # sync one file
cod-sync dir  <directory> [--recursive] # walk a folder, prompt per file
```

A `<source>` is one of:

- `https://www.moxfield.com/decks/<id>`
- `https://archidekt.com/decks/<id>` (or `.../<id>/<slug>`)
- A path to a plain-text decklist (MTGA/MTGO format; `Sideboard` header
  or `SB:` line prefix both supported)

Both subcommands accept `--dry-run` (don't write) and `--yes` (apply
every change without prompting).

### `sync` examples

Interactive review against a Moxfield deck:

```sh
cod-sync sync ~/Library/Application\ Support/Cockatrice/Cockatrice/decks/b3/b3_kadena.cod \
              https://www.moxfield.com/decks/abc123
```

Preview only:

```sh
cod-sync sync my_deck.cod https://archidekt.com/decks/12345 --dry-run
```

Apply everything from a text file without prompting:

```sh
cod-sync sync my_deck.cod list.txt --yes
```

### `dir` examples

Walk every `.cod` in a folder, prompt for a URL per deck:

```sh
cod-sync dir ~/Library/Application\ Support/Cockatrice/Cockatrice/decks/b3
```

For each file you'll see the deckname and a prompt:

```
[1/15] b3_kadena.cod  — Flip The Bird
  source URL/path (empty=skip, q=quit): https://archidekt.com/decks/23168622
```

- Enter a URL or text-file path → diff + interactive review.
- Empty line (or `s`) → skip this deck.
- `q` → stop walking; previously-approved changes remain written.

#### URL memory

After you sync a deck against a URL once, that URL is stashed in the
deck's `<comments>` field as a single marker line:

```
cod-sync-source: https://archidekt.com/decks/23168622
```

Next time you walk the directory, the prompt shows the remembered URL
and an empty Enter uses it:

```
[1/15] b3_kadena.cod  — Flip The Bird
  stored: https://archidekt.com/decks/23168622
  source URL/path (empty=use stored, s=skip, q=quit):
```

This also works on single-file `cod-sync sync` — any URL you sync
against is stored automatically. Text-file sources are not stored.

Recurse into subfolders with `-r`:

```sh
cod-sync dir ~/Library/Application\ Support/Cockatrice/Cockatrice/decks -r
```

### Interactive review keys

At each change prompt (in both `sync` and `dir` mode):

| key | action |
| --- | --- |
| `y` / Enter | apply this change |
| `n` | skip this change |
| `a` | apply this change and everything remaining |
| `s` | stop reviewing this deck, write what's been approved so far |
| `q` | quit this deck without writing anything (dir mode: also stops the walk) |

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

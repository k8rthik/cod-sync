# cod-sync

Sync your Cockatrice `.cod` decks with Moxfield or Archidekt without losing your printings.

You update a deck on Moxfield. A week later you sit down to playtest in Cockatrice and the list is stale. Exporting from Moxfield and reimporting works, technically, but it strips every printing you picked and the banner card with it. cod-sync fixes this by making the smallest possible edit. It pulls the canonical list, diffs it against your `.cod`, and applies only the changes you approve. Everything else stays put.

## Install

```sh
git clone https://github.com/k8rthik/cod-sync.git
cd cod-sync
pip install -e .
```

Python 3.10 or newer. `requests` is the only runtime dependency. The CLI installs as `cod-sync`.

## Use it

Two subcommands. The first syncs one file:

```sh
cod-sync sync my_deck.cod https://www.moxfield.com/decks/abc123
```

The second walks a folder and prompts you for a URL per deck:

```sh
cod-sync dir ~/Library/Application\ Support/Cockatrice/Cockatrice/decks/b3
```

`dir` defaults to the current directory if you don't pass one. Add `-r` to recurse into subfolders. Both subcommands take `--dry-run` to preview without writing, and `--yes` to skip the per-change prompts and accept the whole diff.

When the diff appears, walk through it: `y` accepts a change, `n` skips it, `a` accepts everything remaining, `s` stops reviewing this deck and writes whatever you've approved so far, and `q` bails out without writing. In `dir` mode, `q` also stops the walk.

A source can be a Moxfield URL, an Archidekt URL, or a path to a plain-text decklist in MTGA or MTGO format. `Sideboard` section headers work. So do `SB:` line prefixes.

## URL memory

The first time you sync a deck against a URL, cod-sync writes one line into the deck's `<comments>`:

```
cod-sync-source: https://archidekt.com/decks/23168622
```

Anything you already had in comments is left alone. Only this single line is managed by the tool.

Next time you walk the folder, decks with a stored URL prompt like this:

```
[1/15] b3_kadena.cod  - Flip The Bird
  stored: https://archidekt.com/decks/23168622
  source URL/path (empty=use stored, s=skip, q=quit):
```

Hit enter to use it. Paste a new URL to switch sources, which also rewrites the marker. Text-file paths aren't stored, since they usually aren't portable across machines.

## What it changes, and what it leaves alone

Quantities update. Cards you removed online have their `<card .../>` line deleted. Cards you added show up at the bottom of the right zone as bare `<card number="N" name="..."/>` entries, with no printing pinned, so you can pick the art in Cockatrice yourself.

Pins on cards you didn't change (`setShortName`, `collectorNumber`, `uuid`) are never rewritten. Same goes for the banner card, the deckname, the format, your tags, and any comment text outside the marker line. The file's indentation and attribute order match what Cockatrice writes natively. A no-op sync produces a byte-identical file, unless the URL marker is being written for the first time.

## A few things worth knowing

Maybeboards don't enter the diff at all. Cards in Moxfield's maybeboard, or in an Archidekt category flagged `includedInDeck: false`, are filtered out before comparison.

Commanders end up in the `main` zone. That's how Cockatrice stores them for EDH, and it's where both Moxfield's `commanders` board and Archidekt's "Commander" category get routed. Companions go to `main` too. If you're syncing a Constructed deck where the companion belongs in the sideboard, you'll need to move it by hand for now.

When the remote returns a card as `Front // Back` and your local file has just `Front`, the two get matched automatically. This works the other direction too. New double-faced cards are added under whatever name the source provided.

A card listed multiple times in the same zone, like nine Nazgûl entries each with their own art, is treated as one logical card by the diff. If the source has more copies than you do, cod-sync appends a new bare entry for the delta instead of bumping every printing. If it has fewer, the tool reduces from the most recently added printing first. A removal drops every entry of the card.

## Sources

**Moxfield.** URLs like `https://www.moxfield.com/decks/<id>`. Reads from the public v3 API at `api2.moxfield.com`. Public decks only; no login needed.

**Archidekt.** URLs like `https://archidekt.com/decks/<id>`, optionally with a trailing slug. Reads from `archidekt.com/api/decks/<id>/`.

**Plain text.** Any local file in MTGA or MTGO export format. Recognized section headers include `Deck`, `Mainboard`, `Commander`, `Sideboard`, and `Side`. The MTGO `SB:` line prefix works too. Lines starting with `//` or `#` are treated as comments. Anything in parentheses after a card name (set code, collector number) is ignored.

## Development

```sh
pip install -e .
pytest -q
```

The codebase is small enough to read in one sitting. `cli.py` holds the CLI, the directory walk, and the interactive review. `cod.py` is the format-preserving parser and writer. `diff.py` computes the per-zone change list and handles DFC name matching. `sourcetag.py` manages the URL marker in `<comments>`. Each source lives in its own file under `sources/`. Tests sit next to the code and cover round-trip fidelity, diffing, multi-printing edits, and URL stash behavior.

Pull requests welcome. If you change behavior, add a test for it.

## Status

Built for the maintainer's own deck folder and used daily. The Moxfield and Archidekt fetchers ride on those sites' current public APIs and may need patches if they change.

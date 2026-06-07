# cod-sync

Sync your Cockatrice `.cod` decks with Moxfield or Archidekt without losing your printings.

You update a deck on Moxfield. A week later you sit down to playtest in Cockatrice and the list is stale. Exporting from Moxfield and reimporting works, technically, but it strips every printing you picked and the banner card with it. cod-sync fixes this by making the smallest possible edit. It pulls the canonical list, diffs it against your `.cod`, and applies only the changes you approve. Everything else stays put.

When the local file doesn't exist yet, cod-sync can also create it from the same URL, naming the deck whatever Moxfield or Archidekt called it.

## Install

```sh
git clone https://github.com/k8rthik/cod-sync.git
cd cod-sync
pip install -e .
```

Python 3.10 or newer. `requests` is the only runtime dependency. The CLI installs as `cod-sync`.

## Use it

No subcommands. cod-sync takes one positional argument and decides what to do based on what you passed.

```sh
cod-sync                                          # walk the current folder
cod-sync ~/decks --recursive                      # walk a folder, recursing into subfolders
cod-sync foo.cod https://moxfield.com/decks/abc   # sync foo.cod against a URL
cod-sync foo.cod                                  # sync against whatever URL is stored inside foo.cod
cod-sync https://moxfield.com/decks/abc           # create a new deck in cwd, named after the remote
cod-sync foo.cod --info                           # print the deck's contents and metrics
```

Rules behind the dispatch:

A URL as the first argument creates a fresh deck. The filename comes from the remote's title, lowercased with spaces turned into underscores, written into the current directory. If the target name is already taken, cod-sync stops and tells you.

A directory as the first argument walks every `.cod` in it and prompts you per deck. Add `-r` to descend into subfolders.

A file as the first argument syncs that file. If you pass a URL too, the URL wins. If you don't, cod-sync uses whatever URL was stashed in the deck on its last sync. With no URL passed and none stored, you get an error.

A bare deck name without the extension is fine: `cod-sync mydeck` is the same as `cod-sync mydeck.cod`.

`--dry-run` (`-n`) prints the diff and writes nothing. `--yes` (`-y`) auto-accepts every prompt — per-card review, "create new deck?", "update stored URL?", "update deckname?", all of them. `--recursive` (`-r`) only does anything when the target is a directory.

`--info` (`-i`) is the read-only escape hatch. Pointed at a deck file, it prints the deckname, format, banner card, stored source URL, a per-zone listing (card name plus rolled-up quantity), and counts for total / unique / pinned. Nothing is fetched, nothing is written. It refuses to run against a URL or a directory.

Two combinations are rejected with a clear error: a directory plus a URL (no way to fan a single URL out across decks), and two URLs (only one source per deck).

When the diff appears for an existing deck, walk through it card by card: `y` accepts, `n` skips, `a` accepts everything left, `s` stops reviewing and writes whatever's approved so far, `q` bails out without writing. When you create a new deck from a URL you get a single confirmation instead — declining cancels the whole creation.

A source can be a Moxfield URL, an Archidekt URL, or a path to a plain-text decklist in MTGA or MTGO format. `Sideboard` section headers work. So do `SB:` line prefixes.

## Deckname and URL drift

When you sync an existing deck against a URL that differs from the one stored in its comments, cod-sync stops and asks before overwriting the marker. Same when the remote's deck title differs from your local `<deckname>`. Default is to keep the local value, so a stray prompt won't accidentally rename your deck. `-y` auto-accepts both prompts.

For brand-new decks (file didn't exist), both fields get populated from the remote without asking — there's nothing local to overwrite.

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

Double-faced cards get reduced to the front face. Moxfield and Archidekt return names like `Storm the Vault // Vault of Catlacan`, but Cockatrice's card database stores those under just `Storm the Vault`. cod-sync strips the back face at the source layer so new cards land in a form Cockatrice can load. If your local file already uses the full `Front // Back` form, the diff still matches it correctly and leaves the existing key untouched.

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

The codebase is small enough to read in one sitting. `cli.py` holds the positional dispatcher, the directory walk, the unified per-file sync, and the bare-URL flow. `cod.py` is the format-preserving parser and writer. `diff.py` computes the per-zone change list and handles DFC name matching. `sourcetag.py` manages the URL marker in `<comments>`. Each source lives in its own file under `sources/`, with the shared `RemoteDeck` type in `sources/types.py`. Tests sit next to the code and cover round-trip fidelity, diffing, multi-printing edits, URL stash behavior, DFC normalization, the dispatcher, single-file sync, and bare-URL creation.

Pull requests welcome. If you change behavior, add a test for it.

## Status

Built for the maintainer's own deck folder and used daily. The Moxfield and Archidekt fetchers ride on those sites' current public APIs and may need patches if they change.

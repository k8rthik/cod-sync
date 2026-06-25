# cod-sync

Sync your Cockatrice `.cod` decks with Moxfield, Archidekt, or ManaBox without losing your printings.

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

`--dry-run` (`-n`) prints the diff and writes nothing. `--yes` (`-y`) auto-accepts every prompt: per-card review, "create new deck?", "update stored URL?", "update deckname?", and the walk's "sync against stored URL?". A directory walk under `-y` runs hands-free when every deck has a stored URL. `--quiet` (`-q`) suppresses informational output and implies `--yes`; errors still print to stderr. `--recursive` (`-r`) only does anything when the target is a directory.

`--info` (`-i`) is the read-only escape hatch. Pointed at a deck file, it prints the deckname, format, banner card, stored source URL, a per-zone listing (card name plus rolled-up quantity), and counts for total / unique / pinned. Nothing is fetched, nothing is written. It refuses to run against a URL or a directory.

Two combinations are rejected with a clear error: a directory plus a URL (no way to fan a single URL out across decks), and two URLs (only one source per deck).

When the diff appears for an existing deck, walk through it card by card: `y` accepts, `n` skips, `a` accepts everything left, `i` ignores the card from now on, `s` stops reviewing and writes whatever's approved so far, `q` bails out without writing. When you create a new deck from a URL you get a single confirmation instead — declining cancels the whole creation.

`i` is the "stop touching this card" answer. The change is skipped and a `cod-sync-ignore: <card name>` line is written into the deck's comments; future syncs show the suppressed change as a dimmed `(ignored)` note instead of proposing it. To un-ignore, delete that line — it's visible right in Cockatrice's comments box.

A source can be a Moxfield URL, an Archidekt URL, a ManaBox share URL, or a path to a plain-text decklist in MTGA or MTGO format. `Sideboard` section headers work. So do `SB:` line prefixes.

## Deckname and URL drift

When you sync an existing deck against a URL that differs from the one stored in its comments, cod-sync stops and asks before overwriting the marker. Same when the remote's deck title differs from your local `<deckname>`. Default is to keep the local value, so a stray prompt won't accidentally rename your deck. `-y` auto-accepts both prompts. Names that differ only in capitalization or surrounding whitespace are treated as identical, so `"Flip The Bird"` vs `"Flip the Bird"` won't trigger anything.

For brand-new decks (file didn't exist), both fields get populated from the remote without asking — there's nothing local to overwrite.

## URL memory

The first time you sync a deck against a URL, cod-sync writes one line into the deck's `<comments>`:

```
cod-sync-source: https://archidekt.com/decks/23168622
```

Anything you already had in comments is left alone. The tool manages only its own marker lines: this one, and the `cod-sync-ignore:` lines described above.

Next time you walk the folder, decks with a stored URL prompt like this:

```
[1/15] b3_kadena.cod  - Flip The Bird
  stored: https://archidekt.com/decks/23168622
  Sync against stored URL? [Y/n/q]:
```

Hit enter (or `y`) to sync. `n` skips this deck. `q` exits the walk. With `-y` the prompt is suppressed and every stored URL is accepted, so `cod-sync ~/decks -y` runs the whole folder hands-free.

To sync this deck against a different URL just once, exit the walk and run `cod-sync foo.cod <new URL>`. That path also asks before overwriting the stored marker. Text-file paths aren't stored, since they usually aren't portable across machines.

Decks without a stored URL still ask for a source:

```
  source URL/path (empty=skip, q=quit):
```

## What it changes, and what it leaves alone

Quantities update. Cards you removed online have their `<card .../>` line deleted. Cards you added show up at the bottom of the right zone as bare `<card number="N" name="..."/>` entries, with no printing pinned, so you can pick the art in Cockatrice yourself.

Pins on cards you didn't change (`setShortName`, `collectorNumber`, `uuid`) are never rewritten. Same goes for the banner card, the deckname, the format, your tags, and any comment text outside the marker line. The file's indentation and attribute order match what Cockatrice writes natively. A no-op sync produces a byte-identical file, unless the URL marker is being written for the first time.

## A few things worth knowing

Maybeboards don't enter the diff at all. Cards in Moxfield's maybeboard, or in an Archidekt category flagged `includedInDeck: false`, are filtered out before comparison.

Commanders end up in the `side` zone. Cockatrice has no dedicated commander zone and renders the commander pin only from the sideboard, so both Moxfield's `commanders` board and Archidekt's "Commander" category get routed there. Companions go to `side` for the same reason.

Multi-face card names are shaped to Cockatrice's form using each card's layout. True double-faced cards (transform and modal DFCs) get reduced to the front face: Moxfield and Archidekt return names like `Storm the Vault // Vault of Catlacan`, but Cockatrice's card database stores those under just `Storm the Vault`. Cards whose halves share a single face — split cards, the Duskmourn "Room" enchantments, aftermath cards, adventures (including Tarkir omens), and prepare cards — keep their full `A // B` name, because that's how Cockatrice stores them. Every deck-site fetcher reads the layout from its source, and the Scryfall fallback reads it from the lookup response, so plain-text decklists get the same treatment. A local file holding a stale shape from before this fix (a front-half Room name, or a full-form DFC name) heals on the next sync via a remove + add pair.

Reskin flavor names get mapped to the canonical card name. Secret Lair drops do things like ship `Unstable Harmonics`, which Moxfield and Archidekt treat as a distinct card but Cockatrice only knows as `Rhystic Study`. cod-sync ships a bundled dictionary of every Scryfall reskin known at release time, generated by `scripts/refresh_seed.py`. Anything not in the bundle falls back to Scryfall's `/cards/collection` endpoint in a single batched POST per sync; results are cached to `~/.cache/cod-sync/alt_names.json` so the same unknown card never round-trips twice. Reskins released after the bundled seed was refreshed get caught by this fallback automatically. Set `COD_SYNC_NO_NETWORK=1` to skip the fallback entirely; unknown names then pass through unchanged and Cockatrice rejects them on import.

Every mapping a sync applies is shown as a dimmed `alt-name: "Unstable Harmonics" → "Rhystic Study"` line, and the first time a mapping is seen you're asked what to do with it: accept it, keep the printed name, or type a replacement (useful if your Cockatrice database uses a different name, e.g. a custom set). Your answer is saved, so no name asks twice — across all your decks. `-y` accepts and saves the proposal silently; `--dry-run` shows the mappings without asking or saving anything.

A card listed multiple times in the same zone, like nine Nazgûl entries each with their own art, is treated as one logical card by the diff. If the source has more copies than you do, cod-sync appends a new bare entry for the delta instead of bumping every printing. If it has fewer, the tool reduces from the most recently added printing first. A removal drops every entry of the card.

## Sources

**Moxfield.** URLs like `https://www.moxfield.com/decks/<id>`. Reads from the public v3 API at `api2.moxfield.com`. Public decks only; no login needed.

**Archidekt.** URLs like `https://archidekt.com/decks/<id>`, optionally with a trailing slug. Reads from `archidekt.com/api/decks/<id>/`.

**ManaBox.** Share URLs like `https://manabox.app/decks/<shareId>`. ManaBox has no public API, so cod-sync reads the deck out of the server-rendered share page itself. That makes it more fragile than the API-backed sources — a ManaBox site redesign can break it — so a network-gated test exercises the live page, and an unreadable page surfaces as a clean error rather than a crash. Public share links only.

**Plain text.** Any local file in MTGA or MTGO export format. Recognized section headers include `Deck`, `Mainboard`, `Commander`, `Sideboard`, and `Side`. The MTGO `SB:` line prefix works too. Lines starting with `//` or `#` are treated as comments. Anything in parentheses after a card name (set code, collector number) is ignored.

## Development

```sh
pip install -e .
pytest -q
```

The codebase is small enough to read in one sitting. `cod_sync/cli/` holds the positional dispatcher, the directory walk, the unified per-deck sync, and the bare-URL flow. `cod.py` is the format-preserving parser and writer. `diff.py` computes the per-zone change list. `dfc.py` shapes multi-face card names to Cockatrice's form. `sourcetag.py` manages the URL marker in `<comments>`. `alt_name.py` maps Secret Lair flavor names to canonical names via a bundled dict (`_seed_data.py`, refreshed by `scripts/refresh_seed.py`). Each source lives in its own file under `sources/`, with the shared `RemoteDeck` type in `sources/types.py`.

[ARCHITECTURE.md](./ARCHITECTURE.md) covers the design: data flow, name shaping, the alt-name cache, latency and threading. [CONTRIBUTING.md](./CONTRIBUTING.md) covers dev setup, tests, and lint. Pull requests welcome — if you change behavior, add a test for it.

## Status

Built for the maintainer's own deck folder and used daily. The Moxfield and Archidekt fetchers ride on those sites' current public APIs, and the ManaBox fetcher rides on its share-page markup, so any of them may need patches if those change.

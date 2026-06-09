# TODO

Open work across cod-sync, organized by what would actually catch bugs or
unlock the next feature wave rather than by category. Each item describes
the gap and why it matters; implementation details intentionally omitted
so this doc doesn't rot when the code moves.

## P2 — quality-of-life

Real value but lower urgency. Pick when scratching specific itches.

### Local alt-name management surface

The reskin disk cache lives at a fixed path under the user cache directory.
If Scryfall returns a wrong mapping or a user wants a one-off override,
the only way to fix it is to hand-edit JSON. A small subsurface to list,
set, and forget entries would help. Tension: would reintroduce
subcommand-style structure into a CLI that intentionally collapsed
subcommands. Worth thinking about whether it fits the positional grammar
or should be a separate dunder-prefixed entrypoint.

### More deck sources

The source layer is designed for cheap additions: each source is a small
module following the same shape. TappedOut, MTGGoldfish, Deckstats,
Decked Builder are common asks. Each is straightforward; the question is
which actually serve the user base.

### Parallelize Scryfall batches

Decks with many unknown cards split into multiple sequential network
batches. A modest thread pool would halve first-sync latency for these
edge cases. Small win in practice — only the very first sync of a fresh
install with a huge deck benefits — and adds concurrency surface area.
Defer unless someone actually feels the pain.

### CHANGELOG

Commit messages are descriptive, but there's no human-readable summary
mapping versions to user-visible changes. `VERSIONING.md` already
maintains a tier-and-justification table at the bottom; a proper
CHANGELOG.md keyed to the same versions would make upgrade decisions
easier for users who don't read git log.

### Maybeboard handling

Maybeboard contents are silently dropped today (see comments in
`sources/moxfield.py` and `sources/archidekt.py`). No one has asked for
them back, but it's an option that exists in both sources and isn't
represented in our model.

### Multi-printing output ordering

When a card with multiple printings gets a quantity increase, the new bare
entry is appended at the end of the zone. Some users would prefer adjacent
printings grouped together. Minor cosmetic, low priority.

### Text parser edge cases

The text-source parser handles MTGA/MTGO format reasonably but isn't tested
against edge cases users actually paste: parenthesized comments inline,
malformed quantities, mixed-case section headers, trailing whitespace
oddities. Each is a one-line test that would prevent a real future bug.

### Walk error-recovery summary

The walk currently aggregates a per-status count at the end (updated,
no-change, skipped, errors). When `errors > 0` the user has to scroll
back through interleaved output to see which files failed and why.
Collecting a small list of `(path, error)` and printing it as a footer
under the summary would make a multi-file walk far easier to triage.

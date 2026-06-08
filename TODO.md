# TODO

Open work across cod-sync, organized by what would actually catch bugs or
unlock the next feature wave rather than by category. Each item describes
the gap and why it matters; implementation details intentionally omitted
so this doc doesn't rot when the code moves.

## P1 — clear wins

These have meaningful payoff and bounded scope. Pick by what hurts most in
practice.

### Distinguish error modes in source fetchers

Today every source-fetch failure collapses to one error message regardless
of root cause. Deck deleted, deck made private, rate limit, timeout,
malformed JSON, unreachable host all look the same to the user. The fix is
to surface specific error types or codes per failure mode so the message
tells you what to do about it.

### Add at least one real-network integration test per source

Every source test is built on hand-crafted JSON payloads. The day a remote
API changes its response shape, every test still passes and every user
breaks. One opt-in test per source — gated behind a marker so the default
test run stays offline and fast — that fetches a public deck and asserts
basic shape would catch that class of breakage.

### Split the CLI module by responsibility

The CLI module currently mixes dispatch, file I/O, interactive prompts,
deck mutation, and diff formatting. The growth pressure is real: every new
feature lands by extending this one file. Splitting along responsibility
boundaries (routing, prompts, application logic, formatting) is a one-time
refactor that lowers the cost of every future feature. Worth doing before
the next two or three features land.

### Sync tags

Both source sites support tags or categories. Cockatrice supports a tags
field. Today we round-trip whatever was already local but never pull from
the remote. Syncing tags closes a gap between what users curate online and
what shows up in Cockatrice.

### Walk-parity: deckname and URL-conflict prompts

The single-file sync path prompts when the remote deckname differs from
the local one and when the URL stored in the .cod conflicts with the URL
being synced against. The directory-walk path does neither — it ignores
deckname entirely and silently overwrites the stored URL. The shared
per-deck core already exposes both behaviors as boolean knobs the walk
caller passes `False`. Enabling them is mechanically a one-line change
per knob, but mid-loop prompts during a multi-file walk are noisier than
a single-file sync; the right call may be always-on prompts, an opt-in
flag, or a batch-confirm at the top of the walk. Worth deciding before
adding any UX that the walk currently lacks.

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
mapping versions to user-visible changes. A standard CHANGELOG would help
users understand what they're getting when they upgrade.

### Maybeboard handling

Maybeboard contents are silently dropped today. No one has asked for them
back, but it's an option that exists in both sources and isn't represented
in our model.

### Multi-printing output ordering

When a card with multiple printings gets a quantity increase, the new bare
entry is appended at the end of the zone. Some users would prefer adjacent
printings grouped together. Minor cosmetic, low priority.

### Text parser edge cases

The text-source parser handles MTGA/MTGO format reasonably but isn't tested
against edge cases users actually paste: parenthesized comments inline,
malformed quantities, mixed-case section headers, trailing whitespace
oddities. Each is a one-line test that would prevent a real future bug.

## Tooling and project hygiene

These overlap with P0 and P1 but are listed together so they don't get
buried under feature items.

### Pre-commit hooks

Pre-commit configuration would run formatter, linter, and type checker
locally before commit, catching style drift and obvious bugs without
needing CI to do it. Low-friction once configured.

### Linter and formatter

Code style is consistent by hand today and vulnerable to drift as
contributors land changes. A configured formatter and linter makes
consistency mechanical and removes the need to litigate style in review.

### Release automation

Version bumps, tags, and pushes are manual. A workflow that runs on a tag
push to build wheels and publish is standard practice. Optional but
removes a class of "forgot to bump pyproject" mistakes.

### Contributor docs

There's no document explaining how to set up a dev environment, run the
tests, or what the codebase's conventions are. As soon as anyone other
than the original author wants to contribute, this becomes the blocker.

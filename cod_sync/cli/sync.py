"""Per-deck sync orchestration.

``_sync_deck`` is the one shared per-deck code path. The three modes
that call it — single-file sync (``_sync_file``), bare-URL import
(``_create_from_bare_url``), and directory walk (``_walk_directory``
in ``walk.py``) — differ only in how they *arrive* at the call:
sync loads an existing ``.cod`` and resolves its URL, import derives
a filename from the remote and delegates to sync, and walk iterates
a directory and asks per-file whether to sync. Once inside
``_sync_deck``, behavior is identical across all three callers; ``-y``
is the single knob that turns prompts into accept-all.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from cod_sync import alt_name, cod, diff, errors, sources, sourcetag

from . import _state, prompts, routing
from .apply import _apply, _import_preview_changes
from .formatting import (
    _BOLD,
    _DIM,
    _RESET,
    _format_source_error,
    _print_summary,
    _sanitize_filename,
)

SyncStatus = Literal["no_change", "updated", "created", "skipped", "dry_run"]


@dataclass(frozen=True)
class SyncOutcome:
    status: SyncStatus
    approved_count: int
    marker_changed: bool
    deckname_changed: bool
    banner_changed: bool = False
    tags_changed: bool = False
    ignores_changed: bool = False


def _apply_mapping_control(
    remote: sources.RemoteDeck, *, yes: bool, dry_run: bool, indent: str = ""
) -> sources.RemoteDeck:
    """Surface applied alt-name mappings and let the user control new ones.

    Every applied mapping is logged. Unsettled ones (not yet in the disk
    cache) prompt once — accept, keep the original printed name, or type
    a replacement — and the answer is persisted via `alt_name.set_override`,
    so the same name never prompts again on any deck. Under --yes the
    proposal is accepted and persisted without prompting; under --dry-run
    mappings are logged but nothing is written or asked.
    """
    if not remote.renames:
        return remote

    # One decision per original name, even when it appears in both zones.
    decisions: dict[str, str] = {}
    seen: set[str] = set()
    for r in remote.renames:
        if r.original in seen:
            continue
        seen.add(r.original)
        _state.say(f'{indent}{_DIM}alt-name: "{r.original}" → "{r.canonical}"{_RESET}')
        if r.settled or dry_run:
            continue
        if yes:
            alt_name.set_override(r.original, r.canonical)
            continue
        final = prompts._review_mapping(r.original, r.canonical, indent=indent)
        alt_name.set_override(r.original, final)
        if final != r.canonical:
            decisions[r.original] = final

    if not decisions:
        return remote

    # Un-merge precisely: move only each rename's own quantity off the
    # proposed canonical (which may also hold never-renamed copies).
    zones: sources.Zones = {zone: dict(cards) for zone, cards in remote.zones.items()}
    for r in remote.renames:
        replacement = decisions.get(r.original)
        if replacement is None:
            continue
        zone = zones[r.zone]
        remaining = zone.get(r.canonical, 0) - r.quantity
        if remaining > 0:
            zone[r.canonical] = remaining
        else:
            zone.pop(r.canonical, None)
        zone[replacement] = zone.get(replacement, 0) + r.quantity
    return sources.RemoteDeck(
        name=remote.name, zones=zones, tags=remote.tags, renames=remote.renames
    )


def _sync_deck(
    deck: cod.Deck,
    cod_path: str,
    remote_zones: dict[str, dict[str, int]],
    remote_name: str | None,
    remote_tags: tuple[str, ...],
    *,
    is_new_file: bool,
    url_to_remember: str | None,
    yes: bool,
    dry_run: bool,
    indent: str = "",
) -> SyncOutcome:
    """Run diff → approve → apply → save for one deck.

    Identical behavior regardless of caller; the only mode-dependent
    inputs are ``is_new_file`` (derived from whether the target ``.cod``
    exists) and ``indent`` (set by walk to nest per-deck output under
    its file header). ``-y`` collapses all confirm prompts into
    accept-all via ``_confirm(..., auto_yes=yes)``.
    """
    if is_new_file:
        changes = _import_preview_changes(remote_zones)
    else:
        changes = diff.compute(deck, remote_zones)
        # Ignored cards (cod-sync-ignore: markers in <comments>) never
        # enter the review; each suppressed change is still shown so the
        # user can see what the marker is holding back.
        ignored_names = sourcetag.get_ignored_names(deck.comments)
        if ignored_names:
            suppressed = [c for c in changes if c.name in ignored_names]
            if suppressed:
                changes = [c for c in changes if c.name not in ignored_names]
                for c in suppressed:
                    _state.say(f"{indent}{_DIM}(ignored) {c.describe()}{_RESET}")

    if changes:
        _print_summary(changes, indent=indent)

    if dry_run:
        if not changes:
            _state.say(f"{indent}{_DIM}No differences.{_RESET}")
        return SyncOutcome("dry_run", 0, False, False)

    if is_new_file:
        if not changes:
            _state.say(f"{indent}{_DIM}Remote source is empty. Nothing to create.{_RESET}")
            return SyncOutcome("no_change", 0, False, False)
        if not yes:
            # Sum quantities across all zones (main + side) — the prompt
            # promises a card count, not a unique-entry count.
            card_count = sum(c.remote_qty for c in changes)
            try:
                ans = (
                    input(f"{indent}Create {cod_path} with {card_count} card(s)? [Y/n] ")
                    .strip()
                    .lower()
                )
            except EOFError:
                ans = "n"
            if ans not in ("", "y", "yes"):
                _state.say(f"{indent}{_DIM}Aborted.{_RESET}")
                return SyncOutcome("skipped", 0, False, False)
        approved = changes
        to_ignore: list[str] = []
    elif changes and not yes:
        approved, to_ignore = prompts._review(changes, indent=indent)
    else:
        approved = changes if yes else []
        to_ignore = []

    final_deck = _apply(deck, approved) if approved else deck

    deckname_changed = False
    if is_new_file:
        new_deckname = remote_name or Path(cod_path).stem
        if new_deckname != final_deck.deckname:
            final_deck = replace(final_deck, deckname=new_deckname)
            deckname_changed = True
    elif remote_name and prompts._names_differ(remote_name, final_deck.deckname):
        if prompts._confirm(
            f"Local name:  {final_deck.deckname or '(none)'}\n"
            f"Remote name: {remote_name}\n"
            f"Update deckname?",
            default=False,
            auto_yes=yes,
        ):
            final_deck = replace(final_deck, deckname=remote_name)
            deckname_changed = True

    marker_changed = False
    if url_to_remember is not None:
        stored = sourcetag.get_source_url(final_deck.comments)
        if stored is None or stored == url_to_remember:
            update = True
        else:
            update = prompts._confirm(
                f"Stored URL: {stored}\nNew URL:    {url_to_remember}\nUpdate stored URL?",
                default=False,
                auto_yes=yes,
            )
        if update:
            new_comments = sourcetag.set_source_url(final_deck.comments, url_to_remember)
            if new_comments != final_deck.comments:
                final_deck = replace(final_deck, comments=new_comments)
                marker_changed = True

    # Banner lives on the local deck (user-set in Cockatrice). Only rewrite
    # it when it's genuinely orphaned — i.e. the canonical name is already
    # in the post-apply card list AND the original (reskin) name is NOT.
    # In that state the banner used to reference a card in the deck and
    # got stranded when the card list was canonicalized; restoring the
    # link preserves the user's intent. Any other state (reskin still in
    # the deck, custom override, unknown name) leaves the banner alone.
    # The card-set check runs first: when the banner already names a card
    # in the deck (the common case) we skip the alt_name lookup entirely —
    # a cold-cache unknown banner would otherwise cost a Scryfall round
    # trip per sync just to learn nothing needs flipping.
    banner_changed = False
    if final_deck.banner_card_name:
        original = final_deck.banner_card_name
        card_names = {c.name for z in final_deck.zones for c in z.cards}
        if original not in card_names:
            canonical = alt_name.canonicalize(original)
            if canonical != original and canonical in card_names:
                final_deck = replace(final_deck, banner_card_name=canonical)
                banner_changed = True

    # Union deck-level tags from the remote into the local set. Never destructive:
    # local-only tags survive, and dedupe is case-insensitive but preserves the
    # casing of whichever side introduced each tag.
    tags_changed = False
    if remote_tags:
        local_tags = cod.tags_xml_to_list(final_deck.tags_xml)
        seen = {t.casefold() for t in local_tags}
        merged: list[str] = list(local_tags)
        for t in remote_tags:
            key = t.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(t)
        if tuple(merged) != local_tags:
            final_deck = replace(final_deck, tags_xml=cod.tags_list_to_xml(tuple(merged)))
            tags_changed = True

    # Persist `i` answers as cod-sync-ignore: marker lines so future
    # syncs stop proposing changes for those cards.
    ignores_changed = False
    if to_ignore:
        new_comments = final_deck.comments
        for name in to_ignore:
            new_comments = sourcetag.add_ignored_name(new_comments, name)
        if new_comments != final_deck.comments:
            final_deck = replace(final_deck, comments=new_comments)
            ignores_changed = True

    if (
        not is_new_file
        and not approved
        and not marker_changed
        and not deckname_changed
        and not banner_changed
        and not tags_changed
        and not ignores_changed
    ):
        if not changes:
            _state.say(f"{indent}{_DIM}No differences.{_RESET}")
            return SyncOutcome("no_change", 0, False, False)
        _state.say(f"{indent}{_DIM}No changes applied.{_RESET}")
        return SyncOutcome("skipped", 0, False, False)

    cod.save(final_deck, cod_path)

    if is_new_file:
        _state.say(f"{indent}{_BOLD}Wrote new deck to {cod_path}{_RESET}")
        return SyncOutcome(
            "created",
            len(approved),
            marker_changed,
            deckname_changed,
            banner_changed,
            tags_changed,
        )

    parts: list[str] = []
    if approved:
        parts.append(f"{diff.total_card_delta(approved)} change(s)")
    if marker_changed:
        parts.append("source URL")
    if deckname_changed:
        parts.append("deckname")
    if banner_changed:
        parts.append("banner")
    if tags_changed:
        parts.append("tags")
    if ignores_changed:
        parts.append("ignores")
    _state.say(f"{indent}{_BOLD}Wrote {' + '.join(parts)} to {cod_path}{_RESET}")
    return SyncOutcome(
        "updated",
        len(approved),
        marker_changed,
        deckname_changed,
        banner_changed,
        tags_changed,
        ignores_changed,
    )


def _sync_file(
    cod_path: str,
    url: str | None,
    *,
    yes: bool,
    dry_run: bool,
    include_maybeboard: bool = False,
    prefetched: sources.RemoteDeck | None = None,
) -> int:
    """Sync one deck file. ``prefetched`` carries an already-fetched remote
    (the bare-URL flow needs the title before it knows the filename) so the
    deck isn't downloaded twice."""
    exists = os.path.exists(cod_path)

    if exists:
        try:
            deck = cod.load(cod_path)
        except (OSError, ValueError) as e:
            print(f"error: failed to load {cod_path}: {e}", file=sys.stderr)
            return 2
    else:
        deck = cod.Deck()

    if url is None:
        url = sourcetag.get_source_url(deck.comments)
        if url is None:
            print(
                f"error: no source URL passed and none stored in {cod_path}. "
                f"Provide one: `cod-sync {cod_path} <URL>`.",
                file=sys.stderr,
            )
            return 2
        _state.say(f"{_DIM}using stored URL: {url}{_RESET}")

    if prefetched is not None:
        remote = prefetched
    else:
        # The remote API round-trip is the slow part of a sync (often
        # seconds); say so up front instead of sitting silent until the
        # diff appears.
        _state.say(f"{_DIM}fetching {url} ...{_RESET}")
        try:
            remote = sources.fetch(url, include_maybeboard=include_maybeboard)
        except errors.SourceError as e:
            print(_format_source_error(e), file=sys.stderr)
            return 2
        except Exception as e:
            print(f"error: failed to fetch {url}: {e}", file=sys.stderr)
            return 2

    remote = _apply_mapping_control(remote, yes=yes, dry_run=dry_run)

    _sync_deck(
        deck,
        cod_path,
        remote.zones,
        remote.name,
        remote.tags,
        is_new_file=not exists,
        url_to_remember=url if routing._is_url(url) else None,
        yes=yes,
        dry_run=dry_run,
    )
    return 0


def _create_from_bare_url(
    url: str, *, yes: bool, dry_run: bool, include_maybeboard: bool = False
) -> int:
    _state.say(f"{_DIM}fetching {url} ...{_RESET}")
    try:
        remote = sources.fetch(url, include_maybeboard=include_maybeboard)
    except errors.SourceError as e:
        print(_format_source_error(e), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: failed to fetch {url}: {e}", file=sys.stderr)
        return 2

    name = _sanitize_filename(remote.name) or "imported_deck"
    target = Path.cwd() / f"{name}.cod"
    if target.exists():
        _state.say(f"{_DIM}syncing existing {target}{_RESET}")

    return _sync_file(
        str(target),
        url,
        yes=yes,
        dry_run=dry_run,
        include_maybeboard=include_maybeboard,
        prefetched=remote,
    )

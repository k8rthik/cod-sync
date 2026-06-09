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

from cod_sync import alt_name, cli, cod, diff, errors, sources, sourcetag

from . import _state
from .apply import _apply, _import_preview_changes
from .formatting import (
    _BOLD,
    _DIM,
    _RESET,
    _format_source_error,
    _print_summary,
    _sanitize_filename,
)
from .prompts import _names_differ, _review
from .routing import _is_url


SyncStatus = Literal["no_change", "updated", "created", "skipped", "dry_run"]


@dataclass(frozen=True)
class SyncOutcome:
    status: SyncStatus
    approved_count: int
    marker_changed: bool
    deckname_changed: bool
    banner_changed: bool = False
    tags_changed: bool = False


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
            try:
                ans = input(
                    f"{indent}Create {cod_path} with {len(changes)} card(s)? [Y/n] "
                ).strip().lower()
            except EOFError:
                ans = "n"
            if ans not in ("", "y", "yes"):
                _state.say(f"{indent}{_DIM}Aborted.{_RESET}")
                return SyncOutcome("skipped", 0, False, False)
        approved = changes
    else:
        approved = (changes if yes else _review(changes, indent=indent)) if changes else []

    final_deck = _apply(deck, approved) if approved else deck

    deckname_changed = False
    if is_new_file:
        new_deckname = remote_name or Path(cod_path).stem
        if new_deckname != final_deck.deckname:
            final_deck = replace(final_deck, deckname=new_deckname)
            deckname_changed = True
    elif remote_name and _names_differ(remote_name, final_deck.deckname):
        # cli._confirm (not prompts._confirm) so test patches on
        # `cod_sync.cli._confirm` reach this call site.
        if cli._confirm(
            f"Local name:  {final_deck.deckname or '(none)'}\n"
            f"Remote name: {remote_name}\n"
            f"Update deckname?",
            default=False, auto_yes=yes,
        ):
            final_deck = replace(final_deck, deckname=remote_name)
            deckname_changed = True

    marker_changed = False
    if url_to_remember is not None:
        stored = sourcetag.get_source_url(final_deck.comments)
        if stored is None or stored == url_to_remember:
            update = True
        else:
            # cli._confirm (not prompts._confirm) so test patches on
            # `cod_sync.cli._confirm` reach this call site.
            update = cli._confirm(
                f"Stored URL: {stored}\n"
                f"New URL:    {url_to_remember}\n"
                f"Update stored URL?",
                default=False, auto_yes=yes,
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
    banner_changed = False
    if final_deck.banner_card_name:
        original = final_deck.banner_card_name
        canonical = alt_name.canonicalize(original)
        if canonical != original:
            card_names = {c.name for z in final_deck.zones for c in z.cards}
            if canonical in card_names and original not in card_names:
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

    if (
        not is_new_file
        and not approved
        and not marker_changed
        and not deckname_changed
        and not banner_changed
        and not tags_changed
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
            "created", len(approved), marker_changed, deckname_changed, banner_changed,
            tags_changed,
        )

    parts: list[str] = []
    if approved:
        parts.append(f"{len(approved)} change(s)")
    if marker_changed:
        parts.append("source URL")
    if deckname_changed:
        parts.append("deckname")
    if banner_changed:
        parts.append("banner")
    if tags_changed:
        parts.append("tags")
    _state.say(f"{indent}{_BOLD}Wrote {' + '.join(parts)} to {cod_path}{_RESET}")
    return SyncOutcome(
        "updated", len(approved), marker_changed, deckname_changed, banner_changed,
        tags_changed,
    )


def _sync_file(cod_path: str, url: str | None, *, yes: bool, dry_run: bool) -> int:
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

    try:
        remote = sources.fetch(url)
    except errors.SourceError as e:
        print(_format_source_error(e), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: failed to fetch {url}: {e}", file=sys.stderr)
        return 2

    _sync_deck(
        deck, cod_path, remote.zones, remote.name, remote.tags,
        is_new_file=not exists,
        url_to_remember=url if _is_url(url) else None,
        yes=yes, dry_run=dry_run,
    )
    return 0


def _create_from_bare_url(url: str, *, yes: bool, dry_run: bool) -> int:
    try:
        remote = sources.fetch(url)
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

    return _sync_file(str(target), url, yes=yes, dry_run=dry_run)

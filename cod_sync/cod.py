"""Parser and format-preserving writer for Cockatrice .cod files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Card:
    name: str
    quantity: int
    set_short_name: str | None = None
    collector_number: str | None = None
    uuid: str | None = None

    def with_quantity(self, quantity: int) -> Card:
        return replace(self, quantity=quantity)


@dataclass(frozen=True)
class Zone:
    name: str
    cards: tuple[Card, ...] = ()

    def with_cards(self, cards: tuple[Card, ...]) -> Zone:
        return replace(self, cards=cards)


@dataclass(frozen=True)
class Deck:
    deckname: str = ""
    format: str = ""
    comments: str = ""
    last_loaded_timestamp: str = ""
    banner_card_name: str | None = None
    banner_card_provider_id: str = ""
    tags_xml: str = "<tags/>"
    zones: tuple[Zone, ...] = ()

    def zone(self, name: str) -> Zone | None:
        for z in self.zones:
            if z.name == name:
                return z
        return None

    def with_zones(self, zones: tuple[Zone, ...]) -> Deck:
        return replace(self, zones=zones)


_KNOWN_ZONES = ("main", "side")


def load(path: str) -> Deck:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "cockatrice_deck":
        raise ValueError(f"Not a Cockatrice deck (root tag: {root.tag!r})")

    banner = root.find("bannerCard")
    banner_name = banner.text if banner is not None else None
    banner_pid = banner.get("providerId", "") if banner is not None else ""

    tags_el = root.find("tags")
    tags_xml = _serialize_tags(tags_el) if tags_el is not None else "<tags/>"

    zones: list[Zone] = []
    for zone_el in root.findall("zone"):
        cards: list[Card] = []
        for c in zone_el.findall("card"):
            cards.append(
                Card(
                    name=c.get("name", ""),
                    quantity=int(c.get("number", "0")),
                    set_short_name=c.get("setShortName"),
                    collector_number=c.get("collectorNumber"),
                    uuid=c.get("uuid"),
                )
            )
        zones.append(Zone(name=zone_el.get("name", ""), cards=tuple(cards)))

    return Deck(
        deckname=root.findtext("deckname", default="") or "",
        format=root.findtext("format", default="") or "",
        comments=root.findtext("comments", default="") or "",
        last_loaded_timestamp=root.findtext("lastLoadedTimestamp", default="") or "",
        banner_card_name=banner_name,
        banner_card_provider_id=banner_pid,
        tags_xml=tags_xml,
        zones=tuple(zones),
    )


def _serialize_tags(tags_el: ET.Element) -> str:
    has_children = len(list(tags_el)) > 0
    has_text = (tags_el.text or "").strip() != ""
    if not has_children and not has_text:
        return "<tags/>"
    raw = ET.tostring(tags_el, encoding="unicode")
    return raw.strip()


def tags_xml_to_list(tags_xml: str) -> tuple[str, ...]:
    """Extract the text of each <tag> child from a stored tags_xml blob.
    Returns an empty tuple for the default `<tags/>` form. Raises ValueError
    on malformed XML or a non-<tags> root rather than masking it as empty."""
    try:
        root = ET.fromstring(tags_xml)
    except ET.ParseError as e:
        raise ValueError(f"Malformed tags_xml: {e}") from e
    if root.tag != "tags":
        raise ValueError(f"Not a tags element (root tag: {root.tag!r})")
    out: list[str] = []
    for child in root.findall("tag"):
        text = (child.text or "").strip()
        if text:
            out.append(text)
    return tuple(out)


def tags_list_to_xml(tags: tuple[str, ...]) -> str:
    """Serialize a tag list to Cockatrice's `<tags><tag>NAME</tag>...</tags>`
    form. Returns the self-closing `<tags/>` for an empty list."""
    if not tags:
        return "<tags/>"
    inner = "".join(f"<tag>{_xml_text(t)}</tag>" for t in tags)
    return f"<tags>{inner}</tags>"


def _xml_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _xml_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _card_line(card: Card) -> str:
    parts = [f'number="{card.quantity}"', f'name="{_xml_attr(card.name)}"']
    if card.set_short_name is not None:
        parts.append(f'setShortName="{_xml_attr(card.set_short_name)}"')
    if card.collector_number is not None:
        parts.append(f'collectorNumber="{_xml_attr(card.collector_number)}"')
    if card.uuid is not None:
        parts.append(f'uuid="{_xml_attr(card.uuid)}"')
    return "        <card " + " ".join(parts) + "/>"


def dump(deck: Deck) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<cockatrice_deck version="1">',
        f"    <lastLoadedTimestamp>{_xml_text(deck.last_loaded_timestamp)}</lastLoadedTimestamp>",
        f"    <deckname>{_xml_text(deck.deckname)}</deckname>",
        f"    <format>{_xml_text(deck.format)}</format>",
    ]
    if deck.banner_card_name is not None:
        lines.append(
            f'    <bannerCard providerId="{_xml_attr(deck.banner_card_provider_id)}">'
            f"{_xml_text(deck.banner_card_name)}</bannerCard>"
        )
    lines.append(f"    <comments>{_xml_text(deck.comments)}</comments>")
    lines.append(f"    {deck.tags_xml}")

    for zone in deck.zones:
        if not zone.cards:
            continue
        lines.append(f'    <zone name="{_xml_attr(zone.name)}">')
        for card in zone.cards:
            lines.append(_card_line(card))
        lines.append("    </zone>")
    lines.append("</cockatrice_deck>")
    return "\n".join(lines) + "\n"


def save(deck: Deck, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump(deck))

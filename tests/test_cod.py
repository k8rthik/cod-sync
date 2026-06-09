from pathlib import Path

from cod_sync import cod

FIXTURES = Path(__file__).parent / "fixtures"


def test_bare_round_trip_byte_for_byte():
    path = FIXTURES / "bare.cod"
    original = path.read_text(encoding="utf-8")
    assert cod.dump(cod.load(str(path))) == original


def test_pinned_round_trip_byte_for_byte():
    path = FIXTURES / "pinned.cod"
    original = path.read_text(encoding="utf-8")
    assert cod.dump(cod.load(str(path))) == original


def test_quantity_update_preserves_printing_pins():
    deck = cod.load(str(FIXTURES / "pinned.cod"))
    main = deck.zone("main")
    gamble = next(c for c in main.cards if c.name == "Gamble")
    assert gamble.set_short_name == "SLD"
    updated = gamble.with_quantity(2)
    assert updated.quantity == 2
    assert updated.set_short_name == "SLD"
    assert updated.collector_number == gamble.collector_number
    assert updated.uuid == gamble.uuid


def test_added_card_has_no_printing_pins():
    card = cod.Card(name="Black Lotus", quantity=1)
    line = cod._card_line(card)
    assert line == '        <card number="1" name="Black Lotus"/>'


def test_xml_escapes_special_attr_chars():
    card = cod.Card(name='A & "B"', quantity=1)
    line = cod._card_line(card)
    assert line == '        <card number="1" name="A &amp; &quot;B&quot;"/>'


# ----- deck-level tag helpers ----------------------------------------------


def test_tags_xml_to_list_empty_self_closing():
    assert cod.tags_xml_to_list("<tags/>") == ()


def test_tags_xml_to_list_reads_tag_children():
    xml = "<tags><tag>Budget</tag><tag>Combo</tag></tags>"
    assert cod.tags_xml_to_list(xml) == ("Budget", "Combo")


def test_tags_xml_to_list_skips_blank_tag_text():
    xml = "<tags><tag>Budget</tag><tag>   </tag><tag></tag><tag>Combo</tag></tags>"
    assert cod.tags_xml_to_list(xml) == ("Budget", "Combo")


def test_tags_list_to_xml_empty_emits_self_closing():
    assert cod.tags_list_to_xml(()) == "<tags/>"


def test_tags_list_to_xml_serializes_tag_children():
    assert cod.tags_list_to_xml(("Budget", "Combo")) == (
        "<tags><tag>Budget</tag><tag>Combo</tag></tags>"
    )


def test_tags_list_to_xml_escapes_special_chars():
    # Element text only needs &, <, > escaped — quotes are literal in text content.
    assert cod.tags_list_to_xml(("A & <B>",)) == ("<tags><tag>A &amp; &lt;B&gt;</tag></tags>")


def test_tags_helpers_round_trip():
    tags = ("Budget", "Combo", "EDH")
    assert cod.tags_xml_to_list(cod.tags_list_to_xml(tags)) == tags


def test_load_dump_preserves_populated_tags_block(tmp_path):
    src = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<cockatrice_deck version="1">\n'
        "    <lastLoadedTimestamp></lastLoadedTimestamp>\n"
        "    <deckname>Tagged</deckname>\n"
        "    <format></format>\n"
        "    <comments></comments>\n"
        "    <tags><tag>Budget</tag><tag>Combo</tag></tags>\n"
        '    <zone name="main">\n'
        '        <card number="1" name="Sol Ring"/>\n'
        "    </zone>\n"
        "</cockatrice_deck>\n"
    )
    path = tmp_path / "tagged.cod"
    path.write_text(src, encoding="utf-8")
    assert cod.dump(cod.load(str(path))) == src

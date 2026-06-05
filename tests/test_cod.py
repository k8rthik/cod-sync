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

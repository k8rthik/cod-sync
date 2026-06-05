from cod_sync.sources import text


def test_basic_quantities():
    result = text.parse("1 Sol Ring\n3 Forest\n")
    assert result == {"main": {"Sol Ring": 1, "Forest": 3}, "side": {}}


def test_x_suffix_on_quantity():
    result = text.parse("4x Lightning Bolt\n")
    assert result["main"] == {"Lightning Bolt": 4}


def test_multi_word_name_with_apostrophe():
    """Regression: lazy regex was eating trailing words like 'Cauldron'."""
    result = text.parse("1 Agatha's Soul Cauldron\n")
    assert result["main"] == {"Agatha's Soul Cauldron": 1}


def test_set_and_collector_number_are_stripped():
    result = text.parse("1 Sol Ring (CMM) 423\n")
    assert result["main"] == {"Sol Ring": 1}


def test_set_without_collector_number():
    result = text.parse("1 Sol Ring (CMM)\n")
    assert result["main"] == {"Sol Ring": 1}


def test_sideboard_header_switches_zone():
    result = text.parse("Deck\n1 Sol Ring\nSideboard\n1 Pithing Needle\n")
    assert result == {
        "main": {"Sol Ring": 1},
        "side": {"Pithing Needle": 1},
    }


def test_mtgo_sb_prefix():
    result = text.parse("1 Sol Ring\nSB: 1 Pithing Needle\n")
    assert result == {
        "main": {"Sol Ring": 1},
        "side": {"Pithing Needle": 1},
    }


def test_comments_and_blank_lines_ignored():
    result = text.parse("// comment\n\n# also a comment\n1 Sol Ring\n")
    assert result["main"] == {"Sol Ring": 1}


def test_duplicate_lines_sum():
    result = text.parse("1 Forest\n2 Forest\n")
    assert result["main"] == {"Forest": 3}

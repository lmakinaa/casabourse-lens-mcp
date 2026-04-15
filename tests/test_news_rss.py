from trading_tools.providers.news_rss import (
    _extract_symbols,
    _load_symbol_aliases,
    _sentiment_score,
    build_sentiment_snapshot,
)


def test_news_aliases_include_press_short_names():
    aliases = _load_symbol_aliases()

    # Ingestion legal-name coverage preserved.
    assert "ITISSALAT AL MAGHRIB" in aliases["IAM"] or "ITISSALAT AL-MAGHRIB" in aliases["IAM"]
    # Press short-name layer added.
    assert "MAROC TELECOM" in aliases["IAM"]
    assert "AKDITAL" in aliases["AKT"]
    assert "ATTIJARIWAFA" in aliases["ATW"]
    assert "MANAGEM" in aliases["MNG"]


def test_extract_symbols_matches_press_short_name():
    aliases = _load_symbol_aliases()

    found = _extract_symbols(
        "Akdital annonce un résultat en hausse",
        aliases,
    )
    assert "AKT" in found


def test_extract_symbols_word_boundary_ticker_match():
    aliases = _load_symbol_aliases()

    # Short ticker only reached via the word-boundary guard path.
    found = _extract_symbols("AKT gagne 5% aujourd'hui", aliases)
    assert "AKT" in found


def test_extract_symbols_ignores_unrelated_text():
    aliases = _load_symbol_aliases()

    found = _extract_symbols("La météo sera ensoleillée demain", aliases)
    assert found == []


def test_sentiment_score_lexicon_direction():
    assert _sentiment_score("résultat en hausse solide") > 0
    assert _sentiment_score("perte et chute importante") < 0
    assert _sentiment_score("annonce une convention") == 0.0


def test_build_sentiment_snapshot_mentions_zero_when_empty():
    snap = build_sentiment_snapshot(
        "AKT",
        7,
        {"articles": [], "warnings": []},
    )
    assert snap["mentions_current"] == 0
    assert snap["sentiment_label"] == "neutral"
    assert "baseline_mentions_zero" in snap["warnings"]

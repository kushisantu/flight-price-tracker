from datetime import date

from app.services.smart import parse_rules, parse_smart


def test_rule_parser_still_reads_a_plain_sentence():
    parsed = parse_smart("One way Chicago to Miami under $250", None, date(2026, 10, 26))
    assert parsed["parser"] == "rules"
    assert parsed["criteria"]["origin"]["code"] == "CHI"
    assert parsed["criteria"]["destination"]["code"] == "MIA"
    assert parsed["criteria"]["trip_type"] == "oneway"
    assert parsed["max_price"] == 250


def test_invalid_model_output_falls_back(monkeypatch):
    monkeypatch.setattr("app.services.llm_parse.interpret", lambda text, today: None)
    parsed = parse_smart("Boston to Seattle", None, date(2026, 10, 26))
    assert parsed["parser"] == "rules"
    assert parsed["criteria"]["destination"]["code"] == "SEA"


def test_valid_model_output_is_used(monkeypatch):
    def fake(text, today):
        return {
            "parser": "llm",
            "interpretation": "from the model",
            "max_price": 400,
            "criteria": {
                "origin": {"code": "BOS", "city": "Boston"},
                "destination": {"code": "SEA", "city": "Seattle"},
                "depart_date": "2026-11-02",
                "return_date": "2026-11-09",
                "trip_type": "round",
                "passengers": 1,
                "cabin": "economy",
            },
        }

    monkeypatch.setattr("app.services.llm_parse.interpret", fake)
    parsed = parse_smart("Boston to Seattle", None, date(2026, 10, 26))
    assert parsed["parser"] == "llm"
    assert parsed["max_price"] == 400


def test_rules_match_the_labeled_eval_fields():
    from app.parser_queries import QUERIES

    assert len(QUERIES) >= 50
    for item in QUERIES:
        parsed = parse_rules(item["query"], item.get("fallback"), date(2026, 10, 26))
        criteria = parsed["criteria"]
        assert criteria["origin"]["code"] == item["origin"]
        assert criteria["destination"]["code"] == item["destination"]
        assert criteria["trip_type"] == item["trip_type"]
        assert criteria["passengers"] == item["passengers"]
        assert criteria["cabin"] == item["cabin"]
        assert parsed["max_price"] == item["max_price"]

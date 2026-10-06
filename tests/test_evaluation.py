import json
import sqlite3

import pytest

from gadgetgenie.core.llm import FakeModel
from gadgetgenie.evaluation import GoldError, GoldItem, evaluate, format_report, load_gold
from gadgetgenie.evaluation.metrics import cumulative_by_attempt, jaccard, scalar_match
from gadgetgenie.evaluation.runner import validate_gold


def test_bundled_gold_set_is_valid(policy):
    items = load_gold()
    assert len(items) >= 25 and any(i.expect_refusal for i in items)
    validate_gold(items, policy)


def test_gold_with_nonexistent_values_is_rejected(policy):
    bad = [GoldItem("x", "q", "SELECT model FROM phones WHERE category = 'mobile'")]
    with pytest.raises(GoldError, match="mobile"):
        validate_gold(bad, policy)


def test_metrics():
    assert scalar_match([(17,)], 17) and scalar_match([("tablets", 17.0)], 17) and not scalar_match([(16,)], 17)
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert cumulative_by_attempt([1, 2, None, 2], 3) == {"1": 0.25, "2": 0.75, "3": 0.75}


def test_offline_evaluation_end_to_end(make_recommender):
    report = evaluate(make_recommender(), load_gold())
    assert report["execution_accuracy"] == 1.0 and report["refusal_accuracy"] == 1.0
    assert report["faithful_summaries"] == 1.0
    assert "execution accuracy" in format_report(report)


def test_accuracy_by_attempt_is_tracked(make_recommender):
    items = [GoldItem("n", "How many tablets are there?", "SELECT COUNT(*) FROM phones WHERE category = 'tablet'",
                      compare="scalar")]
    script = ['{"sql": "SELECT COUNT(*) FROM tablets"}',
              '{"sql": "SELECT COUNT(*) AS n FROM phones WHERE category = \'tablet\'"}', "There are some."]
    report = evaluate(make_recommender(model=FakeModel(script)), items)
    assert report["accuracy_within_attempts"] == {"1": 0.0, "2": 1.0, "3": 1.0}
    assert report["retry_rate"] == 1.0


def test_wrong_sql_scores_zero(make_recommender):
    model = FakeModel(fn=lambda s, u: '{"sql": "SELECT model FROM laptops WHERE price_usd > 99999"}'
                      if s.startswith("TASK: sql") else "Nothing.")
    items = [i for i in load_gold() if not i.expect_refusal and i.compare == "set"][:3]
    report = evaluate(make_recommender(model=model), items)
    assert report["execution_accuracy"] == 0.0


def test_ground_truth_follows_the_data(tmp_path, devices, make_recommender):
    from gadgetgenie.etl.seed import write_sqlite

    db = write_sqlite(devices, tmp_path / "copy.db")
    item = GoldItem("t", "How many tablets are there?", "SELECT COUNT(*) FROM phones WHERE category = 'tablet'",
                    compare="scalar")
    rec = make_recommender(sqlite_path=str(db))
    before = evaluate(rec, [item])["results"][0]["detail"]
    conn = sqlite3.connect(db)
    conn.execute("UPDATE devices SET category = 'phone' WHERE model IN "
                 "(SELECT model FROM devices WHERE category = 'tablet' LIMIT 3)")
    conn.commit()
    conn.close()
    after = evaluate(make_recommender(sqlite_path=str(db)), [item])
    assert after["results"][0]["detail"] != before and after["execution_accuracy"] == 1.0


def test_report_is_json_serializable(make_recommender):
    json.dumps(evaluate(make_recommender(), load_gold()[:3]))

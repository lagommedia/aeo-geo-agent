from app.services.adapters.gsc_adapter import GSCAdapter


def test_gsc_normalization_has_query_and_timeseries():
    adapter = GSCAdapter(csv_path="sample_data/gsc.csv")
    raw = adapter.fetch()
    normalized = adapter.normalize(raw)
    assert normalized
    assert "query_text" in normalized[0]
    assert "timeseries" in normalized[0]

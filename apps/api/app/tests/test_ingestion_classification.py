from app.services.ingestion import _best_gsc_query_match, classify_opportunity_type


def _gsc_row(query: str, impressions: float = 0, clicks: float = 0, position: float = 99):
    return {
        "query_text": query,
        "timeseries": [{"date": "2026-03-01", "impressions": impressions, "clicks": clicks, "position": position}],
        "links": ["https://zeni.ai/blog/finance-automation"],
    }


def test_classify_refresh_when_rank_signal_exists():
    gsc_row = _gsc_row("finance automation for startups", impressions=24, clicks=2, position=17)
    opp_type, reason = classify_opportunity_type(
        query_text="finance automation for startups",
        competitor_gap=0.9,
        gsc_row=gsc_row,
        site_links={"https://zeni.ai/blog/finance-automation"},
    )
    assert opp_type == "refresh"
    assert "rank/impression" in reason.lower()


def test_classify_refresh_when_slug_similarity_is_high_without_rank_signal():
    gsc_row = _gsc_row("bookkeeping tips", impressions=0, clicks=0, position=91)
    opp_type, reason = classify_opportunity_type(
        query_text="bookkeeping services for startups",
        competitor_gap=0.8,
        gsc_row=gsc_row,
        site_links={"https://zeni.ai/blog/bookkeeping-services-for-startups"},
    )
    assert opp_type == "refresh"
    assert "similarity" in reason.lower()


def test_classify_new_when_no_rank_and_high_competitor_gap():
    opp_type, reason = classify_opportunity_type(
        query_text="best ai bookkeeping workflow for seed startups",
        competitor_gap=0.8,
        gsc_row=None,
        site_links={"https://zeni.ai/blog/month-end-close-checklist"},
    )
    assert opp_type == "new"
    assert "competitor" in reason.lower()


def test_best_gsc_query_match_finds_near_duplicate_query():
    records = [
        _gsc_row("bookkeeping services for startups", impressions=20, clicks=2, position=11),
        _gsc_row("monthly close checklist", impressions=5, clicks=0, position=43),
    ]
    row, matched_query, sim = _best_gsc_query_match("startup bookkeeping services", records)
    assert row is not None
    assert matched_query == "bookkeeping services for startups"
    assert sim >= 0.55

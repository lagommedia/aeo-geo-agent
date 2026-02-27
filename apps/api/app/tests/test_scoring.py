from app.services.scoring import score_priority


def test_priority_scoring_bounds_and_explanation():
    score, explanation = score_priority(35, "transactional", "BOFU", True, 1.0, 0.8)
    assert 0 <= score <= 100
    assert "trend=" in explanation
    assert score > 70

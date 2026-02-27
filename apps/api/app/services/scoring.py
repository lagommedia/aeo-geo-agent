INTENT_BONUS = {
    "informational": 5,
    "commercial": 12,
    "navigational": 4,
    "transactional": 15,
}

FUNNEL_WEIGHT = {
    "TOFU": 5,
    "MOFU": 10,
    "BOFU": 15,
}


def score_priority(
    trend_score: float,
    intent: str,
    funnel_stage: str,
    refresh_needed: bool,
    ai_visibility_gap: float,
    competitor_gap: float,
) -> tuple[float, str]:
    trend_component = max(0, min(40, trend_score))
    intent_component = INTENT_BONUS.get(intent.lower(), 5)
    funnel_component = FUNNEL_WEIGHT.get(funnel_stage.upper(), 5)
    refresh_component = 15 if refresh_needed else 0
    ai_component = max(0, min(15, ai_visibility_gap * 15))
    competitor_component = max(0, min(15, competitor_gap * 15))

    total = trend_component + intent_component + funnel_component + refresh_component + ai_component + competitor_component
    total = max(0, min(100, total))

    explanation = (
        f"trend={trend_component:.1f}/40, intent={intent_component}/15, funnel={funnel_component}/15, "
        f"refresh={refresh_component}/15, ai_gap={ai_component:.1f}/15, competitor_gap={competitor_component:.1f}/15"
    )
    return total, explanation

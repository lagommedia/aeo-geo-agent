from __future__ import annotations

from dataclasses import asdict

from content_demand_agent.models import (
    AICitation,
    AgentOutput,
    CompetitorVelocity,
    ContentBrief,
    MentionOpportunity,
    PagePerformance,
    QuerySignal,
    SnippetRecommendation,
)


def _sample_query_signals() -> list[QuerySignal]:
    return [
        QuerySignal("ai overview optimization checklist", False, [120, 170, 290, 520], [0.02, 0.025, 0.031, 0.036], 9.6),
        QuerySignal("geo citation strategy", False, [60, 95, 160, 280], [0.021, 0.026, 0.028, 0.032], 13.1),
        QuerySignal("yourbrand pricing", True, [800, 790, 810, 820], [0.16, 0.16, 0.165, 0.168], 1.8),
        QuerySignal("brand mention not cited", False, [20, 30, 70, 160], [0.015, 0.018, 0.023, 0.029], 17.4),
    ]


def _sample_pages() -> list[PagePerformance]:
    return [
        PagePerformance("/blog/seo-basics", "seo basics", 14200, 430, [5.2, 6.4, 8.8, 11.3], 520),
        PagePerformance("/blog/llm-seo", "llm seo", 8400, 380, [4.3, 4.6, 5.0, 6.2], 300),
        PagePerformance("/blog/structured-snippets", "structured snippets", 5100, 290, [3.2, 3.5, 3.6, 3.8], 30),
    ]


def _sample_citations() -> list[AICitation]:
    return [
        AICitation("ai overview optimization checklist", "yourbrand.com", True),
        AICitation("geo citation strategy", "competitor-a.com", False),
        AICitation("geo citation strategy", "yourbrand.com", True),
        AICitation("brand mention not cited", "competitor-b.com", False),
        AICitation("how to win ai answers", "competitor-a.com", False),
        AICitation("non branded seo pipeline", "yourbrand.com", True),
    ]


def _sample_mentions() -> list[MentionOpportunity]:
    return [
        MentionOpportunity(
            "ai overview optimization checklist",
            "industry-newsletter",
            "Mentions YourBrand framework but links only to competitor-a.com",
            "competitor-a.com",
        ),
        MentionOpportunity(
            "geo citation strategy",
            "roundup-post",
            "Names YourBrand method with no citation",
            None,
        ),
    ]


def _sample_velocity() -> list[CompetitorVelocity]:
    return [
        CompetitorVelocity("yourbrand.com", posts_last_30d=8, updated_last_30d=6),
        CompetitorVelocity("competitor-a.com", posts_last_30d=14, updated_last_30d=9),
        CompetitorVelocity("competitor-b.com", posts_last_30d=11, updated_last_30d=10),
    ]


def _query_growth(q: QuerySignal) -> float:
    if len(q.weekly_impressions) < 2 or q.weekly_impressions[0] <= 0:
        return 0.0
    return (q.weekly_impressions[-1] - q.weekly_impressions[0]) / q.weekly_impressions[0]


def _detect_rising_queries(queries: list[QuerySignal]) -> list[dict]:
    rising = []
    for q in queries:
        growth = _query_growth(q)
        if growth >= 1.5 and q.current_rank > 5:
            rising.append(
                {
                    "query": q.query,
                    "brand": q.brand,
                    "growth_pct": round(growth * 100, 1),
                    "current_rank": q.current_rank,
                    "latest_impressions": q.weekly_impressions[-1],
                }
            )
    return sorted(rising, key=lambda x: x["growth_pct"], reverse=True)


def _detect_decaying_pages(pages: list[PagePerformance]) -> list[dict]:
    decaying = []
    for p in pages:
        if len(p.rank_history) < 2:
            continue
        rank_drop = p.rank_history[-1] - p.rank_history[0]
        if rank_drop >= 2 and p.updated_days_ago >= 120:
            decaying.append(
                {
                    "url": p.url,
                    "primary_query": p.primary_query,
                    "rank_drop": round(rank_drop, 1),
                    "updated_days_ago": p.updated_days_ago,
                }
            )
    return sorted(decaying, key=lambda x: x["rank_drop"], reverse=True)


def _snippet_recommendations(rising_queries: list[dict], decaying_pages: list[dict]) -> list[SnippetRecommendation]:
    recs: list[SnippetRecommendation] = []
    for rq in rising_queries:
        recs.append(
            SnippetRecommendation(
                page_or_query=rq["query"],
                schema_type="FAQPage",
                format_hint="4-6 short Q&A blocks with concise definitions and examples",
                rationale="High growth informational demand with ranking upside in AI answers.",
            )
        )
    for dp in decaying_pages:
        recs.append(
            SnippetRecommendation(
                page_or_query=dp["url"],
                schema_type="HowTo",
                format_hint="Ordered step list with validation checklist and expected outcomes",
                rationale="Refresh decaying pages with structured steps to improve answer extraction.",
            )
        )
    return recs[:6]


def _brief_for_query(query: str) -> ContentBrief:
    q = query.lower()
    if "pricing" in q or "tool" in q:
        stage = "BOFU"
        intent = "commercial"
    elif "strategy" in q or "framework" in q:
        stage = "MOFU"
        intent = "consideration"
    else:
        stage = "TOFU"
        intent = "informational"
    return ContentBrief(
        query=query,
        funnel_stage=stage,
        intent=intent,
        title_suggestions=[
            f"{query.title()}: Practical Playbook",
            f"{query.title()} for 2026",
        ],
        must_cover=[
            "Problem framing and user intent",
            "Actionable workflow with examples",
            "Citations and source quality checks",
            "FAQ block for AI extraction",
        ],
        ai_snippet_format="Definition -> Steps -> Evidence -> FAQ",
    )


def _citation_share(citations: list[AICitation]) -> float:
    if not citations:
        return 0.0
    cited = sum(1 for c in citations if c.cited)
    return round((cited / len(citations)) * 100, 1)


def _non_branded_pipeline(queries: list[QuerySignal]) -> int:
    return sum(q.weekly_impressions[-1] for q in queries if not q.brand)


def _velocity_gap(velocities: list[CompetitorVelocity]) -> dict:
    ours = next((v for v in velocities if v.domain == "yourbrand.com"), None)
    competitors = [v for v in velocities if v.domain != "yourbrand.com"]
    if not ours or not competitors:
        return {}
    avg_posts = sum(v.posts_last_30d for v in competitors) / len(competitors)
    avg_updates = sum(v.updated_last_30d for v in competitors) / len(competitors)
    return {
        "our_posts_30d": ours.posts_last_30d,
        "competitor_avg_posts_30d": round(avg_posts, 1),
        "post_gap": round(ours.posts_last_30d - avg_posts, 1),
        "our_updates_30d": ours.updated_last_30d,
        "competitor_avg_updates_30d": round(avg_updates, 1),
        "update_gap": round(ours.updated_last_30d - avg_updates, 1),
    }


def run_agent_snapshot() -> dict:
    queries = _sample_query_signals()
    pages = _sample_pages()
    citations = _sample_citations()
    mentions = _sample_mentions()
    velocity = _sample_velocity()

    rising = _detect_rising_queries(queries)
    decaying = _detect_decaying_pages(pages)
    output = AgentOutput(
        rising_queries=rising,
        decaying_pages=decaying,
        snippet_recommendations=_snippet_recommendations(rising, decaying),
        content_briefs=[_brief_for_query(r["query"]) for r in rising[:4]],
        uncited_brand_mentions=mentions,
        ai_citation_share=_citation_share(citations),
        non_branded_pipeline=_non_branded_pipeline(queries),
        velocity_gap=_velocity_gap(velocity),
    )
    return asdict(output)

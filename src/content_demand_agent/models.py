from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FunnelStage = Literal["TOFU", "MOFU", "BOFU"]


@dataclass
class QuerySignal:
    query: str
    brand: bool
    weekly_impressions: list[int]
    weekly_ctr: list[float]
    current_rank: float


@dataclass
class PagePerformance:
    url: str
    primary_query: str
    impressions: int
    clicks: int
    rank_history: list[float]
    updated_days_ago: int


@dataclass
class AICitation:
    query: str
    source_domain: str
    cited: bool


@dataclass
class MentionOpportunity:
    query: str
    source: str
    mention_context: str
    cited_domain: str | None


@dataclass
class CompetitorVelocity:
    domain: str
    posts_last_30d: int
    updated_last_30d: int


@dataclass
class ContentBrief:
    query: str
    funnel_stage: FunnelStage
    intent: str
    title_suggestions: list[str]
    must_cover: list[str]
    ai_snippet_format: str


@dataclass
class SnippetRecommendation:
    page_or_query: str
    schema_type: str
    format_hint: str
    rationale: str


@dataclass
class AgentOutput:
    rising_queries: list[dict] = field(default_factory=list)
    decaying_pages: list[dict] = field(default_factory=list)
    snippet_recommendations: list[SnippetRecommendation] = field(default_factory=list)
    content_briefs: list[ContentBrief] = field(default_factory=list)
    uncited_brand_mentions: list[MentionOpportunity] = field(default_factory=list)
    ai_citation_share: float = 0.0
    non_branded_pipeline: int = 0
    velocity_gap: dict = field(default_factory=dict)

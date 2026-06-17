from __future__ import annotations

import json
from textwrap import dedent

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.secrets import decrypt_secret
from app.models.source_config import SourceConfig

AGENT_PROMPTS: dict[str, str] = {
    "strategist": dedent(
        """
        You are an AEO/GEO Strategist GPT for Zeni.

        Core mission:
        - Decide whether an opportunity is net-new content or refresh.
        - Prevent SEO cannibalization.
        - Prioritize by business value, AI-answer visibility, and execution feasibility.

        Decision rules:
        - If the site already ranks or has meaningful impressions/clicks for the topic, prefer refresh.
        - If a closely related URL already exists, prefer refresh unless intent is materially different.
        - If the site lacks rank signal and competitor gap is high, classify as new.
        - Surface confidence and what evidence drove the decision.

        Cannibalization guardrails:
        - Explicitly compare proposed target intent vs existing page intent.
        - Flag overlap risk when two pages would satisfy the same user job-to-be-done.
        - If overlap risk exists, recommend consolidation or repositioning instead of net-new.

        Scoring lens:
        - AI query volume potential
        - Answer likelihood in AI systems
        - Commercial intent
        - AI citation gap
        - Authority leverage
        - Content coverage gap
        - Trend velocity
        - SERP and AI fragmentation

        Rules:
        - Be concrete and operational.
        - Never output generic advice without a decision path.
        - Always include assumptions and confidence.
        - If data is missing, list exact missing signals and next collection step.
        - Avoid em dashes.

        Output format:
        1) Classification Decision (new vs refresh)
        2) Confidence + Evidence
        3) Why This Decision
        4) Recommended Actions (ordered)
        5) KPI and Success Criteria
        6) Cannibalization Risks and Mitigations
        """
    ).strip(),
    "content_creator": dedent(
        """
        You are an AEO/GEO Content Creator GPT for Zeni.

        Mission:
        - Produce world-class, publication-ready articles for the exact keyword/prompt provided.
        - Maximize answer-engine usefulness and organic performance while maintaining strong EEAT.
        - Deliver operator-level clarity for startup founders and finance leaders.

        Topic discipline (non-negotiable):
        - The keyword/prompt is the article topic. Do not switch topics.
        - Do not include generic AEO/GEO/SEO explanations unless the keyword explicitly asks for them.
        - Keep every section explicitly tied to the target keyword implementation and decision-making.

        EEAT standards:
        - Demonstrate practical expertise with concrete implementation details.
        - Include realistic examples, decision criteria, tradeoffs, and common failure modes.
        - Include measurable checkpoints: thresholds, ranges, or KPIs where relevant.
        - Prefer specific, falsifiable claims over broad generalizations.
        - Keep the writing original, non-generic, and commercially useful.

        Writing style:
        - Authoritative but approachable.
        - CFO-level financial rigor with founder-friendly clarity.
        - Concise, structured paragraphs with selective bullets/tables where useful.
        - Avoid fluff, cliches, and em dashes.

        Output format contract:
        1) # Main article title
        2) ---
        3) ## Optimized Title Tag
        4) ## Meta Description
        5) ## URL Slug
        6) ## H1
        7) ## OG Title
        8) ## OG Description
        9) ---
        10) ## Heading Placement Map (list H1, all H2, and each H3 under parent H2)
        11) # Main article title (article body starts)
        12) Article body with explicit H2/H3 headings
        13) FAQ section
        14) ## Recommended JSON-LD Schema Markup (json code block)
        15) ## Internal Linking Recommendations
        16) ## Final Takeaway

        Structural minimums:
        - Exactly one H1 in the body.
        - At least 5 H2 sections and at least 6 H3 subsections.
        - Generally target depth appropriate for world-class treatment (often 1400+ words), unless the keyword requires brevity.
        """
    ).strip(),
    "refresh": dedent(
        """
        You are an AEO/GEO Refresh GPT for Zeni.

        Goals:
        - Improve existing pages for declining or underperforming AI/SEO visibility.
        - Prevent cannibalization by strengthening page intent and differentiation.

        Rules:
        - Provide delta recommendations against current page intent.
        - Identify what to keep, remove, and add.
        - Prioritize high-impact low-effort updates first.
        - Avoid em dashes.

        Output format:
        1) Refresh Diagnosis
        2) Proposed Changes (Keep / Remove / Add)
        3) Prompt + SERP Alignment Fixes
        4) Measurement Plan (before/after)
        5) Rollout Sequence
        """
    ).strip(),
    "community": dedent(
        """
        You are an AEO/GEO Community Agent GPT for Zeni.

        Goals:
        - Identify high-value community conversations where Zeni should contribute.
        - Craft responses that are helpful, credible, and non-spammy.

        Rules:
        - Optimize for trust and usefulness, not promotional tone.
        - Suggest response angle + short draft + link strategy.
        - Flag when not to engage.
        - Avoid em dashes.

        Output format:
        1) Engagement Decision
        2) Recommended Response Angle
        3) Draft Response
        4) Optional Link Placement
        5) Moderation / Brand Risk Notes
        """
    ).strip(),
}


def _extract_response_text(payload: dict) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    chunks: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "\n\n".join(chunks).strip()


def _openai_config(db: Session) -> dict:
    row = db.query(SourceConfig).filter(SourceConfig.source_name == "openai").one_or_none()
    config = (row.config or {}) if row else {}
    return config if isinstance(config, dict) else {}


def resolve_openai_credentials(db: Session) -> tuple[str | None, str]:
    config = _openai_config(db)
    api_key = config.get("api_key")
    model = config.get("model") or settings.openai_model

    resolved_key = decrypt_secret(api_key) if api_key else settings.openai_api_key
    resolved_model = str(model or settings.openai_model)
    return resolved_key, resolved_model


def resolve_agent_instructions(db: Session, agent_name: str) -> str:
    key_name = agent_name.strip().lower()
    default_prompt = AGENT_PROMPTS.get(key_name)
    if not default_prompt:
        raise RuntimeError(f"Unsupported agent: {agent_name}")

    config = _openai_config(db)
    custom = config.get("agent_prompts")
    if not isinstance(custom, dict):
        return default_prompt

    override = custom.get(key_name)
    if isinstance(override, str) and override.strip():
        return override.strip()
    return default_prompt


def _provider_config(db: Session, source_name: str) -> dict:
    row = db.query(SourceConfig).filter(SourceConfig.source_name == source_name).one_or_none()
    config = (row.config or {}) if row else {}
    return config if isinstance(config, dict) else {}


def resolve_anthropic_credentials(db: Session) -> tuple[str | None, str]:
    config = _provider_config(db, "anthropic")
    api_key = config.get("api_key")
    model = config.get("model") or "claude-3-5-sonnet-latest"
    resolved_key = decrypt_secret(api_key) if api_key else None
    return resolved_key, str(model)


def resolve_anthropic_instructions(db: Session, opportunity_type: str) -> str:
    config = _provider_config(db, "anthropic")
    instructions = config.get("instructions")

    fallback = AGENT_PROMPTS["content_creator"]
    if isinstance(instructions, str):
        return instructions.strip() or fallback
    if not isinstance(instructions, dict):
        return fallback

    key = (opportunity_type or "").strip().lower()
    aliases = {
        "new": ["new", "new_opportunity", "new_content"],
        "refresh": ["refresh", "revamp", "revamp_opportunity", "refresh_content"],
        "community": ["community", "community_content"],
    }.get(key, [key])

    for candidate in aliases:
        value = instructions.get(candidate)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for candidate in ["content", "content_creator"]:
        value = instructions.get(candidate)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return fallback


def run_agent(
    db: Session,
    agent_name: str,
    prompt: str,
    context: dict | None = None,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    key, resolved_model = resolve_openai_credentials(db)
    key = api_key or key
    resolved_model = model or resolved_model

    if not key:
        raise RuntimeError("OpenAI API key not configured. Save it in Integrations > OpenAI Brain.")

    key_name = agent_name.strip().lower()
    instructions = resolve_agent_instructions(db, key_name)

    context_blob = ""
    if context:
        context_blob = f"\n\nContext JSON:\n{json.dumps(context, indent=2, ensure_ascii=True)}"

    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": resolved_model,
            "instructions": instructions,
            "input": f"{prompt.strip()}{context_blob}",
        },
        timeout=90.0,
    )

    if response.status_code >= 300:
        raise RuntimeError(f"OpenAI agent call failed ({response.status_code})")

    payload = response.json()
    text = _extract_response_text(payload)
    if not text:
        raise RuntimeError("OpenAI agent returned empty output")

    return {
        "agent": key_name,
        "output": text,
        "provider": "openai",
        "model": resolved_model,
    }

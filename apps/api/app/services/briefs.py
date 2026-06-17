from sqlalchemy.orm import Session

from app.services.aeo_geo_agents import run_agent

from textwrap import dedent


def infer_funnel(query_text: str, intent: str) -> str:
    q = query_text.lower()
    if any(x in q for x in ["price", "demo", "buy", "software"]):
        return "BOFU"
    if intent in {"commercial", "transactional"}:
        return "MOFU"
    return "TOFU"


def recommend_snippets(intent: str, query_text: str) -> dict:
    intent_l = intent.lower()
    schema = ["Article", "Organization"]
    blocks = ["Definition block", "AI answer block", "FAQ"]

    if intent_l == "informational":
        schema += ["FAQPage"]
    if "how" in query_text.lower():
        schema += ["HowTo"]
        blocks += ["Step-by-step"]
    if intent_l in {"commercial", "transactional"}:
        schema += ["Product"]
        blocks += ["Pros/Cons", "Comparison table"]

    return {
        "schema": sorted(set(schema)),
        "snippet_blocks": sorted(set(blocks)),
        "speakable": True,
    }


def generate_brief(
    query_text: str,
    intent: str,
    funnel_stage: str,
    secondary_queries: list[str],
    links: list[str],
) -> str:
    internal_links = "\n".join([f"- {link}" for link in links[:5]]) or "- /resources/roi-calculator\n- /demo"
    secondary = ", ".join(secondary_queries[:6]) if secondary_queries else "TBD"
    return dedent(
        f"""
        # Content Brief: {query_text}

        ## Business Context
        - Company: Zeni
        - ICP: founders/CEOs + finance leaders at startups (Seed-Series C)
        - Primary conversion: Demo request
        - Secondary conversions: Newsletter, webinar, ROI calculator

        ## Target Persona
        - Finance leader evaluating automation and decision support

        ## Query Strategy
        - Primary query: {query_text}
        - Intent: {intent}
        - Funnel stage: {funnel_stage}
        - Secondary queries: {secondary}

        ## Outline (H2/H3)
        - H2: What {query_text} means for startup finance teams
        - H2: Common implementation paths
        - H3: Process checklist
        - H2: Pitfalls and ROI modeling
        - H2: Why teams choose Zeni

        ## Internal Links
        {internal_links}

        ## FAQ
        - What are the implementation prerequisites?
        - How long until measurable impact?
        - Which KPIs should be tracked post-launch?

        ## Suggested Schema
        - FAQPage
        - Article
        - Organization

        ## AI Answer Block
        "{query_text} can be addressed by combining clear process ownership, timely financial data, and measurable ROI milestones."

        ## Success Metrics
        - CTR uplift on target query cluster
        - Non-branded click growth
        - Demo request conversion rate from this page
        """
    ).strip()


def generate_strategist_brief(db: Session, opportunity) -> str:
    metadata = opportunity.metadata_json or {}
    prompt = (
        "Create a world-class, execution-ready content brief for the provided opportunity. "
        "Return markdown only. Make it specific, tactical, and decision-useful. "
        "Focus on keyword/topic implementation, cannibalization avoidance, and measurable outcomes."
    )
    context = {
        "query_text": opportunity.query_text,
        "source": opportunity.source,
        "intent": opportunity.intent,
        "funnel_stage": opportunity.funnel_stage,
        "priority_score": opportunity.priority_score,
        "priority_explanation": opportunity.priority_explanation,
        "score_components": (metadata.get("score_components") if isinstance(metadata, dict) else None),
        "classification_reason": (metadata.get("classification_reason") if isinstance(metadata, dict) else None),
        "existing_brief": opportunity.brief,
        "links": opportunity.links or [],
    }

    try:
        result = run_agent(db, "strategist", prompt, context=context)
        output = (result.get("output") or "").strip()
        if output:
            return output
    except Exception:
        pass

    # Fallback to baseline brief generator
    return generate_brief(
        opportunity.query_text,
        opportunity.intent or "informational",
        opportunity.funnel_stage or "TOFU",
        [],
        opportunity.links or [],
    )

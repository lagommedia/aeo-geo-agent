from __future__ import annotations

from textwrap import dedent
import re
import time

import httpx

from app.core.config import settings
from app.models.opportunity import QueryOpportunity

MISSING_KEYWORD_MESSAGE = "Please provide the primary keyword or long-tail query you would like this article optimized for."

SYSTEM_INSTRUCTIONS = dedent(
    """
    You are AEO GEO Content Creator, a specialized AEO and GEO content strategist for Zeni.

    Hard rules:
    - Do not generate any article unless a specific keyword or topic is provided.
    - If keyword is missing, return exactly: "Please provide the primary keyword or long-tail query you would like this article optimized for."
    - Do not provide AI detection evasion or manipulation guidance.
    - Avoid em dashes.
    - Keep the article tightly scoped to the provided primary keyword/topic.
    - Do not add generic preambles about AI search/AEO/GEO trends unless the keyword explicitly asks for that topic.
    - Start the article body by defining or addressing the primary keyword directly for the target audience.
    - Do not write about AEO, GEO, SEO strategy, SERP strategy, answer engines, or content strategy frameworks unless the primary keyword explicitly asks for those topics.

    Output format contract (required):
    - Return pure markdown only.
    - Do NOT wrap the full response in a markdown code fence.
    - Do NOT indent normal paragraphs with leading spaces.
    - Use this section order:
      1) # Main article title
      2) ---
      3) ## Optimized Title Tag
      4) ## Meta Description
      5) ## URL Slug
      6) ## H1
      7) ## OG Title
      8) ## OG Description
      9) ---
      10) ## Heading Placement Map (explicitly list H1, all H2s, and each H3 under its parent)
      11) # Main article title (article body starts)
      12) Article sections with H2/H3
      13) FAQ section
      14) ## Recommended JSON-LD Schema Markup (with json code block)
      15) ## Internal Linking Recommendations
      16) ## Final Takeaway

    Editorial and quality requirements:
    - The body must include explicit heading markers in markdown, not implied sections.
    - Include exactly one H1 in body, at least 5 H2 sections, and at least 6 H3 subsections.
    - Ensure H2/H3 are meaningful labels, not placeholders.
    - Publication-ready, practical, operationally specific, and original.
    - Balance CFO-level sophistication with founder-friendly clarity.
    - Include realistic tradeoffs, caveats, and edge cases where useful.
    - Use concise paragraphs plus selective lists/tables when helpful.
    - Apply Article schema by default and add other schema only when justified.
    - The opening 2 paragraphs must be directly about the primary keyword and practical execution.
    - Target world-class depth: generally 1400+ words unless the keyword naturally requires shorter treatment.
    - Each major section should include implementation detail, common failure modes, and concrete examples.
    - Include practical metrics, thresholds, ranges, or checkpoints where relevant to establish EEAT depth.
    - Avoid vague statements; prefer operator-level specificity.
    """
).strip()


def _fallback_article(keyword: str, opportunity: QueryOpportunity) -> str:
    slug = keyword.lower().strip().replace("/", "-").replace(" ", "-")
    slug = "-".join([p for p in slug.split("-") if p])
    if not slug:
        slug = "zeni-finance-guide"

    title = _dedupe_repeated_phrases(f"How to Improve {keyword.title()} for Startups")

    return dedent(
        f"""
        # {title}

        ---

        ## Optimized Title Tag

        {title} | Complete Guide

        ## Meta Description

        Learn how startup finance leaders can improve {keyword} using practical implementation steps, structure guidance, and measurable ROI criteria.

        ## URL Slug

        {slug}

        ## H1

        {title}

        ## OG Title

        {title} in 2026

        ## OG Description

        A practical framework for structuring, implementing, and scaling {keyword} for startup finance teams.

        ---

        # {title}

        {keyword.title()} is most effective when treated as an operating system, not a one-time project. For startup finance teams, the goal is faster close cycles, fewer manual errors, clearer reporting, and stronger cash-control decisions.

        The most reliable implementation pattern is to map workflows end to end, assign owners, define thresholds for exceptions, and measure business outcomes tied to speed, accuracy, and decision quality.

        ## What {keyword.title()} Means for Startup Finance Teams

        {keyword.title()} works best when finance, accounting, and operations align on responsibilities, data quality expectations, and escalation paths.

        ### Practical Priorities

        - Establish role ownership between finance, operations, and leadership.
        - Define measurable outcomes before implementation.
        - Document control and review checkpoints for reliability.
        - Tie content and reporting workflows to conversion goals.

        ## Implementation Framework for {keyword.title()}

        ### Step 1: Define the current-state workflow for {keyword.title()}

        Document the existing process, owners, source systems, handoffs, and control checkpoints. Capture where delays, rework, and manual overrides occur today.

        ### Step 2: Standardize operating rules and exception thresholds

        Define explicit rules for approvals, data validation, reconciliations, and exception routing. Make these rules auditable and easy for operators to follow.

        ### Step 3: Instrument metrics and accountability

        Track cycle time, error rates, exception volume, on-time completion, and downstream decision quality. Assign accountable owners for each metric.

        ### Step 4: Roll out in phases and optimize

        Deploy by workflow segment, run short feedback loops, and improve based on measured outcomes. Prioritize high-impact bottlenecks first.

        ## FAQ

        ### What should teams measure first?

        Start with reliability and cycle-time metrics, then add conversion and pipeline metrics.

        ### How often should content be refreshed?

        Most teams should review high-intent pages every 30 to 90 days depending on volatility and update frequency.

        ### What is the most common implementation mistake?

        Teams often automate steps without first defining operating rules and exception handling. Start with process standards, then automate against those standards.

        ## Recommended JSON-LD Schema Markup

        ```json
        {{
          "@context": "https://schema.org",
          "@type": "Article",
          "headline": "{title}",
          "description": "A practical framework for startup teams to improve {keyword}.",
          "author": {{
            "@type": "Organization",
            "name": "Zeni"
          }},
          "mainEntityOfPage": {{
            "@type": "WebPage",
            "@id": "https://zeni.ai/resources/{slug}"
          }}
        }}
        ```

        ## Internal Linking Recommendations

        - /demo
        - /resources/roi-calculator
        - /resources/startup-finance-automation-guide
        - /resources/how-to-improve-month-end-close

        ## Final Takeaway

        {keyword.title()} creates outsized value when it is operationalized with clear ownership, measurable controls, and iterative optimization. Teams that execute this consistently improve both finance reliability and decision speed.
        """
    ).strip()




def _compose_instructions(agent_instructions: str | None) -> str:
    extra = (agent_instructions or "").strip()
    if not extra:
        return SYSTEM_INSTRUCTIONS

    return dedent(
        f"""
        You are generating article content for Zeni.

        Non-negotiable constraints:
        - The article topic must come only from the provided primary keyword/prompt.
        - Do not change the topic based on meta-instructions.
        - Use the Content Creator Brain instructions below as the complete writing-method specification.

        <CONTENT_CREATOR_BRAIN_INSTRUCTIONS>
        {extra}
        </CONTENT_CREATOR_BRAIN_INSTRUCTIONS>
        """
    ).strip()
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


def _anthropic_extract_text(payload: dict) -> str:
    chunks: list[str] = []
    for item in payload.get("content", []):
        if item.get("type") == "text" and item.get("text"):
            chunks.append(str(item["text"]))
    return "\n\n".join(chunks).strip()


def _provider_generate(
    *,
    provider: str,
    api_key: str,
    model: str,
    instructions: str,
    prompt: str,
) -> tuple[str | None, str | None]:
    if provider == "anthropic":
        try:
            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 6400,
                    "system": instructions,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                },
                timeout=120.0,
            )
        except httpx.HTTPError as exc:
            return None, f"anthropic-http-error: {exc}"

        if response.status_code >= 300:
            return None, f"anthropic-status-{response.status_code}"

        payload = response.json()
        return _anthropic_extract_text(payload), None

    try:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "instructions": instructions,
                "input": prompt,
            },
            timeout=90.0,
        )
    except httpx.HTTPError as exc:
        return None, f"openai-http-error: {exc}"

    if response.status_code >= 300:
        return None, f"openai-status-{response.status_code}"

    payload = response.json()
    return _extract_response_text(payload), None




def _strip_brief_notes(content: str) -> str:
    lines = content.split("\n")
    filtered = [ln for ln in lines if not ln.strip().lower().startswith("_assumptions used:")]
    return "\n".join(filtered).strip()

def _dedupe_repeated_phrases(content: str) -> str:
    in_fence = False
    out_lines = []
    for line in content.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        cleaned = line
        prev = None
        while prev != cleaned:
            prev = cleaned
            cleaned = re.sub(r"(?i)\b(for startups)\s+\1\b", r"\1", cleaned)
        out_lines.append(cleaned)
    return "\n".join(out_lines).strip()


def _compact_brief(brief: str, max_chars: int = 5000) -> str:
    text = (brief or "").strip()
    if not text:
        return ""
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars]
    last_break = trimmed.rfind("\n## ")
    if last_break > 1200:
        trimmed = trimmed[:last_break]
    return trimmed.strip()

def _word_count(content: str) -> int:
    return len(re.findall(r"\b\w+\b", content or ""))


def _quality_gate_issues(content: str, keyword: str) -> list[str]:
    issues: list[str] = []
    lowered = (content or "").lower()

    wc = _word_count(content)
    if wc < 1200:
        issues.append(f"Expand depth to at least 1200 words (current: {wc}).")

    h2_count = len(re.findall(r"^##\s+", content or "", flags=re.MULTILINE))
    h3_count = len(re.findall(r"^###\s+", content or "", flags=re.MULTILINE))
    if h2_count < 5:
        issues.append(f"Add more H2 sections (current: {h2_count}, target: 5+).")
    if h3_count < 6:
        issues.append(f"Add more H3 subsections (current: {h3_count}, target: 6+).")

    numeric_count = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", content or ""))
    if numeric_count < 8:
        issues.append(f"Add concrete numbers, thresholds, or ranges (current numeric markers: {numeric_count}, target: 8+).")

    if keyword.lower() not in lowered:
        issues.append("Use the exact primary keyword explicitly throughout the article body.")

    drift_markers = [
        "map intent and decision points",
        "structure for extraction and readability",
        "answer engines",
        "ai-native search",
    ]
    if any(m in lowered for m in drift_markers) and not any(x in keyword.lower() for x in ["aeo", "geo", "seo", "serp"]):
        issues.append("Remove generic AEO/GEO strategy framing and keep focus on the target keyword implementation.")

    return issues


def _rewrite_for_depth(
    *,
    content: str,
    keyword: str,
    prompt: str,
    api_key: str,
    model: str,
    instructions: str,
    issues: list[str],
    provider: str = "openai",
) -> str | None:
    issues_block = "\n        - ".join(issues)
    rewrite_prompt = dedent(
        f"""
        Improve this draft to world-class EEAT depth while preserving the required output format and markdown section order.

        Primary keyword/topic:
        {keyword}

        Required fixes:
        - {issues_block}

        Rules:
        - Treat Content Creator instructions as writing guidance only, not topic guidance.
        - Keep the article exclusively on the primary keyword topic.
        - Add concrete examples, implementation detail, decision criteria, and measurable checkpoints.
        - Keep it publication-ready and practical for startup finance operators.

        Original generation context:
        {prompt}

        Draft to improve:
        {content}
        """
    ).strip()

    rewritten_text, error = _provider_generate(
        provider=provider,
        api_key=api_key,
        model=model,
        instructions=instructions,
        prompt=rewrite_prompt,
    )
    if error or not rewritten_text:
        return None

    rewritten = _dedupe_repeated_phrases(_strip_brief_notes(rewritten_text))
    return rewritten or None


def generate_article_from_brief(
    keyword: str,
    brief: str,
    opportunity: QueryOpportunity,
    *,
    provider: str = "openai",
    api_key: str | None = None,
    model: str | None = None,
    agent_instructions: str | None = None,
) -> dict:
    if not keyword or not keyword.strip():
        return {
            "content_markdown": MISSING_KEYWORD_MESSAGE,
            "provider": "validation",
            "model": None,
        }

    keyword = keyword.strip()
    resolved_provider = (provider or "openai").strip().lower()
    api_key = api_key or settings.openai_api_key
    model = model or (settings.openai_model if resolved_provider == "openai" else "claude-3-5-sonnet-latest")

    if not api_key:
        return {
            "content_markdown": _dedupe_repeated_phrases(_strip_brief_notes(_fallback_article(keyword, opportunity))),
            "provider": "fallback-template",
            "model": None,
        }

    prompt = dedent(
        f"""
        Primary keyword: {keyword}

        Company context:
        - Brand: Zeni
        - ICP: founders/CEOs + finance leaders at startups (Seed-Series C)
        - Primary conversion: demo request
        - Secondary conversions: newsletter, webinar, ROI calculator

        Opportunity context:
        - Intent: {opportunity.intent}
        - Funnel stage: {opportunity.funnel_stage}
        - Trend score: {opportunity.trend_score:.1f}
        - Priority score: {opportunity.priority_score:.1f}

        Source brief context (use for substance, do not copy raw formatting):
        {_compact_brief(brief)}

        Generate the final publication-ready article by following the loaded Content Creator Brain instructions exactly for writing method, depth, and structure.

        Critical topicality constraints:
        - The article must be specifically about: {keyword}
        - The Content Creator GPT instructions are writing guidance only, not topic guidance.
        - Do not include generic AEO/GEO/SEO content-strategy explanations unless the keyword explicitly requests that subject.
        - Keep every major section anchored to the practical implementation of {keyword} for startup finance teams.
        """
    ).strip()

    instructions = _compose_instructions(agent_instructions)
    last_error = None
    content = None

    for attempt in range(2):
        generated_text, error = _provider_generate(
            provider=resolved_provider,
            api_key=api_key,
            model=model,
            instructions=instructions,
            prompt=prompt,
        )
        if generated_text:
            content = _dedupe_repeated_phrases(_strip_brief_notes(generated_text))
            break
        last_error = error
        if resolved_provider == "openai" and error and "429" in error and attempt == 0:
            time.sleep(1.0)
            continue
        break

    if not content:
        return {
            "content_markdown": _dedupe_repeated_phrases(_strip_brief_notes(_fallback_article(keyword, opportunity))),
            "provider": "fallback-template",
            "model": None,
            "fallback_reason": last_error or f"{resolved_provider}-empty-content",
        }

    issues = _quality_gate_issues(content, keyword)
    if issues and resolved_provider != "anthropic":
        rewritten = _rewrite_for_depth(
            content=content,
            keyword=keyword,
            prompt=prompt,
            api_key=api_key,
            model=model,
            instructions=instructions,
            issues=issues,
            provider=resolved_provider,
        )
        if rewritten:
            content = rewritten

    post_issues = _quality_gate_issues(content, keyword)
    if post_issues and resolved_provider != "anthropic":
        content = _dedupe_repeated_phrases(_strip_brief_notes(_fallback_article(keyword, opportunity)))
        return {
            "content_markdown": content,
            "provider": "fallback-template",
            "model": None,
            "fallback_reason": "quality-gate-fallback",
        }

    return {
        "content_markdown": content,
        "provider": resolved_provider,
        "model": model,
    }

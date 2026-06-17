"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useToken } from "../components/token-context";

type BoardKey = "new" | "refresh" | "community";
type ColumnKey = "incoming" | "accepted" | "in_progress" | "done";

type Opportunity = {
  id: number;
  query_text: string;
  source: string;
  intent?: string | null;
  funnel_stage?: string | null;
  trend_score?: number | null;
  priority_score?: number | null;
  status: string;
  links?: string[] | null;
  priority_explanation?: string | null;
  metadata_json?: {
    opportunity_type?: string | null;
    [key: string]: unknown;
  } | null;
};

type LegacyPriorityComponent = {
  value: number;
  max: number;
};

type ScoreMetric = {
  label: string;
  value: number;
  weight: number;
  rating: number;
  why: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function normalizeStatus(status?: string | null): string {
  return (status || "new").trim().toLowerCase();
}

function boardForOpportunity(opportunity: Opportunity): BoardKey {
  const normalizedSource = (opportunity.source || "").trim().toLowerCase();
  if (normalizedSource === "refresh_scan") return "refresh";
  if (normalizedSource === "community") return "community";

  const typed = String(opportunity.metadata_json?.opportunity_type || "").trim().toLowerCase();
  if (typed === "refresh") return "refresh";
  if (typed === "community") return "community";
  return "new";
}

function statusForColumn(column: ColumnKey): string {
  if (column === "incoming") return "incoming";
  if (column === "accepted") return "accepted";
  if (column === "in_progress") return "in_progress";
  return "done";
}

function matchesColumnStatus(status: string, column: ColumnKey): boolean {
  if (column === "incoming") return ["incoming", "new", "intake", "queued", "untriaged", "backlog"].includes(status);
  if (column === "accepted") return ["accepted", "triaged", "new_opportunity"].includes(status);
  if (column === "in_progress") return status === "in_progress";
  return status === "done";
}

function scoreBand(score: number): { label: string; tone: string } {
  if (score >= 80) return { label: "P1 Top Priority", tone: "text-emerald-300" };
  if (score >= 65) return { label: "P2 Strong Priority", tone: "text-lime-300" };
  if (score >= 50) return { label: "P3 Medium Priority", tone: "text-amber-300" };
  if (score >= 35) return { label: "P4 Lower Priority", tone: "text-orange-300" };
  return { label: "P5 Watchlist", tone: "text-rose-300" };
}

function priorityCode(score: number): "P1" | "P2" | "P3" | "P4" | "P5" {
  if (score >= 80) return "P1";
  if (score >= 65) return "P2";
  if (score >= 50) return "P3";
  if (score >= 35) return "P4";
  return "P5";
}

function sourceMeta(source?: string | null): { label: string; logo: string; logoPath?: string; logoTint?: string } {
  const key = (source || "").trim().toLowerCase();
  if (key === "gsc") return { label: "GSC", logo: "G", logoPath: "/logos/google.svg" };
  if (key === "semrush") return { label: "SEMrush", logo: "S", logoPath: "/logos/semrush.svg", logoTint: "#FF642D" };
  if (key === "ahrefs") return { label: "Ahrefs", logo: "A" };
  if (key === "community") return { label: "Community", logo: "C" };
  if (key === "strategist_new") return { label: "Strategist", logo: "ST" };
  if (key === "manual") return { label: "Manual", logo: "M" };
  return { label: source || "Unknown", logo: "•" };
}

function parseLegacyPriorityExplanation(explanation?: string | null): Record<string, LegacyPriorityComponent> {
  if (!explanation) return {};
  const components: Record<string, LegacyPriorityComponent> = {};
  for (const part of explanation.split(",")) {
    const [rawKey, rawValue] = part.trim().split("=");
    if (!rawKey || !rawValue) continue;
    const [valueText, maxText] = rawValue.split("/");
    const value = Number.parseFloat(valueText);
    const max = Number.parseFloat(maxText);
    if (!Number.isFinite(value) || !Number.isFinite(max) || max <= 0) continue;
    components[rawKey.trim()] = { value, max };
  }
  return components;
}

function buildAeoGeoBreakdown(opportunity?: Opportunity | null): ScoreMetric[] {
  if (!opportunity) return [];

  const criteria = [
    { key: "ai_query_volume", label: "AI Query Volume", weight: 20, why: "How often this topic is likely asked in AI systems." },
    { key: "answer_likelihood", label: "Answer Likelihood", weight: 15, why: "Chance AI returns a synthesized answer instead of links." },
    { key: "commercial_intent", label: "Commercial / Solution Intent", weight: 20, why: "How close this query is to solution evaluation and purchase." },
    { key: "ai_citation_gap", label: "AI Citation Gap", weight: 15, why: "How often competitors are cited while your brand is not." },
    { key: "authority_leverage", label: "Authority Leverage", weight: 15, why: "How much existing authority can support ranking/citation." },
    { key: "content_coverage_gap", label: "Content Coverage Gap", weight: 15, why: "How much useful structured content is missing today." },
  ] as const;

  const metadata = opportunity.metadata_json && typeof opportunity.metadata_json === "object" ? opportunity.metadata_json : null;
  const scoreComponents = metadata?.score_components && typeof metadata.score_components === "object"
    ? (metadata.score_components as Record<string, unknown>)
    : null;
  const scoreRatings = metadata?.score_ratings && typeof metadata.score_ratings === "object"
    ? (metadata.score_ratings as Record<string, unknown>)
    : null;

  if (scoreComponents && criteria.some((c) => Number.isFinite(Number(scoreComponents[c.key] ?? NaN)))) {
    return criteria.map((row) => {
      const raw = Number(scoreComponents[row.key] ?? 0);
      return {
        label: row.label,
        weight: row.weight,
        value: clamp(Number.isFinite(raw) ? raw : 0, 0, row.weight),
        rating: clamp(Number(scoreRatings?.[row.key] ?? (raw / row.weight) * 10), 0, 10),
        why: row.why,
      };
    });
  }

  const legacy = parseLegacyPriorityExplanation(opportunity.priority_explanation);
  return criteria.map((row) => {
    const comp = legacy[row.key];
    const val = comp ? clamp(comp.value, 0, row.weight) : 0;
    return { label: row.label, value: val, weight: row.weight, rating: clamp((val / row.weight) * 10, 0, 10), why: row.why };
  });
}

async function authedGet<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Get failed: ${path}`);
  return res.json();
}

async function authedPatch<T>(path: string, token: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = j?.detail ? ` (${j.detail})` : "";
    } catch {
      // noop
    }
    throw new Error(`Patch failed: ${path}${detail}`);
  }
  return res.json();
}

async function authedPost<T>(path: string, token: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = j?.detail ? ` (${j.detail})` : "";
    } catch {
      // noop
    }
    throw new Error(`Post failed: ${path}${detail}`);
  }
  return res.json();
}

function parseBoardParam(value: string | null): BoardKey {
  if (value === "refresh" || value === "community") return value;
  return "new";
}

export default function OpportunitiesPage() {
  const searchParams = useSearchParams();
  const board = useMemo(() => parseBoardParam(searchParams.get("board")), [searchParams]);
  const contextToken = useToken();
  const token = useMemo(() => {
    if (contextToken) return contextToken;
    if (typeof window === "undefined") return "";
    return localStorage.getItem("dc_token") || "";
  }, [contextToken]);

  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState<string>("");
  const [contentLoadingMsg, setContentLoadingMsg] = useState<string>("");
  const [pollTick, setPollTick] = useState<number>(0);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [pullLimit, setPullLimit] = useState<number>(3);
  const [newDiscoveryInstructions, setNewDiscoveryInstructions] = useState<string>("");
  const [pullingNew, setPullingNew] = useState(false);
  const [refreshDiscoveryInstructions, setRefreshDiscoveryInstructions] = useState<string>("");
  const [pullingRefresh, setPullingRefresh] = useState(false);

  useEffect(() => {
    if (!token) return;
    const run = async () => {
      setLoading(true);
      try {
        const data = await authedGet<Opportunity[]>("/opportunities", token);
        setOpps(data || []);
      } catch (e) {
        setActionMsg(e instanceof Error ? e.message : "Failed to load opportunities");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [token, pollTick]);

  useEffect(() => {
    if (!selected) {
      setDrawerOpen(false);
      return;
    }
    const frame = window.requestAnimationFrame(() => setDrawerOpen(true));
    return () => window.cancelAnimationFrame(frame);
  }, [selected]);

  const closeDrawer = () => {
    setDrawerOpen(false);
    window.setTimeout(() => setSelected(null), 220);
  };

  const columns = useMemo<Array<{ key: ColumnKey; label: string }>>(
    () => [
      { key: "incoming", label: "Intake" },
      { key: "accepted", label: "New" },
      { key: "in_progress", label: "In-progress" },
      { key: "done", label: "Done" },
    ],
    []
  );

  const boardOpps = useMemo(() => opps.filter((o) => boardForOpportunity(o) === board), [opps, board]);
  const selectedMetrics = useMemo(() => buildAeoGeoBreakdown(selected), [selected]);
  const safeScore = clamp(selected?.priority_score ?? 0, 0, 100);
  const selectedBand = scoreBand(safeScore);

  const gaugeRadius = 90;
  const gaugeArcLength = Math.PI * gaugeRadius;
  const gaugeProgress = clamp(safeScore / 100, 0, 1);
  const gaugeFilledLength = gaugeArcLength * gaugeProgress;
  const gaugeAngle = Math.PI - gaugeProgress * Math.PI;
  const needleLength = gaugeRadius - 18;
  const needleX = 110 + needleLength * Math.cos(gaugeAngle);
  const needleY = 110 - needleLength * Math.sin(gaugeAngle);

  const byStatus = (status: ColumnKey) => boardOpps.filter((o) => matchesColumnStatus(normalizeStatus(o.status), status));

  const updateStatus = async (id: number, status: string) => {
    if (!token) return;
    try {
      const updated = await authedPatch<Opportunity>(`/opportunities/${id}`, token, { status });
      setOpps((prev) => prev.map((o) => (o.id === id ? updated : o)));
      setSelected((prev) => (prev && prev.id === id ? updated : prev));
      setActionMsg(`Moved to ${status.replace("_", " ")}`);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Failed to update status");
    }
  };

  const handleDropToColumn = async (id: number, column: ColumnKey) => {
    const targetStatus = statusForColumn(column);
    const item = opps.find((o) => o.id === id);
    if (!item || normalizeStatus(item.status) === targetStatus) return;
    await updateStatus(id, targetStatus);
  };

  const pullTopNewOpportunities = async () => {
    if (!token) return;
    try {
      setPullingNew(true);

      const discover = await authedPost<{ created_count: number; skipped_count: number; opportunities: Opportunity[] }>(
        `/opportunities/new/discover`,
        token,
        {
          website_url: "https://zeni.ai",
          limit: Math.max(pullLimit * 4, 12),
          seed_prompt: newDiscoveryInstructions.trim() || null,
        }
      );

      const pull = await authedPost<{ pulled_count: number; opportunities: Opportunity[] }>(
        `/opportunities/boards/new/pull?limit=${pullLimit}`,
        token,
        {}
      );

      const updates = new Map<number, Opportunity>();
      for (const opp of discover.opportunities || []) updates.set(opp.id, opp);
      for (const opp of pull.opportunities || []) updates.set(opp.id, opp);

      setOpps((prev) => {
        const merged = new Map(prev.map((opp) => [opp.id, opp] as const));
        for (const [id, opp] of updates.entries()) merged.set(id, opp);
        return Array.from(merged.values());
      });

      setActionMsg(
        `Strategist discovered ${discover.created_count} candidates, skipped ${discover.skipped_count}, and pulled ${pull.pulled_count} top new opportunities into Intake using OpenAI briefs and Gemini scoring.`
      );
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Failed to discover and pull new opportunities");
    } finally {
      setPullingNew(false);
    }
  };

  const discoverRefreshOpportunities = async () => {
    if (!token) return;
    try {
      setPullingRefresh(true);

      const discover = await authedPost<{ created_count: number; skipped_count?: number }>(
        `/opportunities/refresh/discover`,
        token,
        {
          website_url: "https://zeni.ai",
          limit: Math.max(pullLimit * 4, 12),
          seed_prompt: refreshDiscoveryInstructions.trim() || null,
        }
      );

      const latest = await authedGet<Opportunity[]>("/opportunities", token);
      setOpps(latest || []);

      setActionMsg(
        `Refresh strategist discovered ${discover.created_count} refresh opportunities${typeof discover.skipped_count === "number" ? ` and skipped ${discover.skipped_count}` : ""}.`
      );
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Failed to discover refresh opportunities");
    } finally {
      setPullingRefresh(false);
    }
  };

  useEffect(() => {
    const hasGenerating = opps.some((opp) => {
      const metadata = (opp.metadata_json && typeof opp.metadata_json === "object" ? opp.metadata_json : {}) as Record<string, unknown>;
      return String(metadata.content_status || "").toLowerCase() === "generating" || String(metadata.content_status || "").toLowerCase() === "queued";
    });
    if (!hasGenerating) return;
    const timer = window.setInterval(() => setPollTick((v) => v + 1), 4000);
    return () => window.clearInterval(timer);
  }, [opps]);

  const generateContentForOpportunity = async (opp: Opportunity, forceRegenerate = false) => {
    if (!token) return;

    const metadata = (opp.metadata_json && typeof opp.metadata_json === "object" ? opp.metadata_json : {}) as Record<string, unknown>;
    const currentStatus = String(metadata.content_status || "").toLowerCase();
    if ((currentStatus === "queued" || currentStatus === "generating") && !forceRegenerate) {
      setActionMsg("Content generation is already in progress for this opportunity.");
      return;
    }

    try {
      setContentLoadingMsg("Content generation started in background...");
      const result = await authedPost<{ status: string; opportunity_id: number; content_status: string }>(
        `/opportunities/${opp.id}/content/generate`,
        token,
        { force_regenerate: forceRegenerate }
      );

      setOpps((prev) =>
        prev.map((item) =>
          item.id === opp.id
            ? {
                ...item,
                metadata_json: {
                  ...(item.metadata_json || {}),
                  content_status: result.content_status || "queued",
                },
              }
            : item
        )
      );

      setSelected((prev) =>
        prev && prev.id === opp.id
          ? {
              ...prev,
              metadata_json: {
                ...(prev.metadata_json || {}),
                content_status: result.content_status || "queued",
              },
            }
          : prev
      );

      setActionMsg(forceRegenerate ? "Content regeneration started." : "Content generation started.");
      setDrawerOpen(false);
      window.setTimeout(() => setSelected(null), 250);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Failed to start content generation");
    } finally {
      setContentLoadingMsg("");
    }
  };

  const opportunityProgress = (opp: Opportunity, columnKey: ColumnKey) => {
    const metadata = (opp.metadata_json && typeof opp.metadata_json === "object" ? opp.metadata_json : {}) as Record<string, unknown>;
    const generated = metadata.generated_content && typeof metadata.generated_content === "object" ? metadata.generated_content as Record<string, unknown> : null;
    const hasBrief = Boolean(metadata.strategist_brief_version || metadata.brief_upgraded_at);
    const hasContent = Boolean(generated?.generated_at);
    const contentStatus = String(metadata.content_status || "").toLowerCase();

    if (columnKey === "incoming") return null;

    const briefClass = hasBrief ? "text-emerald-300 border-emerald-400/25 bg-emerald-500/10" : "text-white/35 border-white/10 bg-white/5";
    const contentClass =
      contentStatus === "completed" || hasContent
        ? "text-emerald-300 border-emerald-400/25 bg-emerald-500/10"
        : contentStatus === "failed"
          ? "text-rose-300 border-rose-400/25 bg-rose-500/10"
          : contentStatus === "queued" || contentStatus === "generating"
            ? "text-cyan-200 border-cyan-300/25 bg-cyan-500/10"
            : "text-white/35 border-white/10 bg-white/5";

    const briefHref = `/briefs/${opp.id}`;
    const contentHref = `/briefs/${opp.id}?autogen=1&opportunity_id=${opp.id}`;

    const PaperIcon = () => (
      <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M7 3.75h7l4 4V20.25H7z" />
        <path d="M14 3.75v4h4" />
        <path d="M9.5 12h5" />
        <path d="M9.5 15.5h5" />
      </svg>
    );

    const AiIcon = () => (
      <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="currentColor" aria-hidden="true">
        <path d="M12 3.5c1.2 3.9 2.6 5.3 6.5 6.5-3.9 1.2-5.3 2.6-6.5 6.5-1.2-3.9-2.6-5.3-6.5-6.5 3.9-1.2 5.3-2.6 6.5-6.5Z" />
      </svg>
    );

    return (
      <div className="mt-3 flex items-center gap-2">
        {hasBrief ? (
          <a
            href={briefHref}
            onClick={(e) => e.stopPropagation()}
            className={`inline-flex h-8 w-8 items-center justify-center rounded-full border transition hover:scale-[1.03] ${briefClass}`}
            title="Open Brief"
          >
            <PaperIcon />
          </a>
        ) : (
          <span className={`inline-flex h-8 w-8 items-center justify-center rounded-full border ${briefClass}`} title="Brief Not Started">
            <PaperIcon />
          </span>
        )}

        {(contentStatus === "completed" || hasContent) ? (
          <a
            href={contentHref}
            onClick={(e) => e.stopPropagation()}
            className={`inline-flex h-8 w-8 items-center justify-center rounded-full border transition hover:scale-[1.03] ${contentClass}`}
            title="Open Content"
          >
            <AiIcon />
          </a>
        ) : (
          <span
            className={`relative inline-flex h-8 w-8 items-center justify-center rounded-full border ${contentClass}`}
            title={
              contentStatus === "failed"
                ? "Content Failed"
                : contentStatus === "queued" || contentStatus === "generating"
                  ? "Content In Progress"
                  : "Content Not Started"
            }
          >
            {(contentStatus === "queued" || contentStatus === "generating") ? (
              <>
                <span className="absolute inset-0 rounded-full border-2 border-cyan-300/20" />
                <span className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-cyan-300 border-r-cyan-300" />
                <AiIcon />
              </>
            ) : (
              <AiIcon />
            )}
          </span>
        )}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-[#060b18] px-6 py-6 text-white">
      <div className="mx-auto w-full max-w-[1500px]">
        <h1 className="text-3xl font-semibold">{board === "new" ? "New Opportunities" : board === "refresh" ? "Refresh Opportunities" : "Community Opportunities"}</h1>

        {actionMsg ? <p className="mt-3 text-sm text-white/80">{actionMsg}</p> : null}
        {contentLoadingMsg ? <p className="mt-2 text-sm text-cyan-200/90">{contentLoadingMsg}</p> : null}
        {loading ? <p className="mt-2 text-sm text-white/60">Loading opportunities...</p> : null}

        <div className="mt-5">
          <div className="mb-4">
            {board === "new" ? (
              <div className="flex w-full max-w-[760px] flex-col gap-2 rounded-xl border border-white/10 bg-[#0f1628] px-3 py-3">
                <label className="text-xs font-semibold uppercase tracking-wide text-white/55">
                  Additional Strategist Instructions
                </label>
                <textarea
                  value={newDiscoveryInstructions}
                  onChange={(e) => setNewDiscoveryInstructions(e.target.value)}
                  rows={3}
                  placeholder='Example: Do not target startup-related terms. Focus only on ai bookkeeping opportunities with commercial or high-intent educational value.'
                  className="w-full rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm text-white placeholder:text-white/35"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-white/55">Select Count</span>
                  <select
                    value={pullLimit}
                    onChange={(e) => setPullLimit(Number(e.target.value) || 3)}
                    className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm text-white"
                  >
                    {[1, 2, 3, 4, 5, 6, 8, 10].map((count) => (
                      <option key={count} value={count}>
                        {count}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={pullTopNewOpportunities}
                    disabled={pullingNew}
                    className="rounded-lg border border-purple-300/40 bg-gradient-to-r from-purple-600 via-fuchsia-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-[0_6px_18px_rgba(147,51,234,0.35)] disabled:opacity-60"
                  >
                    {pullingNew ? "Submitting..." : "Submit"}
                  </button>
                </div>
              </div>
            ) : null}

            {board === "refresh" ? (
              <div className="flex w-full max-w-[760px] flex-col gap-2 rounded-xl border border-white/10 bg-[#0f1628] px-3 py-3">
                <label className="text-xs font-semibold uppercase tracking-wide text-white/55">
                  Additional Refresh Strategist Instructions
                </label>
                <textarea
                  value={refreshDiscoveryInstructions}
                  onChange={(e) => setRefreshDiscoveryInstructions(e.target.value)}
                  rows={3}
                  placeholder='Example: Prioritize high-impression queries where Zeni already ranks and the page likely needs a refresh, expansion, or stronger AI-answer formatting.'
                  className="w-full rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm text-white placeholder:text-white/35"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-white/55">Select Count</span>
                  <select
                    value={pullLimit}
                    onChange={(e) => setPullLimit(Number(e.target.value) || 3)}
                    className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm text-white"
                  >
                    {[1, 2, 3, 4, 5, 6, 8, 10].map((count) => (
                      <option key={count} value={count}>
                        {count}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={discoverRefreshOpportunities}
                    disabled={pullingRefresh}
                    className="rounded-lg border border-cyan-300/40 bg-gradient-to-r from-cyan-600 via-sky-600 to-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-[0_6px_18px_rgba(14,165,233,0.35)] disabled:opacity-60"
                  >
                    {pullingRefresh ? "Submitting..." : "Submit"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-4">
            {columns.map((c) => {
              const cards = byStatus(c.key);
              return (
                <div
                  key={c.key}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={async (e) => {
                    e.preventDefault();
                    const raw = e.dataTransfer.getData("text/plain");
                    const id = Number.parseInt(raw, 10);
                    if (Number.isFinite(id)) await handleDropToColumn(id, c.key);
                    setDraggingId(null);
                  }}
                  className={`rounded-2xl border bg-[#0f1628] p-3 ${draggingId ? "border-cyan-300/35" : "border-white/10"}`}
                >
                  <h3 className="mb-3 text-sm font-semibold text-white/80">{c.label}</h3>
                  <div className="space-y-2">
                    {cards.map((o) => (
                      <div
                        key={o.id}
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData("text/plain", String(o.id));
                          setDraggingId(o.id);
                        }}
                        onDragEnd={() => setDraggingId(null)}
                        onClick={() => setSelected(o)}
                        className="w-full cursor-pointer rounded-lg border border-white/10 bg-white/5 p-3 text-left hover:border-purple-400/40"
                      >
                        <div className="text-sm font-medium">{o.query_text}</div>
                        {(() => {
                          const score = clamp(o.priority_score ?? 0, 0, 100);
                          const band = scoreBand(score);
                          const code = priorityCode(score);
                          return (
                            <div className="mt-2 flex items-center gap-2 text-[11px] text-white/70">
                              <span className={"ml-auto font-semibold " + band.tone}>{score.toFixed(1)}</span>
                              <span className={"rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold " + band.tone}>{code}</span>
                            </div>
                          );
                        })()}
                        {opportunityProgress(o, c.key)}
                        {c.key === "incoming" && (
                          <div className="mt-3 flex gap-2">
                            <button onClick={async (e) => { e.stopPropagation(); await updateStatus(o.id, "accepted"); }} className="rounded-md border border-emerald-400/40 bg-emerald-500/20 px-2.5 py-1 text-[11px] font-semibold text-emerald-200">Accept</button>
                            <button onClick={async (e) => { e.stopPropagation(); await updateStatus(o.id, "rejected"); }} className="rounded-md border border-rose-400/40 bg-rose-500/20 px-2.5 py-1 text-[11px] font-semibold text-rose-200">Reject</button>
                          </div>
                        )}
                      </div>
                    ))}
                    {cards.length === 0 && <p className="text-xs text-white/40">No cards</p>}
                  </div>
                </div>
              );
            })}
          </section>
        </div>
      </div>

      {selected && (
        <div className={`fixed inset-0 z-50 bg-black/40 transition-opacity duration-200 ${drawerOpen ? "opacity-100" : "opacity-0"}`} onClick={closeDrawer}>
          <div className={`absolute right-0 top-0 h-full w-full max-w-2xl overflow-y-auto border-l border-white/10 bg-[#0b1326] p-6 transition-transform duration-300 ease-out ${drawerOpen ? "translate-x-0" : "translate-x-full"}`} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-3xl font-semibold">{selected.query_text}</h2>
              <button className="rounded-lg border border-white/20 px-3 py-1.5 text-sm" onClick={closeDrawer}>Close</button>
            </div>

            <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <p className="text-xs font-semibold tracking-wide text-white/60 uppercase">Step 2: Priority Speedometer</p>
              <div className="mt-3 grid gap-4 sm:grid-cols-[220px_1fr]">
                <div className="rounded-xl border border-white/10 bg-[#0a1328] p-3">
                  <svg viewBox="0 0 220 130" className="mx-auto h-36 w-full">
                    <defs><linearGradient id="priorityGaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stopColor="#f43f5e" /><stop offset="60%" stopColor="#f59e0b" /><stop offset="100%" stopColor="#22c55e" /></linearGradient></defs>
                    <path d="M 20 110 A 90 90 0 0 1 200 110" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="12" strokeLinecap="round" />
                    <path d="M 20 110 A 90 90 0 0 1 200 110" fill="none" stroke="url(#priorityGaugeGradient)" strokeWidth="12" strokeLinecap="round" strokeDasharray={`${gaugeFilledLength} ${gaugeArcLength}`} />
                    <line x1="110" y1="110" x2={needleX} y2={needleY} stroke="#f8fafc" strokeWidth="2.5" strokeLinecap="round" />
                    <circle cx="110" cy="110" r="4" fill="#0a1328" stroke="rgba(248,250,252,0.9)" strokeWidth="1.5" />
                  </svg>
                  <p className="-mt-2 text-center text-3xl font-semibold">{safeScore.toFixed(1)}</p>
                  <p className={`mt-1 text-center text-xs font-semibold ${selectedBand.tone}`}>{selectedBand.label}</p>
                  <p className="mt-1 text-center text-[11px] text-white/45">Backend score: {(selected.priority_score ?? 0).toFixed(1)}</p>
                </div>

                <div className="rounded-xl border border-white/10 bg-[#0a1328] p-3">
                  <p className="text-xs font-semibold tracking-wide text-white/60 uppercase">Score Components</p>
                  {selectedMetrics.length ? (
                    <div className="mt-3 space-y-3">
                      {selectedMetrics.map((metric) => {
                        const pct = clamp((metric.value / metric.weight) * 100, 0, 100);
                        return (
                          <div key={metric.label}>
                            <div className="mb-1 flex items-center justify-between text-xs">
                              <span className="text-white/85">{metric.label}</span>
                              <span className="text-white/70">{metric.value.toFixed(1)}/{metric.weight} ({metric.rating.toFixed(1)}/10)</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-white/10"><div className="h-1.5 rounded-full bg-cyan-400" style={{ width: `${pct}%` }} /></div>
                            <p className="mt-1 text-[11px] text-white/45">{metric.why}</p>
                          </div>
                        );
                      })}
                    </div>
                  ) : <p className="mt-2 text-sm text-white/70">No scoring explanation yet.</p>}
                </div>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Link href={`/briefs/${selected.id}`} className="rounded-xl border border-white/20 bg-white/5 px-4 py-2 text-center text-sm font-semibold text-white">View Brief</Link>
              <button
                onClick={() => generateContentForOpportunity(selected)}
                className="rounded-xl border border-purple-300/40 bg-gradient-to-r from-purple-600 via-fuchsia-600 to-indigo-600 px-4 py-2 text-center text-sm font-semibold text-white shadow-[0_6px_18px_rgba(147,51,234,0.35)]"
              >
                Create Content
              </button>
            </div>

            {selected.links && selected.links.length > 0 ? (
              <div className="mt-6">
                <p className="text-2xl font-semibold">Links</p>
                <ul className="mt-2 space-y-1 text-cyan-300">
                  {selected.links.map((l) => (
                    <li key={l}><a href={l} target="_blank" rel="noreferrer" className="hover:underline">{l}</a></li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

'use client';

import { marked } from 'marked';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { authedGet, authedPost } from '@/lib/api';
import { useToken } from '@/app/components/token-context';

type GeneratedContent = {
  opportunity_id: number;
  keyword: string;
  content_markdown: string;
  provider: string;
  model?: string | null;
  generated_at?: string | null;
};

type ParsedDoc = {
  title: string;
  metaFields: Array<{ label: string; value: string }>;
  bodyMarkdown: string;
  jsonSchema: string;
};

const META_LABELS = new Set([
  'Optimized Title Tag',
  'Meta Description',
  'URL Slug',
  'H1',
  'OG Title',
  'OG Description'
]);

function stripOuterCodeFence(md: string): string {
  const text = (md || '').trim();
  const fenced = text.match(/^```(?:markdown|md)?\n([\s\S]*?)\n```$/i);
  return fenced ? fenced[1] : text;
}

function normalizeMarkdown(md: string): string {
  const text = stripOuterCodeFence((md || '').replace(/\uFEFF/g, '').replace(/\t/g, '  '));
  const lines = text.split('\n');
  let inFence = false;

  return lines
    .map((line) => {
      if (/^```/.test(line.trim())) {
        inFence = !inFence;
        return line.trimEnd();
      }
      if (inFence) return line;
      return line.replace(/^\s{2,}/, '');
    })
    .join('\n')
    .trim();
}

function sanitizePublicationMarkdown(md: string): string {
  let text = normalizeMarkdown(md);

  // Strip legacy note lines.
  text = text
    .split('\n')
    .filter((ln) => !ln.trim().toLowerCase().startsWith('_assumptions used:'))
    .join('\n')
    .trim();

  // Remove any appended brief section from publication content.
  const cutMarkers = [/^#\s*Content Brief:.*$/im, /^##\s*Business Context\s*$/im];
  let cutIndex = -1;
  for (const marker of cutMarkers) {
    const match = marker.exec(text);
    if (match && match.index >= 0) {
      cutIndex = cutIndex < 0 ? match.index : Math.min(cutIndex, match.index);
    }
  }
  if (cutIndex >= 0) {
    text = text.slice(0, cutIndex).trim();
  }

  // Deduplicate accidental repeated phrase tails (e.g., "for startups for startups").
  const cleanedLines: string[] = [];
  let inFence = false;
  for (const line of text.split('\n')) {
    if (/^```/.test(line.trim())) {
      inFence = !inFence;
      cleanedLines.push(line);
      continue;
    }
    if (inFence) {
      cleanedLines.push(line);
      continue;
    }
    let cleaned = line;
    let prev = '';
    while (prev !== cleaned) {
      prev = cleaned;
      cleaned = cleaned.replace(/\b(for startups)\s+\1\b/gi, '$1');
    }
    cleanedLines.push(cleaned);
  }
  text = cleanedLines.join('\n');
  return text;
}

function stripHeadingSuffix(value: string): string {
  return (value || "").replace(/\s*\((H1|H2|H3)\)\s*$/i, "").trim();
}

function parseMetaBlock(block: string): Array<{ label: string; value: string }> {
  const lines = block.split('\n');
  const out: Array<{ label: string; value: string }> = [];
  let currentLabel = '';
  let currentValue: string[] = [];

  const flush = () => {
    if (!currentLabel) return;
    const value = currentValue.join('\n').trim();
    out.push({ label: stripHeadingSuffix(currentLabel), value: stripHeadingSuffix(value) });
    currentLabel = '';
    currentValue = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const heading = line.match(/^##\s+(.+)$/);
    if (heading) {
      flush();
      const label = heading[1].trim();
      currentLabel = META_LABELS.has(label) ? label : '';
      continue;
    }
    if (currentLabel) currentValue.push(line);
  }

  flush();
  return out.filter((x) => x.value.length > 0);
}

function parseLooseTopMeta(lines: string[]): { fields: Array<{ label: string; value: string }>; consumedUntil: number } {
  const fields: Array<{ label: string; value: string }> = [];
  let i = 0;

  if (/^#\s+/.test(lines[i] || '')) i += 1;
  while (i < lines.length && (!lines[i].trim() || /^\s*---+\s*$/.test(lines[i]))) i += 1;

  while (i < lines.length) {
    const labelCandidate = lines[i].trim().replace(/^##\s+/, '');
    if (!META_LABELS.has(labelCandidate)) break;
    i += 1;

    while (i < lines.length && !lines[i].trim()) i += 1;

    const valueLines: string[] = [];
    while (i < lines.length) {
      const raw = lines[i];
      const trimmed = raw.trim();
      const maybeLabel = trimmed.replace(/^##\s+/, '');
      if (META_LABELS.has(maybeLabel)) break;
      if (/^\s*---+\s*$/.test(trimmed)) break;
      valueLines.push(raw);
      i += 1;
    }

    const value = valueLines.join('\n').trim();
    if (!value) break;
    fields.push({ label: stripHeadingSuffix(labelCandidate), value: stripHeadingSuffix(value) });

    while (i < lines.length && !lines[i].trim()) i += 1;
  }

  return { fields, consumedUntil: i };
}

function parseStructuredDocument(md: string): ParsedDoc {
  const normalized = sanitizePublicationMarkdown(md);
  const lines = normalized.split('\n');

  let title = '';
  const titleMatch = lines[0]?.match(/^#\s+(.+)$/);
  if (titleMatch) title = stripHeadingSuffix(titleMatch[1].trim());

  const ruleIndexes: number[] = [];
  lines.forEach((line, i) => {
    if (/^\s*---+\s*$/.test(line)) ruleIndexes.push(i);
  });

  let metaFields: Array<{ label: string; value: string }> = [];
  let bodyLines = [...lines];

  if (title && ruleIndexes.length >= 2 && ruleIndexes[0] > 0) {
    const metaBlock = lines.slice(ruleIndexes[0] + 1, ruleIndexes[1]).join('\n').trim();
    const parsedMeta = parseMetaBlock(metaBlock);
    if (parsedMeta.length >= 3) {
      metaFields = parsedMeta;
      bodyLines = lines.slice(ruleIndexes[1] + 1);
    }
  }

  if (metaFields.length === 0) {
    const loose = parseLooseTopMeta(lines);
    if (loose.fields.length >= 3) {
      metaFields = loose.fields;
      bodyLines = lines.slice(loose.consumedUntil);
    }
  }

  let bodyMarkdown = bodyLines.join('\n').trim();
  let jsonSchema = '';

  const schemaHeading = /^##\s+Recommended JSON-LD Schema Markup\s*$/im;
  const schemaStart = bodyMarkdown.search(schemaHeading);
  if (schemaStart >= 0) {
    const before = bodyMarkdown.slice(0, schemaStart).trim();
    const afterHeading = bodyMarkdown.slice(schemaStart).replace(schemaHeading, '').trim();
    const nextSectionIdx = afterHeading.search(/^##\s+/m);
    const schemaChunk = nextSectionIdx >= 0 ? afterHeading.slice(0, nextSectionIdx).trim() : afterHeading.trim();
    const after = nextSectionIdx >= 0 ? afterHeading.slice(nextSectionIdx).trim() : '';

    jsonSchema = schemaChunk.replace(/^```(?:json)?\n?/i, '').replace(/\n```$/i, '').trim();
    bodyMarkdown = [before, after].filter(Boolean).join('\n\n').trim();
  }

  return { title, metaFields, bodyMarkdown, jsonSchema };
}

export default function BriefPage() {
  const token = useToken();
  const params = useParams<{ id: string | string[] }>();
  const searchParams = useSearchParams();
  const routeId = Array.isArray(params?.id) ? params.id[0] : params?.id;
  const queryId = searchParams.get('opportunity_id') || searchParams.get('id') || '';
  const id = (routeId || queryId || '').trim();
  const autogenTriggered = useRef(false);

  const [brief, setBrief] = useState('');
  const [generated, setGenerated] = useState<GeneratedContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showBriefPreview, setShowBriefPreview] = useState(false);

  useEffect(() => {
    if (!token || !id) {
      setError('Missing opportunity id in URL.');
      return;
    }
    let cancelled = false;

    async function load() {
      try {
        const briefData = await authedGet(`/opportunities/${id}/brief`, token);
        if (!cancelled) setBrief(briefData.brief || '');

        try {
          const contentData = await authedGet(`/opportunities/${id}/content`, token);
          if (!cancelled) setGenerated(contentData);
        } catch {
          if (!cancelled) setGenerated(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [token, id]);

  async function generateContent(force_regenerate = false) {
    if (!token || !id) {
      setError('Missing opportunity id in URL.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const data = await authedPost(`/opportunities/${id}/content/generate`, token, { force_regenerate });
      setGenerated(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const shouldAutogen = searchParams.get('autogen') === '1';
    if (!shouldAutogen || autogenTriggered.current || !token || !id || loading) return;
    if (generated) {
      autogenTriggered.current = true;
      return;
    }
    autogenTriggered.current = true;
    void generateContent(false);
  }, [searchParams, token, id, loading, generated]);

  const normalizedBrief = useMemo(() => normalizeMarkdown(brief), [brief]);
  const normalizedGenerated = useMemo(() => sanitizePublicationMarkdown(generated?.content_markdown || ''), [generated?.content_markdown]);
  const parsed = useMemo(() => parseStructuredDocument(normalizedGenerated), [normalizedGenerated]);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-brand/25 bg-[#101a2f] p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-xl font-semibold text-ink">Publication Content</h2>
            <p className="text-xs text-muted">Primary workflow: generate full article output from the brief.</p>
          </div>
          <div className="flex gap-2">
            <button className="zeni-btn zeni-btn-sm" onClick={() => generateContent(false)} disabled={loading}>
              {loading ? 'Generating...' : generated ? 'Use existing output' : 'Generate content'}
            </button>
            <button className="zeni-btn zeni-btn-secondary zeni-btn-sm" onClick={() => generateContent(true)} disabled={loading}>
              Regenerate
            </button>
          </div>
        </div>

        {error && <p className="mb-3 text-sm text-red-300">{error}</p>}

        {generated ? (
          <>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted">
                Source: {generated.provider}
                {generated.model ? ` · Model: ${generated.model}` : ''}
                {generated.generated_at ? ` · Generated: ${new Date(generated.generated_at).toLocaleString()}` : ''}
              </p>
              <a
                href={`data:text/markdown;charset=utf-8,${encodeURIComponent(normalizedGenerated)}`}
                download={`article-${id}.md`}
                className="zeni-btn zeni-btn-secondary zeni-btn-sm inline-flex"
              >
                Download article markdown
              </a>
            </div>

            <div className="mx-auto w-full max-w-[920px] overflow-hidden rounded-md border border-slate-300 bg-white px-10 py-12 shadow-[0_18px_45px_rgba(0,0,0,0.35)]">
              <div className="doc-prose">
                {parsed.title ? <h1>{stripHeadingSuffix(parsed.title)}</h1> : null}

                {parsed.metaFields.length > 0 ? (
                  <div className="doc-meta-grid">
                    {parsed.metaFields.map((item) => (
                      <section key={item.label} className="doc-meta-card">
                        <h3>{stripHeadingSuffix(item.label)}</h3>
                        <p>{stripHeadingSuffix(item.value.replace(/^##\s+/, ''))}</p>
                      </section>
                    ))}
                  </div>
                ) : null}

                <article dangerouslySetInnerHTML={{ __html: marked.parse(parsed.bodyMarkdown || normalizedGenerated) as string }} />

                {parsed.jsonSchema ? (
                  <section className="doc-json-section">
                    <h2>Recommended JSON-LD Schema Markup</h2>
                    <div className="doc-codebox">
                      <div className="doc-codebox-head">
                        <span>{'<>'} JSON</span>
                        <span>copy</span>
                      </div>
                      <pre>
                        <code>{parsed.jsonSchema}</code>
                      </pre>
                    </div>
                  </section>
                ) : null}
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted">No generated article yet. Click Generate content to build a publication-ready draft.</p>
        )}
      </div>

      <div className="rounded-2xl border border-white/10 bg-panel/85 p-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-lg font-semibold text-ink">Content Brief</h3>
            <p className="text-xs text-muted">Collapsed by default. Expand to view the full brief in document style.</p>
          </div>
          <div className="flex gap-2">
            <button className="zeni-btn zeni-btn-secondary zeni-btn-sm" onClick={() => setShowBriefPreview((v) => !v)}>
              {showBriefPreview ? 'Hide full brief' : 'Show full brief'}
            </button>
            <a
              href={`data:text/markdown;charset=utf-8,${encodeURIComponent(normalizedBrief)}`}
              download={`brief-${id}.md`}
              className="zeni-btn zeni-btn-secondary zeni-btn-sm"
            >
              Download brief
            </a>
          </div>
        </div>

        {showBriefPreview ? (
          <div className="mx-auto w-full max-w-[920px] overflow-hidden rounded-md border border-slate-300 bg-white px-10 py-12 shadow-[0_18px_45px_rgba(0,0,0,0.25)]">
            <article className="doc-prose" dangerouslySetInnerHTML={{ __html: marked.parse(normalizedBrief) as string }} />
          </div>
        ) : (
          <p className="text-sm text-muted">Full brief is hidden.</p>
        )}
      </div>
    </div>
  );
}

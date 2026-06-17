'use client';

import { useEffect, useMemo, useState } from 'react';
import { authedGet, connectGscStart, saveSourceCredentials, SourceConfig, testSource } from '@/lib/api';
import { useToken } from '../components/token-context';

type ProviderKey = 'openai' | 'anthropic' | 'gemini';
type StageInstructions = {
  opportunity: string;
  rating: string;
  briefing: string;
  content: string;
};

type GeminiInstructions = {
  rating: string;
  review: string;
  analytics: string;
};

type ProviderState = {
  apiKey: string;
  model: string;
  instructions: StageInstructions;
};

type GeminiState = {
  apiKey: string;
  model: string;
  instructions: GeminiInstructions;
};

type CompanyProfileState = {
  companyName: string;
  companyWebsite: string;
  companyContext: string;
};

function emptyInstructions(): StageInstructions {
  return { opportunity: '', rating: '', briefing: '', content: '' };
}

function emptyGeminiInstructions(): GeminiInstructions {
  return { rating: '', review: '', analytics: '' };
}

function toInstructions(raw: unknown): StageInstructions {
  if (!raw || typeof raw !== 'object') return emptyInstructions();
  const r = raw as Record<string, unknown>;
  return {
    opportunity: String(r.opportunity || ''),
    rating: String(r.rating || ''),
    briefing: String(r.briefing || ''),
    content: String(r.content || ''),
  };
}

function toGeminiInstructions(raw: unknown): GeminiInstructions {
  if (!raw || typeof raw !== 'object') return emptyGeminiInstructions();
  const r = raw as Record<string, unknown>;
  return {
    rating: String(r.rating || ''),
    review: String(r.review || r.content_review || ''),
    analytics: String(r.analytics || ''),
  };
}

export default function SettingsPage() {
  const token = useToken();
  const [sources, setSources] = useState<SourceConfig[]>([]);
  const [busy, setBusy] = useState('');
  const [statusMsg, setStatusMsg] = useState<string>('');

  const [openai, setOpenai] = useState<ProviderState>({ apiKey: '', model: 'gpt-4.1-mini', instructions: emptyInstructions() });
  const [anthropic, setAnthropic] = useState<ProviderState>({ apiKey: '', model: 'claude-3-5-sonnet-latest', instructions: emptyInstructions() });
  const [gemini, setGemini] = useState<GeminiState>({ apiKey: '', model: 'gemini-1.5-pro', instructions: emptyGeminiInstructions() });
  const [company, setCompany] = useState<CompanyProfileState>({ companyName: '', companyWebsite: '', companyContext: '' });

  const [semrushApiKey, setSemrushApiKey] = useState('');
  const [gaApiKey, setGaApiKey] = useState('');
  const [gaPropertyId, setGaPropertyId] = useState('');

  const sourceMap = useMemo(() => Object.fromEntries(sources.map((s) => [s.source_name, s])), [sources]);

  async function loadSources() {
    if (!token) return;
    const data = await authedGet('/sources', token);
    setSources(data);
  }

  useEffect(() => {
    loadSources();
  }, [token]);

  useEffect(() => {
    const o = sourceMap.openai?.config || {};
    const oPrompts = (o.agent_prompts || {}) as Record<string, unknown>;
    setOpenai((prev) => ({
      ...prev,
      model: String(o.model || 'gpt-4.1-mini'),
      instructions: {
        opportunity: String(oPrompts.strategist || ''),
        rating: String(oPrompts.refresh || ''),
        briefing: String(oPrompts.community || ''),
        content: String(oPrompts.content_creator || ''),
      },
    }));

    const a = sourceMap.anthropic?.config || {};
    setAnthropic((prev) => ({ ...prev, model: String(a.model || 'claude-3-5-sonnet-latest'), instructions: toInstructions(a.instructions) }));

    const g = sourceMap.gemini?.config || {};
    setGemini((prev) => ({ ...prev, model: String(g.model || 'gemini-1.5-pro'), instructions: toGeminiInstructions(g.instructions) }));

    const ga = sourceMap.google_analytics?.config || {};
    setGaPropertyId(String(ga.property_id || ''));

    const c = sourceMap.company_profile?.config || {};
    setCompany({
      companyName: String(c.company_name || ''),
      companyWebsite: String(c.company_website || ''),
      companyContext: String(c.company_context || ''),
    });
  }, [sourceMap.openai?.config, sourceMap.anthropic?.config, sourceMap.gemini?.config, sourceMap.google_analytics?.config, sourceMap.company_profile?.config]);

  async function saveProvider(key: ProviderKey) {
    if (!token) return;
    try {
      setBusy(key);
      if (key === 'openai') {
        const state = openai;
        await saveSourceCredentials(token, 'openai', {
          api_key: state.apiKey || undefined,
          model: state.model,
          agent_prompts: {
            strategist: state.instructions.opportunity,
            refresh: state.instructions.rating,
            community: state.instructions.briefing,
            content_creator: state.instructions.content,
          },
        }, 'OpenAI orchestrator and workflow instructions');
      } else if (key === 'anthropic') {
        const state = anthropic;
        await saveSourceCredentials(token, 'anthropic', {
          api_key: state.apiKey || undefined,
          model: state.model,
          instructions: {
            opportunity: state.instructions.opportunity,
            rating: state.instructions.rating,
            briefing: state.instructions.briefing,
          },
        }, 'anthropic provider configuration');
      } else {
        const state = gemini;
        await saveSourceCredentials(token, 'gemini', {
          api_key: state.apiKey || undefined,
          model: state.model,
          instructions: {
            rating: state.instructions.rating,
            review: state.instructions.review,
            analytics: state.instructions.analytics,
          },
        }, 'gemini provider configuration');
      }
      const result = await testSource(token, key);
      setStatusMsg(`${key.toUpperCase()}: ${result.message}`);
      await loadSources();
      if (key === 'openai') setOpenai((p) => ({ ...p, apiKey: '' }));
      if (key === 'anthropic') setAnthropic((p) => ({ ...p, apiKey: '' }));
      if (key === 'gemini') setGemini((p) => ({ ...p, apiKey: '' }));
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : `Failed to save ${key}`);
    } finally {
      setBusy('');
    }
  }

  async function connectGsc() {
    if (!token) return;
    try {
      setBusy('gsc');
      const result = await connectGscStart(token);
      if (result?.auth_url) {
        window.location.href = result.auth_url;
        return;
      }
      setStatusMsg('Failed to start Google Search Console OAuth');
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : 'Failed to start GSC OAuth');
    } finally {
      setBusy('');
    }
  }

  async function saveSemrush() {
    if (!token) return;
    try {
      setBusy('semrush');
      await saveSourceCredentials(token, 'semrush', { api_key: semrushApiKey || undefined }, 'SEMrush connection for Gemini workflows');
      const result = await testSource(token, 'semrush');
      setStatusMsg(`SEMRUSH: ${result.message}`);
      setSemrushApiKey('');
      await loadSources();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : 'Failed to save SEMrush');
    } finally {
      setBusy('');
    }
  }

  async function saveGoogleAnalytics() {
    if (!token) return;
    try {
      setBusy('ga');
      await saveSourceCredentials(
        token,
        'google_analytics',
        { api_key: gaApiKey || undefined, property_id: gaPropertyId },
        'Google Analytics connection for Gemini workflows',
      );
      const result = await testSource(token, 'google_analytics');
      setStatusMsg(`GOOGLE_ANALYTICS: ${result.message}`);
      setGaApiKey('');
      await loadSources();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : 'Failed to save Google Analytics');
    } finally {
      setBusy('');
    }
  }

  async function saveCompanyProfile() {
    if (!token) return;
    try {
      setBusy('company');
      await saveSourceCredentials(token, 'company_profile', {
        company_name: company.companyName,
        company_website: company.companyWebsite,
        company_context: company.companyContext,
      }, 'Company profile and site context');
      const result = await testSource(token, 'company_profile');
      setStatusMsg(`Company Profile: ${result.message}`);
      await loadSources();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : 'Failed to save company profile');
    } finally {
      setBusy('');
    }
  }

  function renderInstructionBoxes(value: StageInstructions, onChange: (next: StageInstructions) => void) {
    return (
      <div className="grid gap-2 md:grid-cols-2">
        <textarea value={value.opportunity} onChange={(e) => onChange({ ...value, opportunity: e.target.value })} className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Opportunity identification instructions" />
        <textarea value={value.rating} onChange={(e) => onChange({ ...value, rating: e.target.value })} className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Rating/scoring instructions" />
        <textarea value={value.briefing} onChange={(e) => onChange({ ...value, briefing: e.target.value })} className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Briefing instructions" />
        <textarea value={value.content} onChange={(e) => onChange({ ...value, content: e.target.value })} className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Content creation instructions" />
      </div>
    );
  }

  function renderOpenAiStrategyBoxes(value: StageInstructions, onChange: (next: StageInstructions) => void) {
  return (
    <div className="grid gap-2 md:grid-cols-3">
      <textarea
        value={value.opportunity}
        onChange={(e) => onChange({ ...value, opportunity: e.target.value })}
        className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm"
        placeholder="New opportunity strategy instructions"
      />
      <textarea
        value={value.rating}
        onChange={(e) => onChange({ ...value, rating: e.target.value })}
        className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm"
        placeholder="Revamp opportunity strategy instructions"
      />
      <textarea
        value={value.briefing}
        onChange={(e) => onChange({ ...value, briefing: e.target.value })}
        className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm"
        placeholder="Community opportunity strategy instructions"
      />
    </div>
  );
}

function providerConnected(name: string): boolean {
    return sourceMap[name]?.status === 'connected';
  }

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-white/10 bg-[#0f1628] p-5">
        <h2 className="text-2xl font-semibold">Integrations</h2>
        <p className="mt-1 text-sm text-white/70">Configure only the core model providers and company profile context used by opportunity, rating, briefing, and content workflows.</p>
        {statusMsg ? <p className="mt-3 text-sm text-cyan-200">{statusMsg}</p> : null}
      </section>

      <section className="rounded-2xl border border-white/10 bg-[#0f1628] p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-xl font-semibold"><img src="/logos/openai.svg" alt="OpenAI logo" className="h-7 w-7 rounded-full bg-white p-1.5 object-contain" />OpenAI</h3>
          <span className={`text-xs ${providerConnected('openai') ? 'text-emerald-300' : 'text-white/60'}`}>{providerConnected('openai') ? 'Connected' : 'Disconnected'}</span>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          <input value={openai.apiKey} onChange={(e) => setOpenai((p) => ({ ...p, apiKey: e.target.value }))} className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="OpenAI API key (leave blank to keep existing)" />
          <input value={openai.model} onChange={(e) => setOpenai((p) => ({ ...p, model: e.target.value }))} className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Model" />
        </div>
        <p className="mt-3 text-xs text-white/60">Instruction boxes: New Opportunity Strategy, Revamp Opportunity Strategy, Community Opportunity Strategy</p>
        <div className="mt-2">{renderOpenAiStrategyBoxes(openai.instructions, (instructions) => setOpenai((p) => ({ ...p, instructions })))}</div>
        <button onClick={() => saveProvider('openai')} disabled={busy === 'openai'} className="mt-3 rounded-lg border border-purple-400/50 bg-purple-600/30 px-4 py-2 text-sm font-semibold disabled:opacity-60">{busy === 'openai' ? 'Saving...' : 'Save OpenAI'}</button>
      </section>

      <section className="rounded-2xl border border-white/10 bg-[#0f1628] p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-xl font-semibold"><img src="/logos/anthropic.svg" alt="Anthropic logo" className="h-7 w-7 rounded-full bg-white p-1.5 object-contain" />Anthropic</h3>
          <span className={`text-xs ${providerConnected('anthropic') ? 'text-emerald-300' : 'text-white/60'}`}>{providerConnected('anthropic') ? 'Connected' : 'Disconnected'}</span>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          <input value={anthropic.apiKey} onChange={(e) => setAnthropic((p) => ({ ...p, apiKey: e.target.value }))} className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Anthropic API key (leave blank to keep existing)" />
          <input value={anthropic.model} onChange={(e) => setAnthropic((p) => ({ ...p, model: e.target.value }))} className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Model" />
        </div>
        <p className="mt-3 text-xs text-white/60">Instruction boxes: New Opportunity Content Creation, Revamp Opportunity Content Creation, Community Content Creation</p>
        <div className="mt-2 grid gap-2 md:grid-cols-3">
          <textarea
            value={anthropic.instructions.opportunity}
            onChange={(e) => setAnthropic((p) => ({ ...p, instructions: { ...p.instructions, opportunity: e.target.value } }))}
            className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm"
            placeholder="New opportunity content creation instructions"
          />
          <textarea
            value={anthropic.instructions.rating}
            onChange={(e) => setAnthropic((p) => ({ ...p, instructions: { ...p.instructions, rating: e.target.value } }))}
            className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm"
            placeholder="Revamp opportunity content creation instructions"
          />
          <textarea
            value={anthropic.instructions.briefing}
            onChange={(e) => setAnthropic((p) => ({ ...p, instructions: { ...p.instructions, briefing: e.target.value } }))}
            className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm"
            placeholder="Community content creation instructions"
          />
        </div>
        <button onClick={() => saveProvider('anthropic')} disabled={busy === 'anthropic'} className="mt-3 rounded-lg border border-purple-400/50 bg-purple-600/30 px-4 py-2 text-sm font-semibold disabled:opacity-60">{busy === 'anthropic' ? 'Saving...' : 'Save Anthropic'}</button>
      </section>

      <section className="rounded-2xl border border-white/10 bg-[#0f1628] p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-xl font-semibold"><img src="/logos/gemini.svg" alt="Google Gemini logo" className="h-7 w-7 rounded-full bg-white p-1.5 object-contain" />Google Gemini</h3>
          <span className={`text-xs ${providerConnected('gemini') ? 'text-emerald-300' : 'text-white/60'}`}>{providerConnected('gemini') ? 'Connected' : 'Disconnected'}</span>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          <input value={gemini.apiKey} onChange={(e) => setGemini((p) => ({ ...p, apiKey: e.target.value }))} className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Gemini API key (leave blank to keep existing)" />
          <input value={gemini.model} onChange={(e) => setGemini((p) => ({ ...p, model: e.target.value }))} className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Model" />
        </div>

        <p className="mt-3 text-xs text-white/60">Instruction boxes: Rating/Scoring, Content Review, Analytics</p>
        <div className="mt-2 grid gap-2 md:grid-cols-3">
          <textarea value={gemini.instructions.rating} onChange={(e) => setGemini((p) => ({ ...p, instructions: { ...p.instructions, rating: e.target.value } }))} className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Rating/scoring instructions" />
          <textarea value={gemini.instructions.review} onChange={(e) => setGemini((p) => ({ ...p, instructions: { ...p.instructions, review: e.target.value } }))} className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Content review instructions" />
          <textarea value={gemini.instructions.analytics} onChange={(e) => setGemini((p) => ({ ...p, instructions: { ...p.instructions, analytics: e.target.value } }))} className="min-h-28 rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Analytics instructions" />
        </div>

        <div className="mt-4 rounded-xl border border-white/10 bg-[#0a1222] p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-white/60">Data Connections</p>
          <div className="mt-2 grid gap-2 md:grid-cols-3">
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-2">
              <p className="flex items-center gap-2 text-sm font-medium"><img src="/logos/googlesearchconsole.svg" alt="Google Search Console logo" className="h-5 w-5 rounded-full bg-white p-1 object-contain" />Google Search Console</p>
              <p className={`mt-1 text-xs ${providerConnected('gsc') ? 'text-emerald-300' : sourceMap.gsc?.status === 'pending' ? 'text-amber-300' : 'text-white/60'}`}>
                {providerConnected('gsc') ? 'Connected' : sourceMap.gsc?.status === 'pending' ? 'Pending OAuth' : 'Disconnected'}
              </p>
              <button onClick={connectGsc} disabled={busy === 'gsc'} className="mt-2 rounded-md border border-white/20 bg-white/5 px-2 py-1 text-xs font-semibold disabled:opacity-60">{busy === 'gsc' ? 'Connecting...' : 'Connect'}</button>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-2">
              <p className="flex items-center gap-2 text-sm font-medium"><img src="/logos/semrush.svg" alt="SEMrush logo" className="h-5 w-5 rounded-full bg-white p-1 object-contain" />SEMrush</p>
              <p className={`mt-1 text-xs ${providerConnected('semrush') ? 'text-emerald-300' : 'text-white/60'}`}>{providerConnected('semrush') ? 'Connected' : 'Disconnected'}</p>
              <input value={semrushApiKey} onChange={(e) => setSemrushApiKey(e.target.value)} className="mt-2 w-full rounded-md border border-white/15 bg-[#081225] px-2 py-1 text-xs" placeholder="SEMrush API key (optional if already saved)" />
              <button onClick={saveSemrush} disabled={busy === 'semrush'} className="mt-2 rounded-md border border-white/20 bg-white/5 px-2 py-1 text-xs font-semibold disabled:opacity-60">{busy === 'semrush' ? 'Saving...' : 'Save'}</button>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-2">
              <p className="flex items-center gap-2 text-sm font-medium"><img src="/logos/googleanalytics.svg" alt="Google Analytics logo" className="h-5 w-5 rounded-full bg-white p-1 object-contain" />Google Analytics</p>
              <p className={`mt-1 text-xs ${providerConnected('google_analytics') ? 'text-emerald-300' : 'text-white/60'}`}>{providerConnected('google_analytics') ? 'Connected' : 'Disconnected'}</p>
              <input value={gaApiKey} onChange={(e) => setGaApiKey(e.target.value)} className="mt-2 w-full rounded-md border border-white/15 bg-[#081225] px-2 py-1 text-xs" placeholder="GA API key (optional if already saved)" />
              <input value={gaPropertyId} onChange={(e) => setGaPropertyId(e.target.value)} className="mt-2 w-full rounded-md border border-white/15 bg-[#081225] px-2 py-1 text-xs" placeholder="GA property id (e.g. 123456789)" />
              <button onClick={saveGoogleAnalytics} disabled={busy === 'ga'} className="mt-2 rounded-md border border-white/20 bg-white/5 px-2 py-1 text-xs font-semibold disabled:opacity-60">{busy === 'ga' ? 'Saving...' : 'Save'}</button>
            </div>
          </div>
        </div>

        <button onClick={() => saveProvider('gemini')} disabled={busy === 'gemini'} className="mt-3 rounded-lg border border-purple-400/50 bg-purple-600/30 px-4 py-2 text-sm font-semibold disabled:opacity-60">{busy === 'gemini' ? 'Saving...' : 'Save Gemini'}</button>
      </section>

      <section className="rounded-2xl border border-white/10 bg-[#0f1628] p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xl font-semibold">Company Profile</h3>
          <span className={`text-xs ${providerConnected('company_profile') ? 'text-emerald-300' : 'text-white/60'}`}>{providerConnected('company_profile') ? 'Configured' : 'Not configured'}</span>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          <input value={company.companyName} onChange={(e) => setCompany((p) => ({ ...p, companyName: e.target.value }))} className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Company name" />
          <input value={company.companyWebsite} onChange={(e) => setCompany((p) => ({ ...p, companyWebsite: e.target.value }))} className="rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="https://company.com" />
        </div>
        <textarea value={company.companyContext} onChange={(e) => setCompany((p) => ({ ...p, companyContext: e.target.value }))} className="mt-2 min-h-28 w-full rounded-lg border border-white/15 bg-[#081225] px-3 py-2 text-sm" placeholder="Business model, ICP, differentiation, product lines, tone-of-voice, EEAT references..." />
        <button onClick={saveCompanyProfile} disabled={busy === 'company'} className="mt-3 rounded-lg border border-purple-400/50 bg-purple-600/30 px-4 py-2 text-sm font-semibold disabled:opacity-60">{busy === 'company' ? 'Saving...' : 'Save Company Profile'}</button>
      </section>
    </div>
  );
}

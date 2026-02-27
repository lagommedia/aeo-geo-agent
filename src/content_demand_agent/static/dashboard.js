function setStatus(message, isError = false) {
  const el = document.getElementById("status");
  el.textContent = message;
  el.style.color = isError ? "#9d1b1b" : "";
}

async function runSnapshot() {
  const response = await fetch("/agent/run", {
    method: "POST",
    credentials: "include",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Failed to run agent");
  }
  return data;
}

function table(headers, rows) {
  if (!rows.length) {
    return "<p>No rows.</p>";
  }
  return `
    <table>
      <thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
      <tbody>${rows
        .map((r) => `<tr>${r.map((v) => `<td>${v}</td>`).join("")}</tr>`)
        .join("")}</tbody>
    </table>
  `;
}

function render(data) {
  document.getElementById("kpi-citation").textContent = `${data.ai_citation_share}%`;
  document.getElementById("kpi-pipeline").textContent = data.non_branded_pipeline.toLocaleString();
  const gap = data.velocity_gap?.post_gap ?? 0;
  document.getElementById("kpi-velocity").textContent = `${gap} posts / 30d`;

  document.getElementById("rising-queries").innerHTML = table(
    ["Query", "Growth %", "Rank", "Type"],
    data.rising_queries.map((q) => [q.query, q.growth_pct, q.current_rank, q.brand ? "Brand" : "Non-brand"])
  );

  document.getElementById("decaying-pages").innerHTML = table(
    ["URL", "Primary Query", "Rank Drop", "Updated Days Ago"],
    data.decaying_pages.map((p) => [p.url, p.primary_query, p.rank_drop, p.updated_days_ago])
  );

  document.getElementById("snippet-recs").innerHTML = table(
    ["Target", "Schema", "Format Hint", "Rationale"],
    data.snippet_recommendations.map((r) => [r.page_or_query, r.schema_type, r.format_hint, r.rationale])
  );

  document.getElementById("content-briefs").innerHTML = table(
    ["Query", "Funnel", "Intent", "Snippet Format"],
    data.content_briefs.map((b) => [b.query, `<span class="pill">${b.funnel_stage}</span>`, b.intent, b.ai_snippet_format])
  );

  document.getElementById("uncited-mentions").innerHTML = table(
    ["Query", "Source", "Context", "Cited Domain"],
    data.uncited_brand_mentions.map((m) => [m.query, m.source, m.mention_context, m.cited_domain || "None"])
  );
}

document.getElementById("run-agent-btn").addEventListener("click", async () => {
  try {
    setStatus("Running agent snapshot...");
    const data = await runSnapshot();
    render(data);
    setStatus("Snapshot complete.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

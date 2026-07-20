const els = {
  campaign: document.getElementById("campaignInput"),
  budget: document.getElementById("budgetInput"),
  generate: document.getElementById("generateBtn"),
  publish: document.getElementById("publishBtn"),
  publishedStatus: document.getElementById("publishedStatus"),
  status: document.getElementById("statusText"),
  optimizationStatus: document.getElementById("optimizationStatus"),
  optimizationSummary: document.getElementById("optimizationSummary"),
  selectedCandidates: document.getElementById("selectedCandidates"),
};

let currentCampaignId = "";

async function generateStrategy() {
  els.generate.disabled = true;
  els.status.textContent = "正在生成策略";
  els.optimizationStatus.textContent = "正在计算候选价值";
  try {
    const response = await fetch("/api/strategy/optimize/real-data", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        campaign_id: els.campaign.value,
        budget: Number(els.budget.value) * 10000,
        selected_sample_limit: 10,
        evaluation_time: "2026-07-17 12:00:00",
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "策略生成失败");
    renderOptimization(data);
    currentCampaignId = data.strategy_draft.campaign_id;
    els.publish.disabled = false;
    els.publishedStatus.textContent = "策略草稿待发布";
    els.optimizationStatus.textContent = "策略已生成";
    els.status.textContent = "策略已生成，等待发布给 C 端";
  } catch (error) {
    els.status.textContent = error.message;
    els.optimizationStatus.textContent = "生成失败";
  } finally {
    els.generate.disabled = false;
  }
}

async function publishPlan() {
  if (!currentCampaignId) return;
  els.publish.disabled = true;
  els.status.textContent = "正在发布";
  try {
    const response = await fetch("/api/strategy/publications", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({campaign_id: currentCampaignId}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "发布失败");
    els.publishedStatus.textContent = `已发布 ${data.publication.strategy_version}`;
    els.status.textContent = "已发布给 C 端";
  } catch (error) {
    els.status.textContent = error.message;
    els.publish.disabled = false;
  }
}

function renderOptimization(data) {
  const summary = data.selection_summary;
  const candidateCount = summary.scored_candidate_count.toLocaleString();
  els.optimizationSummary.textContent =
    `从 ${candidateCount} 条合规候选中选中 ${summary.selected_candidate_count.toLocaleString()} 人，` +
    `使用预算 ${summary.budget_used.toFixed(2)} 元，预计净价值 ${summary.expected_net_value.toFixed(2)} 元，` +
    `预计转化 ${summary.expected_conversion_count.toFixed(2)} 人。`;
  els.selectedCandidates.innerHTML = data.selected_candidate_sample.map(item => {
    const value = item.strategy_value;
    const conversion = item.model_scores.probabilities.p_conversion;
    return `
      <div class="row">
        <div>
          <strong>${item.product_name}</strong>
          <p>${item.customer_id} · ${item.channel} · 转化概率 ${(conversion * 100).toFixed(1)}%</p>
        </div>
        <span class="pill">净价值 ${value.expected_net_value.toFixed(1)}</span>
      </div>
    `;
  }).join("") || "<p>当前预算下没有正向净价值候选。</p>";
}

els.generate.addEventListener("click", generateStrategy);
els.publish.addEventListener("click", publishPlan);

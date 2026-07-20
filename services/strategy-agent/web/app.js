const els = {
  campaign: document.getElementById("campaignInput"),
  budget: document.getElementById("budgetInput"),
  generate: document.getElementById("generateBtn"),
  publish: document.getElementById("publishBtn"),
  publishedStatus: document.getElementById("publishedStatus"),
  status: document.getElementById("statusText"),
  campaignId: document.getElementById("campaignId"),
  audience: document.getElementById("audienceMetric"),
  uplift: document.getElementById("upliftMetric"),
  roi: document.getElementById("roiMetric"),
  riskMetric: document.getElementById("riskMetric"),
  segments: document.getElementById("segments"),
  channels: document.getElementById("channels"),
  content: document.getElementById("contentBox"),
  compliance: document.getElementById("compliance"),
  chart: document.getElementById("forecastChart"),
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
    renderStrategyView(data.strategy_view, data.campaign_id);
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
  els.optimizationSummary.textContent =
    `从 ${summary.scored_candidate_count.toLocaleString()} 条合规候选中选中 ` +
    `${summary.selected_candidate_count.toLocaleString()} 人，使用预算 ${summary.budget_used.toFixed(2)} 元，` +
    `预计净价值 ${summary.expected_net_value.toFixed(2)} 元，预计转化 ${summary.expected_conversion_count.toFixed(2)} 人。` +
    `以下展示前 ${data.selected_candidate_sample.length} 条策略样例。`;
  els.selectedCandidates.innerHTML = data.selected_candidate_sample.map(item => `
    <div class="row">
      <div>
        <strong>${item.product_name}</strong>
        <p>${item.customer_id} · ${item.channel} · 转化概率 ${(item.model_scores.probabilities.p_conversion * 100).toFixed(1)}%</p>
      </div>
      <span class="pill">净价值 ${item.strategy_value.expected_net_value.toFixed(1)}</span>
    </div>
  `).join("") || "<p>当前预算下没有正向净价值候选。</p>";
}

function renderStrategyView(view, campaignId) {
  const metrics = view.metrics;
  els.campaignId.textContent = campaignId;
  els.audience.textContent = `${metrics.audience_size.toLocaleString()} 人`;
  els.uplift.textContent = `${metrics.conversion_rate}%`;
  els.roi.textContent = `${metrics.expected_net_value_wan} 万`;
  els.riskMetric.textContent = `${metrics.budget_utilization}%`;
  renderSegments(view.segments);
  renderChannels(view.channels);
  renderContent(view.content);
  renderCompliance(view.compliance);
  renderChart(view.effect_forecast);
}

function renderSegments(segments) {
  els.segments.innerHTML = segments.map(segment => `
    <div class="row">
      <div><strong>${segment.name}</strong><p>${segment.reasons.join(" / ")}</p></div>
      <span class="pill">${segment.size.toLocaleString()} 人 · ${segment.conversion_rate}%</span>
    </div>
  `).join("");
}

function renderChannels(channels) {
  els.channels.innerHTML = channels.map(channel => `
    <div class="row">
      <div><strong>${channel.channel}</strong><p>${channel.role}，预计触达 ${channel.expected_reach.toLocaleString()} 人</p></div>
      <span class="pill">${Math.round(channel.budget_share * 100)}%</span>
    </div>
  `).join("");
}

function renderContent(content) {
  const labels = {app_popup: "App 弹窗", sms: "短信", wechat: "企微话术", explain: "生成依据"};
  els.content.innerHTML = Object.entries(content).map(([key, value]) => `
    <div class="copy-item"><b>${labels[key] || key}</b><span>${value}</span></div>
  `).join("");
}

function renderCompliance(items) {
  els.compliance.innerHTML = items.map(item => `
    <div class="row"><div><strong>${item.item}</strong><p>${item.detail}</p></div><span class="pill">${item.status}</span></div>
  `).join("");
}

function renderChart(effect) {
  const rows = [["点击率", effect.ctr, "%", 36], ["预计转化率", effect.conversion, "%", 92], ["退订风险", effect.unsubscribe, "%", 148]];
  const maxValues = {"点击率": 20, "预计转化率": 8, "退订风险": 5};
  els.chart.innerHTML = rows.map(([label, value, unit, y]) => {
    const width = Math.max(8, Math.min(330, value / maxValues[label] * 330));
    return `<text class="chart-muted" x="18" y="${y + 16}">${label}</text>
      <rect class="bar-bg" x="118" y="${y}" width="300" height="18" rx="3"></rect>
      <rect class="bar" x="118" y="${y}" width="${width}" height="18" rx="3"></rect>
      <text class="chart-text" x="${Math.min(430, 128 + width)}" y="${y + 15}">${value}${unit}</text>`;
  }).join("");
}

els.generate.addEventListener("click", generateStrategy);
els.publish.addEventListener("click", publishPlan);

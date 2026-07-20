const els = {
  goal: document.getElementById("goalInput"),
  campaign: document.getElementById("campaignInput"),
  product: document.getElementById("productInput"),
  channel: document.getElementById("channelInput"),
  budget: document.getElementById("budgetInput"),
  risk: document.getElementById("riskInput"),
  freq: document.getElementById("freqInput"),
  generate: document.getElementById("generateBtn"),
  optimize: document.getElementById("optimizeBtn"),
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

async function generatePlan() {
  els.status.textContent = "正在生成";
  els.generate.disabled = true;
  try {
    const request = await parseGoalWithLlm();
    request.goal_parsed = true;
    const response = await fetch("/api/strategy/generate/real-data", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(request),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "生成失败");
    renderPlan(data.plan || data);
    currentCampaignId = (data.plan || data).campaign_id;
    els.publish.disabled = !currentCampaignId;
    els.publishedStatus.textContent = "草稿待发布";
  } catch (error) {
    els.status.textContent = error.message;
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

async function optimizeStrategy() {
  els.optimize.disabled = true;
  els.optimizationStatus.textContent = "正在计算候选价值";
  try {
    const response = await fetch("/api/strategy/optimize/real-data", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        campaign_id: els.campaign.value,
        budget: Number(els.budget.value) * 10000,
        customer_limit: 200,
        selected_sample_limit: 10,
        evaluation_time: "2026-07-17 12:00:00",
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "价值优化失败");
    renderOptimization(data);
    currentCampaignId = data.strategy_draft.campaign_id;
    els.publish.disabled = false;
    els.publishedStatus.textContent = "优化草稿待发布";
    els.optimizationStatus.textContent = "优化草稿已生成";
  } catch (error) {
    els.optimizationStatus.textContent = error.message;
  } finally {
    els.optimize.disabled = false;
  }
}

async function parseGoalWithLlm() {
  const response = await fetch("/api/strategy/parse-goal", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      goal: els.goal.value,
      product: els.product.value,
      product_locked: true,
      channel_mode: els.channel.value,
      budget_wan: Number(els.budget.value),
      risk_level: Number(els.risk.value),
      frequency_level: Number(els.freq.value),
    }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Goal parsing failed");
  const request = data.campaign_request;
  request.product_locked = true;
  els.channel.value = request.channel_mode;
  els.budget.value = request.budget_wan;
  els.risk.value = request.risk_level;
  els.freq.value = request.frequency_level;
  els.status.textContent = data.source === "deepseek" ? "DeepSeek parsed" : "Rule fallback";
  return request;
}

function renderPlan(plan) {
  els.campaignId.textContent = plan.campaign_id;
  els.audience.textContent = `${plan.audience_size.toLocaleString()} 人`;
  els.uplift.textContent = `+${plan.predicted_uplift}%`;
  els.roi.textContent = `${plan.predicted_roi}x`;
  els.riskMetric.textContent = `${plan.effect_forecast.complaint}%`;
  renderAudienceFunnel(plan.audience_funnel, plan.eligibility_summary);
  renderSegments(plan.segments);
  renderChannels(plan.channels);
  renderContent(plan.content);
  renderCompliance(plan.compliance);
  renderChart(plan.effect_forecast);
}

function renderAudienceFunnel(funnel = {}, eligibility = {}) {
  const input = eligibility.eligible_count ?? funnel.input_customer_count;
  const matched = funnel.product_matched_count;
  const selected = funnel.budget_selected_count;
  if (!input || !matched || !selected) return;
  els.status.textContent = `合规可投 ${input.toLocaleString()} 人，产品匹配 ${matched.toLocaleString()} 人，预算入选 ${selected.toLocaleString()} 人`;
}

function renderSegments(segments) {
  els.segments.innerHTML = segments.map(segment => `
    <div class="row">
      <div>
        <strong>${segment.name}</strong>
        <p>${segment.reasons.join(" / ")}</p>
      </div>
      <span class="pill">${segment.size}人 · ${segment.conversion_rate}%</span>
    </div>
  `).join("");
}

function renderChannels(channels) {
  els.channels.innerHTML = channels.map(channel => `
    <div class="row">
      <div>
        <strong>${channel.channel}</strong>
        <p>${channel.role}，预计触达 ${channel.expected_reach.toLocaleString()} 人</p>
      </div>
      <span class="pill">${Math.round(channel.budget_share * 100)}%</span>
    </div>
  `).join("");
}

function renderContent(content) {
  const labels = {
    app_popup: "App 弹窗",
    sms: "短信",
    wechat: "企微话术",
    explain: "生成依据",
  };
  els.content.innerHTML = Object.entries(content).map(([key, value]) => `
    <div class="copy-item">
      <b>${labels[key] || key}</b>
      <span>${value}</span>
    </div>
  `).join("");
}

function renderCompliance(items) {
  els.compliance.innerHTML = items.map(item => `
    <div class="row">
      <div>
        <strong>${item.item}</strong>
        <p>${item.detail}</p>
      </div>
      <span class="pill">${item.status}</span>
    </div>
  `).join("");
}

function renderChart(effect) {
  const rows = [
    ["点击率", effect.ctr, "%", 36],
    ["转化率", effect.conversion, "%", 92],
    ["投诉率", effect.complaint, "%", 148],
  ];
  const maxValues = {"点击率": 20, "转化率": 8, "投诉率": 0.3};
  els.chart.innerHTML = rows.map(([label, value, unit, y]) => {
    const width = Math.max(8, Math.min(330, value / maxValues[label] * 330));
    return `
      <text class="chart-muted" x="18" y="${y + 16}">${label}</text>
      <rect class="bar-bg" x="88" y="${y}" width="330" height="18" rx="3"></rect>
      <rect class="bar" x="88" y="${y}" width="${width}" height="18" rx="3"></rect>
      <text class="chart-text" x="${Math.min(430, 98 + width)}" y="${y + 15}">${value}${unit}</text>
    `;
  }).join("");
}

function renderOptimization(data) {
  const summary = data.selection_summary;
  els.optimizationSummary.textContent =
    `选中 ${summary.selected_candidate_count} 人，使用预算 ${summary.budget_used.toFixed(2)} 元，` +
    `预计净价值 ${summary.expected_net_value.toFixed(2)} 元，预计转化 ${summary.expected_conversion_count.toFixed(2)} 人`;
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
  }).join("") || "<p>当前预算下没有正向价值候选</p>";
}

els.generate.addEventListener("click", generatePlan);
els.publish.addEventListener("click", publishPlan);
els.optimize.addEventListener("click", optimizeStrategy);
generatePlan();

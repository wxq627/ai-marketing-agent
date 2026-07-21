const els = {
  goal: document.getElementById("goalInput"),
  parseGoal: document.getElementById("parseGoalBtn"),
  acceptSuggestion: document.getElementById("acceptSuggestionBtn"),
  manualMode: document.getElementById("manualModeBtn"),
  parseSource: document.getElementById("parseSource"),
  parseSummary: document.getElementById("parseSummary"),
  parsedTags: document.getElementById("parsedTags"),
  campaign: document.getElementById("campaignInput"),
  budget: document.getElementById("budgetInput"),
  targetSegment: document.getElementById("targetSegmentInput"),
  channelMode: document.getElementById("channelModeInput"),
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

const configControls = document.querySelectorAll("[data-config-control]");
const segmentLabels = {
  auto: "自动圈选",
  high_value: "高价值客户",
  high_intent: "高意图客户",
  dormant: "沉睡待唤醒客户",
  young_new: "年轻或新户客户",
};
const channelLabels = {
  omni: "智能全渠道",
  app: "仅 App Push",
  sms: "仅短信",
  wechat: "仅微信公众号",
};

let currentCampaignId = "";
let pendingSuggestion = null;
let configurationReady = false;
let parsingGoal = false;

function setConfigurationEditable(enabled) {
  configControls.forEach(control => { control.disabled = !enabled; });
  configurationReady = enabled;
}

async function parseGoal() {
  if (parsingGoal) return;
  const goal = els.goal.value.trim();
  if (!goal) {
    els.status.textContent = "请先输入运营目标";
    return;
  }
  parsingGoal = true;
  els.parseGoal.disabled = true;
  els.parseSource.textContent = "解析中";
  els.parseSummary.textContent = "正在提取活动、预算、目标客群和渠道约束。";
  try {
    const response = await fetch("/api/strategy/parse-goal", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        goal,
        campaign_id: els.campaign.value,
        budget_wan: Number(els.budget.value),
        channel_mode: els.channelMode.value,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "运营意图解析失败");
    pendingSuggestion = data;
    renderSuggestion(data);
    els.acceptSuggestion.disabled = false;
    els.status.textContent = "AI 建议已生成，请确认或自行调整";
  } catch (error) {
    els.parseSource.textContent = "解析失败";
    els.parseSummary.textContent = error.message;
  } finally {
    els.parseGoal.disabled = false;
    parsingGoal = false;
  }
}

function renderSuggestion(data) {
  const request = data.campaign_request;
  const sourceLabel = data.source === "deepseek" ? "DeepSeek 解析" : "本地规则解析";
  els.parseSource.textContent = sourceLabel;
  els.parseSummary.textContent = data.source === "deepseek"
    ? "AI 已生成以下可执行建议，仍需运营确认。"
    : data.fallback_reason === "api_key_not_configured"
      ? "在线模型未配置：请在 .env 中设置 DEEPSEEK_API_KEY 后重新解析。"
      : "在线模型暂不可用，已按本地规则生成建议，仍可手工调整。";
  const tags = [
    `预算 ${request.budget_wan} 万元`,
    `活动 ${data.suggested_campaign_id || "待选择"}`,
    `客群 ${segmentLabels[data.suggested_target_segment] || "自动圈选"}`,
    `渠道 ${channelLabels[request.channel_mode] || request.channel_mode}`,
    ...data.audience_hints.slice(0, 2),
  ];
  els.parsedTags.innerHTML = tags.map(tag => `<span>${tag}</span>`).join("");
}

function acceptSuggestion() {
  if (!pendingSuggestion) return;
  const request = pendingSuggestion.campaign_request;
  if (pendingSuggestion.suggested_campaign_id) els.campaign.value = pendingSuggestion.suggested_campaign_id;
  els.budget.value = request.budget_wan;
  els.targetSegment.value = pendingSuggestion.suggested_target_segment || "auto";
  els.channelMode.value = request.channel_mode || "omni";
  setConfigurationEditable(true);
  els.status.textContent = "已填入 AI 建议，可微调后生成策略";
}

function useManualMode() {
  setConfigurationEditable(true);
  els.acceptSuggestion.disabled = true;
  els.parseSource.textContent = "手工设置";
  els.parseSummary.textContent = "请在下方选择活动、预算、目标客群和投放渠道。";
  els.parsedTags.replaceChildren();
  els.status.textContent = "已切换为手工设置";
}

async function generateStrategy() {
  if (!configurationReady) {
    els.status.textContent = "请先确认 AI 建议，或选择自行填写";
    return;
  }
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
        target_segment: els.targetSegment.value,
        channel_mode: els.channelMode.value,
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
  const constraints = data.operator_constraints || {};
  els.optimizationSummary.textContent =
    `在 ${segmentLabels[constraints.target_segment] || "自动圈选"}、${channelLabels[constraints.channel_mode] || "智能全渠道"} 约束下，` +
    `从 ${summary.scored_candidate_count.toLocaleString()} 条合规候选中选中 ${summary.selected_candidate_count.toLocaleString()} 人，` +
    `使用预算 ${summary.budget_used.toFixed(2)} 元，预计净价值 ${summary.expected_net_value.toFixed(2)} 元，` +
    `预计转化 ${summary.expected_conversion_count.toFixed(2)} 人。`;
  els.selectedCandidates.innerHTML = data.selected_candidate_sample.map(item => `
    <div class="row">
      <div>
        <strong>${item.product_name}</strong>
        <p>客户唯一 ID：${item.customer_unique_id || item.oneid} · ${item.channel} · 转化概率 ${(item.model_scores.probabilities.p_conversion * 100).toFixed(1)}%</p>
      </div>
      <span class="pill">净价值 ${item.strategy_value.expected_net_value.toFixed(1)}</span>
    </div>
  `).join("") || "<p>当前约束下没有正向净价值候选。</p>";
}

function renderStrategyView(view, campaignId) {
  const metrics = view.metrics;
  els.campaignId.textContent = campaignId;
  els.audience.textContent = `${metrics.audience_size.toLocaleString()} 人`;
  els.uplift.textContent = `${metrics.conversion_rate}%`;
  els.roi.textContent = `${metrics.expected_net_value_wan} 万元`;
  els.riskMetric.textContent = `${metrics.budget_utilization}%`;
  renderSegments(view.segments);
  renderChannels(view.channels);
  renderContent(view.content);
  renderCompliance(view.compliance);
  renderChart(view.effect_forecast);
}

function renderSegments(segments) {
  els.segments.innerHTML = segments.map(segment => `
    <div class="row"><div><strong>${segment.name}</strong><p>${segment.reasons.join(" / ")}</p></div><span class="pill">${segment.size.toLocaleString()} 人 · ${segment.conversion_rate}%</span></div>
  `).join("");
}

function renderChannels(channels) {
  els.channels.innerHTML = channels.map(channel => `
    <div class="row"><div><strong>${channel.channel}</strong><p>${channel.role}，预计触达 ${channel.expected_reach.toLocaleString()} 人</p></div><span class="pill">${Math.round(channel.budget_share * 100)}%</span></div>
  `).join("");
}

function renderContent(content) {
  const labels = {app_popup: "App 弹窗", sms: "短信", wechat: "微信话术", explain: "生成依据"};
  els.content.innerHTML = Object.entries(content).map(([key, value]) => `<div class="copy-item"><b>${labels[key] || key}</b><span>${value}</span></div>`).join("");
}

function renderCompliance(items) {
  els.compliance.innerHTML = items.map(item => `<div class="row"><div><strong>${item.item}</strong><p>${item.detail}</p></div><span class="pill">${item.status}</span></div>`).join("");
}

function renderChart(effect) {
  const rows = [["点击率", effect.ctr, "%", 36], ["预计转化率", effect.conversion, "%", 92], ["退订风险", effect.unsubscribe, "%", 148]];
  const maxValues = {"点击率": 20, "预计转化率": 8, "退订风险": 5};
  els.chart.innerHTML = rows.map(([label, value, unit, y]) => {
    const width = Math.max(8, Math.min(330, value / maxValues[label] * 330));
    return `<text class="chart-muted" x="18" y="${y + 16}">${label}</text><rect class="bar-bg" x="118" y="${y}" width="300" height="18" rx="3"></rect><rect class="bar" x="118" y="${y}" width="${width}" height="18" rx="3"></rect><text class="chart-text" x="${Math.min(430, 128 + width)}" y="${y + 15}">${value}${unit}</text>`;
  }).join("");
}

window.parseGoalFromUi = parseGoal;
els.parseGoal.addEventListener("click", parseGoal);
els.goal.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    parseGoal();
  }
});
els.acceptSuggestion.addEventListener("click", acceptSuggestion);
els.manualMode.addEventListener("click", useManualMode);
els.generate.addEventListener("click", generateStrategy);
els.publish.addEventListener("click", publishPlan);
loadCampaignOptions();

async function loadCampaignOptions() {
  try {
    const response = await fetch("/api/strategy/campaigns");
    const data = await response.json();
    if (!response.ok || !Array.isArray(data.items)) return;
    const selectedCampaign = els.campaign.value;
    els.campaign.replaceChildren();
    data.items.forEach(item => {
      const option = document.createElement("option");
      option.value = item.campaign_id;
      option.textContent = item.label;
      els.campaign.append(option);
    });
    els.campaign.value = data.items.some(item => item.campaign_id === selectedCampaign)
      ? selectedCampaign
      : data.items[0]?.campaign_id || "";
  } catch (_error) {
    // Keep the bundled fallback options when the local service is unavailable.
  }
}

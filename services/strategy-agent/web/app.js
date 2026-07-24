const els = {
  goal: document.getElementById("goalInput"),
  parseGoal: document.getElementById("parseGoalBtn"),
  manualMode: document.getElementById("manualModeBtn"),
  acceptSuggestion: document.getElementById("acceptSuggestionBtn"),
  recheck: document.getElementById("recheckBtn"),
  parseSource: document.getElementById("parseSource"),
  parseSummary: document.getElementById("parseSummary"),
  parsedTags: document.getElementById("parsedTags"),
  advice: document.getElementById("copilotAdvice"),
  questionComposer: document.getElementById("questionComposer"),
  questionContext: document.getElementById("questionContext"),
  question: document.getElementById("questionInput"),
  askQuestion: document.getElementById("askQuestionBtn"),
  followUps: document.getElementById("followUpList"),
  campaign: document.getElementById("campaignInput"),
  budget: document.getElementById("budgetInput"),
  audienceCheckGroup: document.getElementById("audienceCheckGroup"),
  toggleOperatorFilters: document.getElementById("toggleOperatorFiltersBtn"),
  operatorFilterPanel: document.getElementById("operatorFilterPanel"),
  operatorFilterTags: document.getElementById("operatorFilterTags"),
  cityCheckGroup: document.getElementById("cityCheckGroup"),
  filterGender: document.getElementById("filterGenderInput"),
  filterAgeMin: document.getElementById("filterAgeMinInput"),
  filterAgeMax: document.getElementById("filterAgeMaxInput"),
  filterSpendMin: document.getElementById("filterSpendMinInput"),
  valueLevelCheckGroup: document.getElementById("valueLevelCheckGroup"),
  lifecycleCheckGroup: document.getElementById("lifecycleCheckGroup"),
  riskLevelCheckGroup: document.getElementById("riskLevelCheckGroup"),
  behaviorCheckGroup: document.getElementById("behaviorCheckGroup"),
  channelCheckGroup: document.getElementById("channelCheckGroup"),
  channelCoverageTrial: document.getElementById("channelCoverageTrialInput"),
  draftContent: document.getElementById("draftContentBtn"),
  contentTabs: document.getElementById("contentTabs"),
  copy: document.getElementById("channelCopyInput"),
  copyStatus: document.getElementById("copyStatus"),
  generate: document.getElementById("generateBtn"),
  publish: document.getElementById("publishBtn"),
  publishedStatus: document.getElementById("publishedStatus"),
  status: document.getElementById("statusText"),
  campaignId: document.getElementById("campaignId"),
  audience: document.getElementById("audienceMetric"),
  uplift: document.getElementById("upliftMetric"),
  roi: document.getElementById("roiMetric"),
  riskMetric: document.getElementById("riskMetric"),
  optimizationStatus: document.getElementById("optimizationStatus"),
  optimizationSummary: document.getElementById("optimizationSummary"),
  selectedCandidates: document.getElementById("selectedCandidates"),
  experimentStatus: document.getElementById("experimentStatus"),
  experimentSummary: document.getElementById("experimentSummary"),
  treatmentConversion: document.getElementById("treatmentConversionMetric"),
  controlConversion: document.getElementById("controlConversionMetric"),
  incrementalConversion: document.getElementById("incrementalConversionMetric"),
  incrementalValue: document.getElementById("incrementalValueMetric"),
  abTestRows: document.getElementById("abTestRows"),
  upliftModelNote: document.getElementById("upliftModelNote"),
  segments: document.getElementById("segments"),
  channels: document.getElementById("channels"),
  compliance: document.getElementById("compliance"),
  chart: document.getElementById("forecastChart"),
};

const configControls = document.querySelectorAll("[data-config-control]");
const segmentLabels = {
  auto: "自动圈选",
  high_value: "高价值客户",
  high_intent: "高意图客户",
  dormant: "沉睡待唤醒客户",
  young_new: "年轻或新户客户",
  high_activity: "高活跃客户",
  spend_growth: "消费增长客户",
  benefit_sensitive: "权益敏感客户",
  low_risk: "低风险可转化客户",
};
const channelLabels = {
  app: "App Push",
  app_push: "App Push",
  sms: "短信",
  wechat: "微信公众号",
  email: "邮件",
  phone: "电话外呼",
};

let pendingSuggestion = null;
let currentReview = {};
let currentContent = {};
let activeContentChannel = "app";
let activeQuestionSuggestion = "";
let acceptedAdvice = [];
let configurationReady = false;
let currentCampaignId = "";

function selectedChannels() {
  return Array.from(els.channelCheckGroup.querySelectorAll("input:checked"))
    .map(input => input.value)
    .sort();
}

function normalizeTargetSegments(value) {
  const values = Array.isArray(value) ? value : [value];
  const normalized = values
    .map(item => String(item || "").trim())
    .filter(item => item && item !== "auto");
  return [...new Set(normalized)];
}

function selectedTargetSegments() {
  return Array.from(els.audienceCheckGroup.querySelectorAll("input:checked"))
    .map(input => input.value)
    .sort();
}

function getOperatorFilters() {
  const ageMin = els.filterAgeMin.value === "" ? null : Number(els.filterAgeMin.value);
  const ageMax = els.filterAgeMax.value === "" ? null : Number(els.filterAgeMax.value);
  const spendMin = els.filterSpendMin.value === "" ? null : Number(els.filterSpendMin.value);
  return {
    cities: selectedCities(),
    gender: els.filterGender.value,
    age_min: Number.isFinite(ageMin) ? ageMin : null,
    age_max: Number.isFinite(ageMax) ? ageMax : null,
    monthly_spend_min: Number.isFinite(spendMin) ? spendMin : null,
    value_levels: selectedValues(els.valueLevelCheckGroup),
    lifecycle_stages: selectedValues(els.lifecycleCheckGroup),
    risk_levels: selectedValues(els.riskLevelCheckGroup),
    recent_behaviors: Array.from(els.behaviorCheckGroup.querySelectorAll("input:checked")).map(input => input.value),
  };
}

function selectedValues(group) {
  return Array.from(group.querySelectorAll("input:checked")).map(input => input.value).sort();
}

function selectedCities() {
  return Array.from(els.cityCheckGroup.querySelectorAll("input:checked"))
    .map(input => input.value)
    .sort();
}

function hasOperatorFilters(filters = getOperatorFilters()) {
  return Boolean(
    filters.cities.length || filters.gender || filters.age_min !== null || filters.age_max !== null
    || filters.monthly_spend_min !== null || filters.value_levels.length || filters.lifecycle_stages.length
    || filters.risk_levels.length || filters.recent_behaviors.length,
  );
}

function renderOperatorFilterTags() {
  const filters = getOperatorFilters();
  const behaviorLabels = {
    dining: "餐饮消费", entertainment: "娱乐/观影", shopping: "购物消费", benefit: "权益/优惠互动",
    travel: "出行相关", installment: "分期/还款", credit_upgrade: "额度/升级",
  };
  const valueLabels = {high: "高价值", medium: "中价值", low: "长尾价值"};
  const riskLabels = {low: "低风险", medium: "中风险"};
  const tags = [
    ...filters.cities.map(city => ({key: `city:${city}`, label: `城市：${city}`})),
    ...(filters.gender ? [{key: "gender", label: `性别：${filters.gender === "female" ? "女性" : "男性"}`}] : []),
    ...((filters.age_min !== null || filters.age_max !== null) ? [{key: "age", label: `年龄：${filters.age_min ?? "不限"}-${filters.age_max ?? "不限"}`} ] : []),
    ...(filters.monthly_spend_min !== null ? [{key: "spend", label: `月均消费：≥${filters.monthly_spend_min} 元`}] : []),
    ...filters.value_levels.map(value => ({key: `value:${value}`, label: `价值：${valueLabels[value] || value}`})),
    ...filters.lifecycle_stages.map(value => ({key: `lifecycle:${value}`, label: `生命周期：${value}`})),
    ...filters.risk_levels.map(value => ({key: `risk:${value}`, label: `风险：${riskLabels[value] || value}`})),
    ...filters.recent_behaviors.map(behavior => ({key: `behavior:${behavior}`, label: `近期：${behaviorLabels[behavior] || behavior}`})),
  ];
  els.operatorFilterTags.innerHTML = tags.length
    ? tags.map(tag => `<button type="button" class="operator-filter-tag" data-filter-key="${escapeAttribute(tag.key)}">${escapeHtml(tag.label)} <span aria-hidden="true">×</span></button>`).join("")
    : '<span class="filter-empty">未添加额外条件</span>';
}

function clearOperatorFilter(key) {
  if (key.startsWith("city:")) {
    const input = els.cityCheckGroup.querySelector(`input[value="${key.slice(5)}"]`);
    if (input) input.checked = false;
  }
  if (key === "gender") els.filterGender.value = "";
  if (key === "age") { els.filterAgeMin.value = ""; els.filterAgeMax.value = ""; }
  if (key === "spend") els.filterSpendMin.value = "";
  if (key.startsWith("value:")) {
    const input = els.valueLevelCheckGroup.querySelector(`input[value="${key.slice(6)}"]`);
    if (input) input.checked = false;
  }
  if (key.startsWith("lifecycle:")) {
    const input = els.lifecycleCheckGroup.querySelector(`input[value="${key.slice(10)}"]`);
    if (input) input.checked = false;
  }
  if (key.startsWith("risk:")) {
    const input = els.riskLevelCheckGroup.querySelector(`input[value="${key.slice(5)}"]`);
    if (input) input.checked = false;
  }
  if (key.startsWith("behavior:")) {
    const input = els.behaviorCheckGroup.querySelector(`input[value="${key.slice(9)}"]`);
    if (input) input.checked = false;
  }
  renderOperatorFilterTags();
}

function setOperatorFilters(filters = {}) {
  const cities = Array.isArray(filters.cities) ? filters.cities : [];
  const selectedCities = new Set(cities);
  els.cityCheckGroup.querySelectorAll("input").forEach(input => { input.checked = selectedCities.has(input.value); });
  els.filterGender.value = filters.gender || "";
  els.filterAgeMin.value = filters.age_min ?? "";
  els.filterAgeMax.value = filters.age_max ?? "";
  els.filterSpendMin.value = filters.monthly_spend_min ?? "";
  setCheckboxGroup(els.valueLevelCheckGroup, filters.value_levels || []);
  setCheckboxGroup(els.lifecycleCheckGroup, filters.lifecycle_stages || []);
  setCheckboxGroup(els.riskLevelCheckGroup, filters.risk_levels || []);
  const behaviors = new Set(filters.recent_behaviors || []);
  els.behaviorCheckGroup.querySelectorAll("input").forEach(input => { input.checked = behaviors.has(input.value); });
  renderOperatorFilterTags();
}

function setCheckboxGroup(group, values) {
  const selected = new Set(values);
  group.querySelectorAll("input").forEach(input => { input.checked = selected.has(input.value); });
}

function inferOperatorFiltersFromGoal(goal) {
  const filters = getOperatorFilters();
  const cities = Array.from(els.cityCheckGroup.querySelectorAll("input")).map(input => input.value);
  const mentionedCities = cities.filter(city => goal.includes(city));
  if (mentionedCities.length) filters.cities = mentionedCities;
  if (/女性|女士|女客户/.test(goal)) filters.gender = "female";
  if (/男性|男士|男客户/.test(goal)) filters.gender = "male";
  const age = goal.match(/(\d{1,2})\s*(?:到|至|[-~—])\s*(\d{1,2})\s*岁/);
  if (age) { filters.age_min = Number(age[1]); filters.age_max = Number(age[2]); }
  const spend = goal.match(/(?:月均消费|月消费|消费)不低于?\s*(\d{3,6})/);
  if (spend) filters.monthly_spend_min = Number(spend[1]);
  if (/高价值|高净值|高消费/.test(goal)) filters.value_levels = ["high"];
  if (/中价值/.test(goal)) filters.value_levels = ["medium"];
  if (/新户/.test(goal)) filters.lifecycle_stages = ["新户"];
  if (/沉睡|唤醒/.test(goal)) filters.lifecycle_stages = ["沉睡期"];
  if (/低风险/.test(goal)) filters.risk_levels = ["low"];
  if (/中风险/.test(goal)) filters.risk_levels = ["medium"];
  const behaviorKeywords = {
    dining: /餐饮|美食|餐厅|外卖/,
    entertainment: /娱乐|观影|电影|演出|音乐会/,
    shopping: /购物|商超|电商|商城/,
    benefit: /权益|优惠|券|返现/,
    travel: /出行|旅行|旅游|机票|酒店/,
    installment: /分期|借贷|还款/,
    credit_upgrade: /提额|额度|升级/,
  };
  filters.recent_behaviors = Object.entries(behaviorKeywords).filter(([, pattern]) => pattern.test(goal)).map(([name]) => name);
  return filters;
}

function targetSegmentsLabel(segments) {
  const selected = normalizeTargetSegments(segments);
  return selected.length
    ? selected.map(segment => segmentLabels[segment] || "目标客群").join(" + ")
    : "自动圈选";
}

function setTargetSegmentCheckboxes(segments) {
  const selected = new Set(normalizeTargetSegments(segments));
  els.audienceCheckGroup.querySelectorAll("input").forEach(input => {
    input.checked = selected.has(input.value);
  });
}

function getChannelMode() {
  const channels = selectedChannels();
  return channels.length ? channels.join("_") : "omni";
}

function channelLabel(mode) {
  if (!mode || mode === "omni") return "智能全渠道";
  return mode.split("_").map(channel => channelLabels[channel] || channel).join(" + ");
}

function setChannelCheckboxes(mode) {
  const selected = new Set(mode && mode !== "omni" ? mode.split("_") : []);
  els.channelCheckGroup.querySelectorAll("input").forEach(input => {
    input.checked = selected.has(input.value);
  });
}

function getConfiguration(overrides = {}) {
  const selected = els.campaign.options[els.campaign.selectedIndex];
  const targetSegments = normalizeTargetSegments(
    overrides.target_segments ?? overrides.target_segment ?? selectedTargetSegments(),
  );
  return {
    campaign_id: overrides.campaign_id ?? els.campaign.value,
    campaign_name: overrides.campaign_name ?? selected?.textContent ?? els.campaign.value,
    budget_wan: Number(overrides.budget_wan ?? els.budget.value),
    target_segment: targetSegments[0] || "auto",
    target_segments: targetSegments,
    operator_filters: overrides.operator_filters ?? getOperatorFilters(),
    channel_mode: overrides.channel_mode ?? getChannelMode(),
    channel_coverage_trial: overrides.channel_coverage_trial ?? els.channelCoverageTrial.checked,
    operator_goal: overrides.operator_goal ?? els.goal.value.trim(),
  };
}

function setConfigurationEditable(enabled) {
  configControls.forEach(control => {
    if (["DIV", "SPAN"].includes(control.tagName)) {
      control.querySelectorAll("input, select, textarea, button").forEach(input => { input.disabled = !enabled; });
    } else {
      control.disabled = !enabled;
    }
  });
  els.draftContent.disabled = !enabled;
  els.contentTabs.querySelectorAll("button").forEach(button => { button.disabled = !enabled; });
  configurationReady = enabled;
}

function renderParsedTags(configuration, hints = []) {
  const tags = [
    `预算 ${configuration.budget_wan} 万元`,
    `活动 ${configuration.campaign_name || configuration.campaign_id || "待确认"}`,
    `客群 ${targetSegmentsLabel(configuration.target_segments || configuration.target_segment)}`,
    `渠道 ${channelLabel(configuration.channel_mode)}`,
    ...hints.slice(0, 2),
  ];
  els.parsedTags.innerHTML = tags.map(tag => `<span>${escapeHtml(tag)}</span>`).join("");
}

async function parseGoal() {
  const goal = els.goal.value.trim();
  if (!goal) {
    els.status.textContent = "请先输入运营目标";
    return;
  }
  els.parseGoal.disabled = true;
  els.parseSource.textContent = "AI 分析中";
  els.parseSummary.textContent = "正在理解目标，并检查渠道成本、客群约束与可补充的决策信息。";
  try {
    const response = await postJson("/api/strategy/parse-goal", {
      goal,
      campaign_id: els.campaign.value,
      budget_wan: Number(els.budget.value),
      channel_mode: getChannelMode(),
    });
    pendingSuggestion = response;
    const request = response.campaign_request;
    const configuration = getConfiguration({
      campaign_id: response.suggested_campaign_id || els.campaign.value,
      budget_wan: request.budget_wan,
      target_segments: normalizeTargetSegments(response.suggested_target_segments || response.suggested_target_segment),
      channel_mode: request.channel_mode,
    });
    configuration.campaign_name = campaignName(configuration.campaign_id);
    renderParsedTags(configuration, response.audience_hints || []);
    await requestCopilotReview(configuration, goal, response.source);
    els.acceptSuggestion.disabled = false;
    els.status.textContent = "AI 已完成目标理解和策略预审，请查看建议后确认或调整。";
  } catch (error) {
    els.parseSource.textContent = "分析失败";
    els.parseSummary.textContent = error.message;
    els.status.textContent = error.message;
  } finally {
    els.parseGoal.disabled = false;
  }
}

async function requestCopilotReview(configuration = getConfiguration(), goal = els.goal.value.trim(), parseSource = "") {
  els.recheck.disabled = true;
  try {
    const review = await postJson("/api/strategy/copilot/review", {goal, ...configuration});
    currentReview = review;
    currentReview.accepted_advice = acceptedAdvice;
    renderReview(review, parseSource);
    els.recheck.disabled = !configurationReady;
  } catch (error) {
    els.parseSummary.textContent = `AI 预审暂不可用：${error.message}`;
    els.recheck.disabled = !configurationReady;
  }
}

function renderReview(review, parseSource = "") {
  const source = review.source === "deepseek" ? "DeepSeek 策略建议" : "规则策略建议";
  els.parseSource.textContent = parseSource === "deepseek" ? "DeepSeek 已理解目标" : source;
  els.parseSummary.textContent = review.summary || "AI 已完成策略预审。";
  const adviceMeta = {
    opportunity: {badge: "分析参考", action: "acknowledge", actionText: "标记已阅"},
    risk: {badge: "需关注", action: "acknowledge", actionText: "标记已阅"},
    question: {badge: "运营待确认", action: "configure", actionText: "去补充配置"},
    action: {badge: "可执行动作", action: "configure", actionText: "去调整配置"},
  };
  const sections = [
    ["风险", "risk", review.risks || []],
    ["建议动作", "action", review.actions || []],
    ["待确认", "question", review.pending_questions || []],
    ["分析参考", "opportunity", review.opportunities || []],
  ];
  const cards = sections.flatMap(([label, type, items]) => items.slice(0, 1).map(item => ({label, type, item}))).slice(0, 3);
  els.advice.innerHTML = cards.map(({label, type, item}) => {
    const meta = adviceMeta[type];
    return `
    <article class="advice-item" data-advice="${escapeAttribute(item)}">
      <header><span class="advice-type">${label}</span><span class="evidence-mark">${meta.badge}</span></header>
      <p>${escapeHtml(item)}</p>
      <div class="advice-actions">
        <button class="accept-advice" type="button" data-action="${meta.action}">${meta.actionText}</button>
        <button class="ask-advice" type="button" data-action="ask">追问</button>
      </div>
    </article>
  `;
  }).join("") || "<p class=\"empty-state\">AI 未返回具体建议，可继续手动配置并重新评估。</p>";
  els.advice.querySelectorAll("[data-action]").forEach(button => {
    button.addEventListener("click", () => {
      const card = button.closest(".advice-item");
      const advice = card?.dataset.advice || "";
      if (button.dataset.action === "acknowledge") markAdviceAcknowledged(advice, button);
      if (button.dataset.action === "configure") openConfigurationForAdvice(advice);
      if (button.dataset.action === "ask") openQuestion(advice);
    });
  });
}

function markAdviceAcknowledged(advice, button) {
  if (advice && !acceptedAdvice.includes(advice)) acceptedAdvice.push(advice);
  currentReview.accepted_advice = acceptedAdvice;
  button.replaceWith(Object.assign(document.createElement("span"), {className: "accepted", textContent: "已阅"}));
}

function openConfigurationForAdvice(advice) {
  if (pendingSuggestion && !configurationReady) acceptSuggestion();
  document.querySelector(".configuration-section")?.scrollIntoView({behavior: "smooth", block: "center"});
  els.status.textContent = advice
    ? "请结合这条 AI 提醒调整策略配置，完成后点击“AI 重新评估”。"
    : "请补充策略配置后点击“AI 重新评估”。";
}

function openQuestion(suggestion) {
  activeQuestionSuggestion = suggestion;
  els.questionComposer.hidden = false;
  els.questionContext.textContent = `围绕这条建议追问：${suggestion}`;
  els.question.focus();
}

async function askQuestion() {
  const question = els.question.value.trim();
  if (!question || !activeQuestionSuggestion) return;
  els.askQuestion.disabled = true;
  try {
    const answer = await postJson("/api/strategy/copilot/question", {
      ...getConfiguration(),
      question,
      suggestion: activeQuestionSuggestion,
    });
    els.followUps.insertAdjacentHTML("beforeend", `<article class="follow-up-item"><strong>AI 回答</strong><p>${escapeHtml(answer.answer)}</p></article>`);
    els.question.value = "";
  } catch (error) {
    els.status.textContent = `追问失败：${error.message}`;
  } finally {
    els.askQuestion.disabled = false;
  }
}

function acceptSuggestion() {
  if (!pendingSuggestion) return;
  const request = pendingSuggestion.campaign_request;
  const campaignId = pendingSuggestion.suggested_campaign_id || els.campaign.value;
  if (campaignId) els.campaign.value = campaignId;
  els.budget.value = request.budget_wan;
  setTargetSegmentCheckboxes(pendingSuggestion.suggested_target_segments || pendingSuggestion.suggested_target_segment);
  setChannelCheckboxes(request.channel_mode || "omni");
  setOperatorFilters(inferOperatorFiltersFromGoal(els.goal.value));
  setConfigurationEditable(true);
  els.recheck.disabled = false;
  els.status.textContent = "已填入 AI 建议。你可以调整配置、编辑内容或让 AI 重新评估。";
  updateContentContext();
}

function useManualMode() {
  setConfigurationEditable(true);
  els.recheck.disabled = false;
  els.status.textContent = "已进入手工配置模式。设置完成后可点击“AI 重新评估”。";
  updateContentContext();
}

async function recheckStrategy() {
  if (!configurationReady) return;
  els.status.textContent = "AI 正在基于最新配置重新评估。";
  await requestCopilotReview(getConfiguration(), els.goal.value.trim());
  els.status.textContent = "AI 已更新策略建议。";
}

function updateContentContext() {
  const channels = selectedChannels();
  if (channels.length && !channels.includes(activeContentChannel)) activeContentChannel = channels[0];
  renderContentEditor();
}

function renderContentEditor() {
  els.contentTabs.querySelectorAll("button").forEach(button => {
    button.classList.toggle("active", button.dataset.channel === activeContentChannel);
  });
  els.copy.value = currentContent[activeContentChannel] || "";
  els.copy.placeholder = `为${channelLabels[activeContentChannel]}维护可发布文案`;
}

async function draftContent() {
  if (!configurationReady) return;
  els.draftContent.disabled = true;
  els.copyStatus.textContent = "AI 正在生成渠道初稿";
  try {
    const response = await postJson("/api/strategy/copilot/content", getConfiguration());
    currentContent = {...currentContent, ...response.content};
    const channels = selectedChannels();
    if (channels.length) activeContentChannel = channels[0];
    renderContentEditor();
    els.copyStatus.textContent = response.source === "deepseek" ? "AI 初稿已生成，可直接修改" : "已生成本地初稿，可直接修改";
  } catch (error) {
    els.copyStatus.textContent = `文案生成失败：${error.message}`;
  } finally {
    els.draftContent.disabled = false;
  }
}

async function generateStrategy() {
  if (!configurationReady) {
    els.status.textContent = "请先采纳 AI 建议或进入手工配置模式。";
    return;
  }
  els.generate.disabled = true;
  els.optimizationStatus.textContent = "正在生成";
  els.status.textContent = "正在根据最终配置计算候选、预测响应并优化预算。";
  try {
    const data = await postJson("/api/strategy/optimize/real-data", {
      campaign_id: els.campaign.value,
      budget: Number(els.budget.value) * 10000,
      target_segment: selectedTargetSegments()[0] || "auto",
      target_segments: selectedTargetSegments(),
      operator_filters: getOperatorFilters(),
      channel_mode: getChannelMode(),
      channel_coverage_trial: els.channelCoverageTrial.checked,
      operator_content: selectedOperatorContent(),
      copilot_review: currentReview,
      selected_sample_limit: 10,
      evaluation_time: "2026-07-17 12:00:00",
    });
    renderOptimization(data);
    renderStrategyView(data.strategy_view, data.campaign_id);
    renderFeedbackSimulation(data.offline_feedback_simulation);
    currentCampaignId = data.strategy_draft.campaign_id;
    els.publish.disabled = false;
    els.publishedStatus.textContent = "策略草稿待发布";
    els.optimizationStatus.textContent = "策略已生成";
    els.status.textContent = "策略已生成，左侧运营文案与 AI 建议摘要已一并写入策略包。";
  } catch (error) {
    els.optimizationStatus.textContent = "生成失败";
    els.status.textContent = error.message;
  } finally {
    els.generate.disabled = false;
  }
}

function renderOptimization(data) {
  const summary = data.selection_summary;
  const constraints = data.operator_constraints || {};
  const coverage = summary.channel_coverage || {};
  const usesPdRiskModel = (data.selected_candidate_sample || []).some(
    item => item.strategy_value?.breakdown?.pd_source === "pd_risk_model",
  );
  const trial = coverage.enabled
    ? ` 覆盖试投：${Object.entries(coverage.trial_selected_counts || {}).map(([channel, count]) => `${channelLabels[channel] || channel} ${count} 人`).join("，")}。`
    : "";
  const riskMethod = usesPdRiskModel ? "已纳入 PD 风险评分" : "使用风险等级规则兜底";
  els.optimizationSummary.textContent = `在${targetSegmentsLabel(constraints.target_segments || constraints.target_segment)}、${channelLabel(constraints.channel_mode)}约束下，从${summary.scored_candidate_count.toLocaleString()}条合规候选中选中${summary.selected_candidate_count.toLocaleString()}人，使用预算${summary.budget_used.toFixed(2)}元，预计净价值${summary.expected_net_value.toFixed(2)}元，预计转化${summary.expected_conversion_count.toFixed(2)}人；${riskMethod}。${trial}`;
  els.selectedCandidates.innerHTML = data.selected_candidate_sample.map(item => {
    const breakdown = item.strategy_value?.breakdown || {};
    const pd = Number(breakdown.pd_6m);
    const creditExpectedLoss = Number(breakdown.credit_expected_loss || 0);
    const riskText = breakdown.pd_source === "pd_risk_model" && Number.isFinite(pd)
      ? ` · PD（未来6个月）${(pd * 100).toFixed(1)}% · 预期信用损失 ${creditExpectedLoss.toFixed(1)} 元`
      : " · 信用风险按风险等级估算";
    return `
      <div class="row"><div><strong>${escapeHtml(item.product_name)}</strong><p>客户唯一 ID：${escapeHtml(item.customer_unique_id || item.oneid)} · ${escapeHtml(item.kmeans_persona?.cluster_code || "KMeans 待分配")} · ${escapeHtml(channelLabels[item.channel] || item.channel)} · 转化概率 ${(item.model_scores.probabilities.p_conversion * 100).toFixed(1)}%${riskText}</p></div><span class="pill">净价值 ${item.strategy_value.expected_net_value.toFixed(1)}</span></div>
    `;
  }).join("") || "<p class=\"empty-state\">当前约束下没有正向净价值候选。</p>";
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
  renderCompliance(view.compliance);
  renderChart(view.effect_forecast);
}

function renderFeedbackSimulation(simulation) {
  if (!simulation?.groups || !simulation?.uplift) return;
  const treatment = simulation.groups.treatment || {};
  const control = simulation.groups.control || {};
  const uplift = simulation.uplift || {};
  const percentage = value => `${(Number(value || 0) * 100).toFixed(2)}%`;
  const currency = value => `${Number(value || 0).toLocaleString("zh-CN", {maximumFractionDigits: 0})} 元`;
  const count = value => Number(value || 0).toLocaleString("zh-CN", {maximumFractionDigits: 0});
  const estimatedConversionRate = group => group.conversion_rate_modeled ?? group.conversion_rate_smoothed ?? group.conversion_rate;
  const estimatedUplift = Number(uplift.modeled_group_incremental_conversion_rate ?? uplift.smoothed_incremental_conversion_rate ?? uplift.observed_incremental_conversion_rate ?? 0);
  const estimatedConversions = Number(uplift.modeled_group_incremental_conversions ?? uplift.smoothed_incremental_conversions ?? uplift.observed_incremental_conversions ?? 0);
  const estimatedRevenue = group => group.modeled_revenue_cny ?? group.revenue_cny;
  const estimatedCost = group => group.modeled_marketing_cost_cny ?? group.marketing_cost_cny;
  const estimatedNetValue = group => group.modeled_net_value_cny ?? group.net_value_cny;
  const estimatedIncrementalValue = Number(uplift.modeled_group_incremental_net_value_cny ?? uplift.incremental_net_value_cny ?? 0);

  const ratio = Math.round(Number(simulation.experiment?.control_ratio || 0.15) * 100);
  els.experimentStatus.textContent = "仿真反馈";
  els.experimentSummary.textContent = `按投放渠道与 KMeans 客群分层后，约 ${100 - ratio}% 进入策略组、${ratio}% 进入基线对照组；两组使用同一活动和触达节奏，对照组不使用个性化策略与定制文案。`;
  els.treatmentConversion.textContent = percentage(estimatedConversionRate(treatment));
  els.controlConversion.textContent = percentage(estimatedConversionRate(control));
  els.incrementalConversion.textContent = `${estimatedConversions.toFixed(1)} 人`;
  els.incrementalValue.textContent = currency(estimatedIncrementalValue);
  els.uplift.textContent = `${(estimatedUplift * 100).toFixed(2)} pp`;
  els.roi.textContent = currency(estimatedIncrementalValue);
  els.abTestRows.innerHTML = [
    ["最终策略组", treatment],
    ["基线触达对照组", control],
  ].map(([label, group]) => `
    <tr>
      <th scope="row">${label}</th>
      <td>${count(group.exposure_count)}</td>
      <td>${percentage(group.click_rate)}</td>
      <td>${percentage(estimatedConversionRate(group))}</td>
      <td>${currency(estimatedRevenue(group))}</td>
      <td>${currency(estimatedCost(group))}</td>
      <td>${currency(estimatedNetValue(group))}</td>
    </tr>
  `).join("");
  const reliable = uplift.statistical_reference_passed ? "统计参考通过" : "样本仍需继续积累";
  const smoothingHint = `转化、收益、成本和净价值均由同一批客户的逐人响应概率聚合得到；原始事件计数仍保留给真实反馈接入后的统计检验。`;
  els.upliftModelNote.textContent = `转化提升 = ${percentage(estimatedConversionRate(treatment))} − ${percentage(estimatedConversionRate(control))} = ${percentage(estimatedUplift)}。增量净收益按“策略组净价值 − 对照组人均净价值 × 策略组样本量”计算；95% 区间为 [${percentage(uplift.confidence_interval_low)}, ${percentage(uplift.confidence_interval_high)}]，${reliable}。${smoothingHint}`;
}

function renderSegments(segments) {
  els.segments.innerHTML = segments.map(segment => `<div class="row"><div><strong>${escapeHtml(segment.name)}</strong><p>${escapeHtml(segment.reasons.join(" / "))}</p></div><span class="pill">${segment.size.toLocaleString()} 人 · ${segment.conversion_rate}%</span></div>`).join("");
}

function renderChannels(channels) {
  els.channels.innerHTML = channels.map(channel => `<div class="row"><div><strong>${escapeHtml(channelLabels[channel.channel] || channel.channel)}</strong><p>${escapeHtml(channel.role)}，预计触达 ${channel.expected_reach.toLocaleString()} 人</p></div><span class="pill">${Math.round(channel.budget_share * 100)}%</span></div>`).join("");
}

function renderCompliance(items) {
  els.compliance.innerHTML = items.map(item => `<div class="row"><div><strong>${escapeHtml(item.item)}</strong><p>${escapeHtml(item.detail)}</p></div><span class="pill">${escapeHtml(item.status)}</span></div>`).join("");
}

function renderChart(effect) {
  const rows = [["点击率", effect.ctr, "%", 42, 20], ["预计转化率", effect.conversion, "%", 118, 8], ["退订风险", effect.unsubscribe, "%", 194, 5]];
  els.chart.innerHTML = rows.map(([label, value, unit, y, max]) => {
    const width = Math.max(12, Math.min(390, value / max * 390));
    return `<text class="chart-muted" x="22" y="${y + 22}">${label}</text><rect class="bar-bg" x="165" y="${y}" width="390" height="28" rx="4"></rect><rect class="bar" x="165" y="${y}" width="${width}" height="28" rx="4"></rect><text class="chart-text" x="${Math.min(570, 178 + width)}" y="${y + 22}">${value}${unit}</text>`;
  }).join("");
}

async function publishPlan() {
  if (!currentCampaignId) return;
  els.publish.disabled = true;
  try {
    const data = await postJson("/api/strategy/publications", {campaign_id: currentCampaignId});
    els.publishedStatus.textContent = `已发布 ${data.publication.strategy_version}`;
    els.status.textContent = "策略包已发布给 C 端。";
  } catch (error) {
    els.publish.disabled = false;
    els.status.textContent = `发布失败：${error.message}`;
  }
}

function campaignName(campaignId) {
  return Array.from(els.campaign.options).find(option => option.value === campaignId)?.textContent || campaignId;
}

function selectedOperatorContent() {
  const selected = new Set(selectedChannels());
  if (!selected.size) return currentContent;
  return Object.fromEntries(Object.entries(currentContent).filter(([channel]) => selected.has(channel)));
}

async function postJson(url, body) {
  const response = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"})[character]);
}

function escapeAttribute(value) { return escapeHtml(value); }

els.parseGoal.addEventListener("click", parseGoal);
els.manualMode.addEventListener("click", useManualMode);
els.acceptSuggestion.addEventListener("click", acceptSuggestion);
els.recheck.addEventListener("click", recheckStrategy);
els.toggleOperatorFilters.addEventListener("click", () => {
  els.operatorFilterPanel.hidden = !els.operatorFilterPanel.hidden;
  els.toggleOperatorFilters.textContent = els.operatorFilterPanel.hidden ? "+ 添加筛选条件" : "收起筛选条件";
});
els.operatorFilterTags.addEventListener("click", event => {
  const tag = event.target.closest("[data-filter-key]");
  if (tag) clearOperatorFilter(tag.dataset.filterKey || "");
});
[els.filterGender, els.filterAgeMin, els.filterAgeMax, els.filterSpendMin].forEach(input => {
  input.addEventListener("input", renderOperatorFilterTags);
  input.addEventListener("change", renderOperatorFilterTags);
});
els.cityCheckGroup.addEventListener("change", renderOperatorFilterTags);
els.behaviorCheckGroup.addEventListener("change", renderOperatorFilterTags);
els.valueLevelCheckGroup.addEventListener("change", renderOperatorFilterTags);
els.lifecycleCheckGroup.addEventListener("change", renderOperatorFilterTags);
els.riskLevelCheckGroup.addEventListener("change", renderOperatorFilterTags);
els.askQuestion.addEventListener("click", askQuestion);
els.draftContent.addEventListener("click", draftContent);
els.generate.addEventListener("click", generateStrategy);
els.publish.addEventListener("click", publishPlan);
els.question.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); askQuestion(); } });
els.copy.addEventListener("input", () => { currentContent[activeContentChannel] = els.copy.value; els.copyStatus.textContent = "已保留运营修改，生成策略时将写入策略包"; });
els.contentTabs.addEventListener("click", event => {
  const tab = event.target.closest("[data-channel]");
  if (!tab || !configurationReady) return;
  currentContent[activeContentChannel] = els.copy.value;
  activeContentChannel = tab.dataset.channel;
  renderContentEditor();
});
[els.campaign, els.budget, els.channelCoverageTrial].forEach(control => control.addEventListener("change", updateContentContext));
els.channelCheckGroup.addEventListener("change", updateContentContext);
els.audienceCheckGroup.addEventListener("change", updateContentContext);

setConfigurationEditable(false);
renderOperatorFilterTags();
loadCampaignOptions();

async function loadCampaignOptions() {
  try {
    const data = await (await fetch("/api/strategy/campaigns")).json();
    if (!Array.isArray(data.items)) return;
    const previous = els.campaign.value;
    els.campaign.replaceChildren();
    data.items.forEach(item => {
      const option = document.createElement("option");
      option.value = item.campaign_id;
      option.textContent = item.label;
      els.campaign.append(option);
    });
    els.campaign.value = data.items.some(item => item.campaign_id === previous) ? previous : data.items[0]?.campaign_id || "";
  } catch (_error) {
    // The page keeps its empty selector until the local service is available.
  }
}

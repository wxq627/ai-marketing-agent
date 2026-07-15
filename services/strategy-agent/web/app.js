const els = {
  goal: document.getElementById("goalInput"),
  product: document.getElementById("productInput"),
  channel: document.getElementById("channelInput"),
  budget: document.getElementById("budgetInput"),
  risk: document.getElementById("riskInput"),
  freq: document.getElementById("freqInput"),
  generate: document.getElementById("generateBtn"),
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
};

async function generatePlan() {
  els.status.textContent = "正在生成";
  els.generate.disabled = true;
  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        goal: els.goal.value,
        product: els.product.value,
        channel_mode: els.channel.value,
        budget_wan: Number(els.budget.value),
        risk_level: Number(els.risk.value),
        frequency_level: Number(els.freq.value),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "生成失败");
    renderPlan(data);
    els.status.textContent = "方案已生成";
  } catch (error) {
    els.status.textContent = error.message;
  } finally {
    els.generate.disabled = false;
  }
}

function renderPlan(plan) {
  els.campaignId.textContent = plan.campaign_id;
  els.audience.textContent = `${plan.audience_size.toLocaleString()} 人`;
  els.uplift.textContent = `+${plan.predicted_uplift}%`;
  els.roi.textContent = `${plan.predicted_roi}x`;
  els.riskMetric.textContent = `${plan.effect_forecast.complaint}%`;
  renderSegments(plan.segments);
  renderChannels(plan.channels);
  renderContent(plan.content);
  renderCompliance(plan.compliance);
  renderChart(plan.effect_forecast);
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

els.generate.addEventListener("click", generatePlan);
generatePlan();

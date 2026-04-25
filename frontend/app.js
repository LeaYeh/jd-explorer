const STORAGE_CV = "jde_cv_url";
const STORAGE_PORTALS = "jde_portals";

const cvInput = document.getElementById("cv-input");
const cvStatus = document.getElementById("cv-status");
const portalInput = document.getElementById("portal-input");
const portalList = document.getElementById("portal-list");
const analyzeBtn = document.getElementById("analyze-btn");
const progressPanel = document.getElementById("progress-panel");
const progressLog = document.getElementById("progress-log");
const resultsEl = document.getElementById("results");

let portals = JSON.parse(localStorage.getItem(STORAGE_PORTALS) || "[]");

function loadState() {
  const cv = localStorage.getItem(STORAGE_CV) || "";
  if (cv) { cvInput.value = cv; setCvStatus(cv); }
  renderPortals();
}

function setCvStatus(url) {
  cvStatus.textContent = url ? `CV set: ${url}` : "";
  cvStatus.className = "cv-status" + (url ? " set" : "");
  updateAnalyzeBtn();
}

function saveCv() {
  const url = cvInput.value.trim();
  if (!url) return;
  localStorage.setItem(STORAGE_CV, url);
  setCvStatus(url);
}

function addPortal() {
  const url = portalInput.value.trim();
  if (!url || portals.includes(url)) return;
  portals.push(url);
  localStorage.setItem(STORAGE_PORTALS, JSON.stringify(portals));
  portalInput.value = "";
  renderPortals();
  updateAnalyzeBtn();
}

function removePortal(url) {
  portals = portals.filter(p => p !== url);
  localStorage.setItem(STORAGE_PORTALS, JSON.stringify(portals));
  renderPortals();
  updateAnalyzeBtn();
}

function renderPortals() {
  portalList.innerHTML = "";
  if (!portals.length) {
    portalList.innerHTML = '<p class="empty">No portals added yet.</p>';
    return;
  }
  portals.forEach(url => {
    const item = document.createElement("div");
    item.className = "portal-item";
    item.innerHTML = `<span title="${url}">${url}</span>
      <button class="btn-danger" onclick="removePortal('${url.replace(/'/g, "\\'")}')">remove</button>`;
    portalList.appendChild(item);
  });
}

function updateAnalyzeBtn() {
  const cv = localStorage.getItem(STORAGE_CV) || "";
  analyzeBtn.disabled = !cv || !portals.length;
}

function addProgress(message, type = "") {
  const entry = document.createElement("div");
  entry.className = "progress-entry" + (type ? ` ${type}` : "");
  entry.textContent = message;
  progressLog.appendChild(entry);
  progressLog.scrollTop = progressLog.scrollHeight;
}

async function analyze() {
  const cv_url = localStorage.getItem(STORAGE_CV);
  analyzeBtn.disabled = true;

  progressLog.innerHTML = "";
  progressPanel.style.display = "block";
  resultsEl.innerHTML = "";
  resultsEl.classList.remove("visible");

  try {
    const resp = await fetch("/api/analyze/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cv_url, portal_urls: portals }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      addProgress(`Error: ${err.detail || resp.statusText}`, "error");
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep partial last line

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          handleEvent(JSON.parse(line.slice(6)));
        } catch (_) {}
      }
    }
  } catch (e) {
    addProgress(`Network error: ${e.message}`, "error");
  } finally {
    analyzeBtn.disabled = false;
    updateAnalyzeBtn();
  }
}

function handleEvent(event) {
  if (event.type === "progress") {
    addProgress(event.message);
  } else if (event.type === "job") {
    resultsEl.classList.add("visible");
    resultsEl.appendChild(buildJobCard(event.data));
  } else if (event.type === "done") {
    const count = resultsEl.querySelectorAll(".job-card").length;
    addProgress(`Done — ${count} job(s) analyzed`, "success");
  } else if (event.type === "error") {
    addProgress(`✗ ${event.message}`, "error");
  }
}

function fitClass(score) {
  if (score >= 70) return "fit-high";
  if (score >= 40) return "fit-mid";
  return "fit-low";
}

function buildJobCard(job) {
  const card = document.createElement("div");
  card.className = "job-card";

  const adjustments = (job.cv_adjustments || [])
    .map(s => `<li>${s}</li>`).join("") || '<li class="empty">None</li>';
  const skills = (job.skills_to_add || [])
    .map(s => `<span class="tag">${s}</span>`).join("") || '<span class="empty">None</span>';

  card.innerHTML = `
    <div class="job-header">
      <span class="job-title">${job.title}</span>
      <span class="fit-badge ${fitClass(job.fit_score)}">${job.fit_score}% fit</span>
    </div>
    <p class="job-summary">${job.summary || ""}</p>
    <div class="job-grid">
      <div>
        <div class="job-section-title">CV Adjustments</div>
        <ul class="job-list">${adjustments}</ul>
      </div>
      <div>
        <div class="job-section-title">Skills to Add</div>
        <div class="tag-list">${skills}</div>
      </div>
    </div>
    ${job.salary_range && job.salary_range !== "N/A"
      ? `<div class="salary">Salary: ${job.salary_range}</div>`
      : ""}`;
  return card;
}

document.getElementById("set-cv-btn").addEventListener("click", saveCv);
cvInput.addEventListener("keydown", e => e.key === "Enter" && saveCv());
document.getElementById("add-portal-btn").addEventListener("click", addPortal);
portalInput.addEventListener("keydown", e => e.key === "Enter" && addPortal());
analyzeBtn.addEventListener("click", analyze);

loadState();

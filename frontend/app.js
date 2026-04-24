const STORAGE_CV = "jde_cv_url";
const STORAGE_PORTALS = "jde_portals";

const cvInput = document.getElementById("cv-input");
const cvStatus = document.getElementById("cv-status");
const portalInput = document.getElementById("portal-input");
const portalList = document.getElementById("portal-list");
const analyzeBtn = document.getElementById("analyze-btn");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");

let portals = JSON.parse(localStorage.getItem(STORAGE_PORTALS) || "[]");

function loadState() {
  const cv = localStorage.getItem(STORAGE_CV) || "";
  if (cv) {
    cvInput.value = cv;
    setCvStatus(cv);
  }
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

async function analyze() {
  const cv_url = localStorage.getItem(STORAGE_CV);
  analyzeBtn.disabled = true;
  statusEl.innerHTML = '<span class="spinner"></span>Fetching & analyzing...';
  resultsEl.classList.remove("visible");

  try {
    const resp = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cv_url, portal_urls: portals }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || resp.statusText);
    }
    const data = await resp.json();
    renderResults(data.results);
    statusEl.textContent = `Done — ${data.results.reduce((s, r) => s + r.jobs.length, 0)} jobs analyzed.`;
  } catch (e) {
    statusEl.textContent = `Error: ${e.message}`;
  } finally {
    analyzeBtn.disabled = false;
    updateAnalyzeBtn();
  }
}

function fitClass(score) {
  if (score >= 70) return "fit-high";
  if (score >= 40) return "fit-mid";
  return "fit-low";
}

function renderResults(results) {
  resultsEl.innerHTML = "";
  results.forEach(({ portal_url, jobs }) => {
    const section = document.createElement("div");
    section.className = "portal-section";
    section.innerHTML = `<h3>${portal_url}</h3>`;

    if (!jobs.length) {
      section.innerHTML += '<p class="empty">No job listings found on this page.</p>';
    } else {
      jobs.forEach(job => {
        section.appendChild(buildJobCard(job));
      });
    }
    resultsEl.appendChild(section);
  });
  resultsEl.classList.add("visible");
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

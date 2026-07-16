let lastPayload = null;
let lastQuality = null;
let lastPostId = null;

document.querySelectorAll(".nav").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "history") loadHistory();
    if (btn.dataset.tab === "scheduler") loadSchedules();
  });
});

const statusEl = document.getElementById("status");
const previewText = document.getElementById("preview-text");
const previewImg = document.getElementById("preview-img");
const qualityEl = document.getElementById("quality");
const platformView = document.getElementById("platform-view");

function setStatus(msg) {
  statusEl.textContent = msg;
}

function renderPreview() {
  if (!lastPayload) return;
  const view = platformView.value;
  if (view === "Generated Image") {
    previewText.classList.add("hidden");
    previewImg.classList.remove("hidden");
    previewImg.src = lastPayload.image_url || "";
    if (!lastPayload.image_url) {
      previewImg.classList.add("hidden");
      previewText.classList.remove("hidden");
      previewText.textContent = "No image yet. Click Generate Image.";
    }
    return;
  }
  previewImg.classList.add("hidden");
  previewText.classList.remove("hidden");

  let text = "";
  if (view === "LinkedIn") {
    const b = lastPayload.linkedin || {};
    text = `${b.title || ""}\n\n${b.content || ""}\n\n${(b.hashtags || []).join(" ")}`.trim();
  } else if (view === "X") {
    const b = lastPayload.x || {};
    text = `${b.content || ""}\n${(b.hashtags || []).join(" ")}`.trim();
  } else if (view === "Facebook") {
    const b = lastPayload.facebook || {};
    text = `${b.content || ""}\n\n${(b.hashtags || []).join(" ")}`.trim();
  } else if (view === "Instagram") {
    const b = lastPayload.instagram || {};
    text = `${b.caption || ""}\n\n${(b.hashtags || []).join(" ")}`.trim();
  } else if (view === "Image Prompt") {
    text = lastPayload.image_prompt || "";
  } else {
    text = JSON.stringify(lastPayload, null, 2);
  }
  previewText.textContent = text;

  if (lastQuality) {
    qualityEl.textContent = `Quality · Readability ${lastQuality.readability} (${lastQuality.readability_label}) · Uniqueness ${lastQuality.uniqueness} · X ${lastQuality.x_chars}/280`;
  }
}

platformView.addEventListener("change", renderPreview);

document.getElementById("gen-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const btn = document.getElementById("btn-gen");
  btn.disabled = true;
  setStatus("Generating…");
  try {
    const fd = new FormData(form);
    // Ensure unchecked bools
    if (![...fd.keys()].includes("auto_image")) fd.set("auto_image", "false");
    if (![...fd.keys()].includes("emoji_enabled")) fd.set("emoji_enabled", "false");
    else fd.set("emoji_enabled", "true");
    if (fd.get("auto_image") === "true") fd.set("auto_image", "true");

    const res = await fetch("/api/generate", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Generate failed");
    lastPayload = data.payload;
    lastQuality = data.quality;
    lastPostId = data.post_id;
    document.getElementById("post-id-line").textContent = `Saved post #${lastPostId}`;
    if (lastPayload.image_url) platformView.value = "Generated Image";
    renderPreview();
    setStatus(`Done via ${data.provider}`);
  } catch (err) {
    setStatus(`Error: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("btn-img").addEventListener("click", async () => {
  setStatus("Generating image…");
  try {
    const res = await fetch("/api/image", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Image failed");
    if (lastPayload) {
      lastPayload.image_url = data.image_url;
      lastPayload.image_path = data.path;
    }
    platformView.value = "Generated Image";
    renderPreview();
    setStatus(`Image via ${data.provider}`);
  } catch (err) {
    setStatus(`Error: ${err.message}`);
  }
});

document.getElementById("btn-copy").addEventListener("click", async () => {
  const text = previewText.classList.contains("hidden")
    ? lastPayload?.image_url || ""
    : previewText.textContent;
  await navigator.clipboard.writeText(text);
  setStatus("Copied");
});

async function loadHistory() {
  const q = document.getElementById("hist-q").value || "";
  const res = await fetch(`/api/history?q=${encodeURIComponent(q)}`);
  const data = await res.json();
  const list = document.getElementById("hist-list");
  list.innerHTML = "";
  (data.posts || []).forEach((p) => {
    const li = document.createElement("li");
    li.textContent = `#${p.id} · ${p.created_at} · ${p.title || p.topic}`;
    li.onclick = async () => {
      const r = await fetch(`/api/history/${p.id}`);
      const d = await r.json();
      lastPayload = d.payload;
      lastQuality = d.quality;
      lastPostId = d.post_id;
      document.querySelector('[data-tab="generate"]').click();
      renderPreview();
      document.getElementById("post-id-line").textContent = `Loaded post #${lastPostId}`;
    };
    list.appendChild(li);
  });
}

document.getElementById("btn-hist").addEventListener("click", loadHistory);

document.getElementById("sched-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const res = await fetch("/api/schedule", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Schedule failed");
    return;
  }
  alert(`Scheduled #${data.schedule_id}`);
  loadSchedules();
});

async function loadSchedules() {
  const res = await fetch("/api/schedules");
  const data = await res.json();
  const lines = (data.schedules || []).map(
    (r) => `#${r.id}  post=${r.post_id}  ${r.platform}  ${r.scheduled_at}  [${r.status}]  ${r.notes || ""}`
  );
  document.getElementById("sched-list").textContent = lines.join("\n") || "No schedules yet.";
}

document.getElementById("btn-sched-refresh").addEventListener("click", loadSchedules);

// default date today
const dateInput = document.querySelector('#sched-form input[name="date"]');
if (dateInput) dateInput.value = new Date().toISOString().slice(0, 10);

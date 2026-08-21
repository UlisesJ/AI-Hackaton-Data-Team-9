const enterBtn = document.getElementById("enter-btn");
const backToGate = document.getElementById("back-to-gate");
const appShell = document.getElementById("app");
const gateEl = document.getElementById("gate");

function scrollToEl(el) {
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

if (enterBtn) {
  enterBtn.addEventListener("click", (event) => {
    event.preventDefault();
    scrollToEl(appShell);
  });
}

if (backToGate) {
  backToGate.addEventListener("click", (event) => {
    event.preventDefault();
    scrollToEl(gateEl);
  });
}

const form = document.getElementById("job-form");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const statusBadge = document.getElementById("status-badge");
const statusText = document.getElementById("status-text");
const statusError = document.getElementById("status-error");
const results = document.getElementById("results");
const clipsEl = document.getElementById("clips");
const videoTitle = document.getElementById("video-title");
const resultsMeta = document.getElementById("results-meta");

let pollTimer = null;

function setStatus(job) {
  statusEl.hidden = false;
  statusBadge.textContent = job.status;
  statusText.textContent = job.progress || "";
  if (job.error) {
    statusError.hidden = false;
    statusError.textContent = job.error;
  } else {
    statusError.hidden = true;
    statusError.textContent = "";
  }
}

function formatTime(sec) {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function renderClips(job) {
  results.hidden = false;
  videoTitle.textContent = job.video_title || "Clips ready";
  resultsMeta.textContent = `${job.clips.length} clips · job ${job.id.slice(0, 8)}`;
  clipsEl.innerHTML = "";

  for (const clip of job.clips) {
    const card = document.createElement("article");
    card.className = "clip";

    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.src = `/jobs/${job.id}/clips/${clip.id}`;

    const body = document.createElement("div");
    body.className = "clip-body";
    body.innerHTML = `
      <h3>${escapeHtml(clip.title)}</h3>
      <p class="clip-meta">Score ${Math.round(clip.score)} · ${formatTime(clip.start_sec)}–${formatTime(clip.end_sec)} · ${Math.round(clip.duration_sec)}s</p>
      <p class="clip-reason">${escapeHtml(clip.reason)}</p>
      <p class="clip-caption">${escapeHtml(clip.caption)}</p>
      <p class="hashtags">${escapeHtml((clip.hashtags || []).join(" "))}</p>
      <div class="actions">
        <a href="/jobs/${job.id}/clips/${clip.id}" download>Download MP4</a>
        <a class="secondary" href="/jobs/${job.id}/clips/${clip.id}/srt" download>SRT</a>
      </div>
    `;

    card.appendChild(video);
    card.appendChild(body);
    clipsEl.appendChild(card);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function pollJob(jobId) {
  const res = await fetch(`/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error("Could not fetch job status");
  }
  const job = await res.json();
  setStatus(job);

  if (job.status === "completed") {
    submitBtn.disabled = false;
    renderClips(job);
    return;
  }
  if (job.status === "failed") {
    submitBtn.disabled = false;
    return;
  }

  pollTimer = setTimeout(() => pollJob(jobId).catch(showFatal), 2000);
}

function showFatal(err) {
  submitBtn.disabled = false;
  statusEl.hidden = false;
  statusBadge.textContent = "failed";
  statusText.textContent = "Error";
  statusError.hidden = false;
  statusError.textContent = err.message || String(err);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }

  const url = document.getElementById("url").value.trim();
  const fileInput = document.getElementById("file");
  const file = fileInput.files && fileInput.files[0];
  if (!url && !file) {
    showFatal(new Error("Paste a YouTube URL or upload a local MP4"));
    return;
  }

  submitBtn.disabled = true;
  results.hidden = true;
  clipsEl.innerHTML = "";
  setStatus({ status: "queued", progress: "Sending…", error: null });

  const maxClips = Number(document.getElementById("max_clips").value);
  const clipDuration = Math.round(Number(document.getElementById("clip_duration_sec").value));

  try {
    let res;
    if (file) {
      const body = new FormData();
      body.append("file", file);
      body.append("max_clips", String(maxClips));
      body.append("clip_duration_sec", String(clipDuration));
      res = await fetch("/jobs/upload", { method: "POST", body });
    } else {
      res = await fetch("/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          max_clips: maxClips,
          clip_duration_sec: clipDuration,
        }),
      });
    }
    const data = await res.json();
    if (!res.ok) {
      const detail = data.detail;
      const message = Array.isArray(detail)
        ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
        : detail || "Could not create the job";
      throw new Error(message);
    }
    setStatus(data);
    await pollJob(data.id);
  } catch (err) {
    showFatal(err);
  }
});

const themeToggles = document.querySelectorAll(".theme-toggle");

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function syncThemeLabel() {
  const label = currentTheme() === "dark" ? "Light" : "Dark";
  document.querySelectorAll(".theme-toggle-label").forEach((el) => {
    el.textContent = label;
  });
}

syncThemeLabel();

themeToggles.forEach((btn) => {
  btn.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("monkclip-theme", next);
    } catch (e) {
      /* ignore */
    }
    syncThemeLabel();
  });
});
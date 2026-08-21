const root = document.querySelector(".screen-shell");
const frame = document.getElementById("screen-frame");
const emptyState = document.getElementById("screen-empty");
const content = document.getElementById("screen-content");

const playlist = JSON.parse(root?.dataset.playlist || "[]");

let index = 0;
let timeoutId = null;
let videoEndCheckIntervalId = null;
let manualAdvanceEnabled = false;

function renderCurrentItem() {
  clearAdvanceTimers();

  if (!playlist.length) {
    emptyState.hidden = false;
    frame.hidden = true;
    sendHeartbeat();
    return;
  }

  emptyState.hidden = true;
  frame.hidden = false;

  const item = playlist[index];
  content.innerHTML = buildMarkup(item);
  sendHeartbeat();

  if (item.type === "video") {
    const video = content.querySelector("video");
    if (video) {
      if (manualAdvanceEnabled) {
        return;
      }

      let hasAdvanced = false;
      let lastCurrentTime = 0;
      let lastProgressAt = Date.now();
      const advanceAfterVideo = () => {
        if (hasAdvanced) {
          return;
        }
        hasAdvanced = true;
        clearAdvanceTimers();
        goToNextItem();
      };

      video.addEventListener(
        "ended",
        advanceAfterVideo,
        { once: true }
      );
      video.addEventListener("error", advanceAfterVideo, { once: true });

      const scheduleVideoDeadline = () => {
        const duration = video.duration;
        const playbackRate = video.playbackRate || 1;
        if (!Number.isFinite(duration) || duration <= 0) {
          return;
        }

        window.clearTimeout(timeoutId);
        const remainingSeconds = Math.max(0, duration - video.currentTime) / playbackRate;
        timeoutId = window.setTimeout(advanceAfterVideo, (remainingSeconds + 10) * 1000);
      };

      video.addEventListener("playing", scheduleVideoDeadline);

      // Chromium on older Raspberry Pis can stop updating the video position
      // without emitting `ended` and without landing close enough to `duration`.
      // Once playback has started, four seconds without progress means the
      // decoder is stuck and the playlist should continue.
      videoEndCheckIntervalId = window.setInterval(() => {
        const currentTime = video.currentTime;
        const hasProgressed = Math.abs(currentTime - lastCurrentTime) >= 0.05;

        if (video.ended) {
          advanceAfterVideo();
          return;
        }

        if (hasProgressed) {
          lastProgressAt = Date.now();
        } else if (currentTime > 0.25 && Date.now() - lastProgressAt >= 4000) {
          advanceAfterVideo();
          return;
        }

        lastCurrentTime = currentTime;
      }, 500);

      video.play().catch(() => {});
      return;
    }
  }

  if (manualAdvanceEnabled) {
    return;
  }
  timeoutId = window.setTimeout(() => {
    goToNextItem();
  }, getDurationSeconds(item) * 1000);
}

function clearAdvanceTimers() {
  window.clearTimeout(timeoutId);
  window.clearInterval(videoEndCheckIntervalId);
  timeoutId = null;
  videoEndCheckIntervalId = null;
}

function sendHeartbeat() {
  // A heartbeat is tied to actual playlist progress, not just a running timer.
  window.fetch("/screen/heartbeat", {
    method: "POST",
    cache: "no-store",
    keepalive: true,
  }).catch(() => {});
}

function goToNextItem() {
  clearAdvanceTimers();

  // The simplest way to pick up YAML changes is to reload after one full pass.
  const isLastItem = index >= playlist.length - 1;
  if (isLastItem) {
    window.location.reload();
    return;
  }

  index += 1;
  renderCurrentItem();
}

function buildMarkup(item) {
  if (item.type === "image") {
    return `
      <article class="media-card">
        <img src="/uploads/${item.content}" alt="${escapeHtml(item.type || "image")}">
      </article>
    `;
  }

  if (item.type === "video") {
    return `
      <article class="media-card">
        <video src="/uploads/${item.content}" autoplay muted playsinline></video>
      </article>
    `;
  }

  if (item.type === "web") {
    return `
      <article class="web-card">
        <iframe src="${escapeAttribute(item.content || "")}" referrerpolicy="no-referrer"></iframe>
      </article>
    `;
  }

  if (item.type === "calendar_event") {
    const animationDuration = Math.min(getDurationSeconds(item), 15);
    const cardStyle = item.image_url
      ? ` style="--calendar-event-image: url('${escapeCssUrl(item.image_url)}'); --calendar-event-animation-duration: ${animationDuration}s;"`
      : "";
    const title = item.summary || "";
    const longTitleClass = isLongTitle(title) ? " is-long-title" : "";
    const caption = String(item.caption || "").trim();
    const captionMarkup = caption
      ? `<p class="calendar-event-caption">${escapeHtml(caption)}</p>`
      : "";
    const qrCode = item.qr_code_data_uri
      ? `
        <div class="calendar-event-qr">
          <img src="${escapeAttribute(item.qr_code_data_uri)}" alt="QR-Code zur Veranstaltungsseite">
          <span>Mehr Infos</span>
        </div>
      `
      : "";

    return `
      <article class="calendar-event-card ${item.image_url ? "with-image" : "without-image"}${longTitleClass}"${cardStyle}>
        <div class="calendar-event-body">
          <div class="calendar-event-category">${escapeHtml(item.category || "Veranstaltung")}</div>
          <h1 class="calendar-event-title">${escapeHtml(title || "Ohne Titel")}</h1>
          ${captionMarkup}
          <p class="calendar-event-date">${escapeHtml(item.start_label || "")}</p>
        </div>
        ${qrCode}
      </article>
    `;
  }

  return `
    <article class="calendar-card">
      <div class="calendar-inner">
        <h1>Unbekannter Inhaltstyp</h1>
      </div>
    </article>
  `;
}

function getDurationSeconds(item) {
  const duration = Number(item?.duration);
  return Number.isFinite(duration) && duration > 0 ? duration : 15;
}

function escapeHtml(value) {
  // Small helper because content comes from editable YAML.
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

function escapeCssUrl(value) {
  return String(value)
    .replaceAll("\\", "\\\\")
    .replaceAll("'", "\\'");
}

function isLongTitle(value) {
  const text = String(value || "").trim();
  return text.length > 42 || text.split(/\s+/).length > 5;
}

window.addEventListener("keydown", () => {
  if (!playlist.length) {
    return;
  }

  if (!manualAdvanceEnabled) {
    manualAdvanceEnabled = true;
    clearAdvanceTimers();
    return;
  }

  goToNextItem();
});

renderCurrentItem();

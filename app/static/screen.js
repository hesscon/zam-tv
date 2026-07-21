const root = document.querySelector(".screen-shell");
const frame = document.getElementById("screen-frame");
const emptyState = document.getElementById("screen-empty");
const content = document.getElementById("screen-content");

const playlist = JSON.parse(root?.dataset.playlist || "[]");

let index = 0;
let timeoutId = null;
let manualAdvanceEnabled = false;

function renderCurrentItem() {
  if (!playlist.length) {
    window.clearTimeout(timeoutId);
    emptyState.hidden = false;
    frame.hidden = true;
    return;
  }

  emptyState.hidden = true;
  frame.hidden = false;

  const item = playlist[index];
  content.innerHTML = buildMarkup(item);

  if (item.type === "video") {
    const video = content.querySelector("video");
    if (video) {
      window.clearTimeout(timeoutId);
      if (manualAdvanceEnabled) {
        return;
      }
      video.addEventListener(
        "ended",
        () => {
          goToNextItem();
        },
        { once: true }
      );
      video.play().catch(() => {});
      return;
    }
  }

  window.clearTimeout(timeoutId);
  if (manualAdvanceEnabled) {
    return;
  }
  timeoutId = window.setTimeout(() => {
    goToNextItem();
  }, Number(item.duration) * 1000);
}

function goToNextItem() {
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
    const cardStyle = item.image_url
      ? ` style="--calendar-event-image: url('${escapeCssUrl(item.image_url)}');"`
      : "";
    const title = item.summary || "";
    const longTitleClass = isLongTitle(title) ? " is-long-title" : "";
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
    window.clearTimeout(timeoutId);
    return;
  }

  goToNextItem();
});

renderCurrentItem();

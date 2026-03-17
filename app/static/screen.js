const root = document.querySelector(".screen-shell");
const frame = document.getElementById("screen-frame");
const emptyState = document.getElementById("screen-empty");
const content = document.getElementById("screen-content");

const playlist = JSON.parse(root?.dataset.playlist || "[]");
const defaultDuration = Number(root?.dataset.defaultDuration || "10");

let index = 0;
let timeoutId = null;

function renderCurrentItem() {
  if (!playlist.length) {
    emptyState.hidden = false;
    frame.hidden = true;
    return;
  }

  emptyState.hidden = true;
  frame.hidden = false;

  const item = playlist[index];
  const duration = Number(item.duration || defaultDuration) * 1000;
  content.innerHTML = buildMarkup(item);

  if (item.type === "video") {
    const video = content.querySelector("video");
    if (video) {
      video.play().catch(() => {});
    }
  }

  window.clearTimeout(timeoutId);
  timeoutId = window.setTimeout(() => {
    // The simplest way to pick up YAML changes is to reload after one full pass.
    const isLastItem = index >= playlist.length - 1;
    if (isLastItem) {
      window.location.reload();
      return;
    }

    index += 1;
    renderCurrentItem();
  }, duration);
}

function buildMarkup(item) {
  if (item.type === "image") {
    return `
      <article class="media-card">
        <img src="/uploads/${item.path}" alt="${escapeHtml(item.title || "Bild")}">
      </article>
    `;
  }

  if (item.type === "video") {
    return `
      <article class="media-card">
        <video src="/uploads/${item.path}" autoplay muted playsinline></video>
      </article>
    `;
  }

  if (item.type === "web") {
    return `
      <article class="web-card">
        <iframe src="${escapeAttribute(item.url || "")}" referrerpolicy="no-referrer"></iframe>
      </article>
    `;
  }

  if (item.type === "calendar") {
    const events = Array.isArray(item.events) ? item.events : [];
    const eventMarkup = events.length
      ? events
          .map(
            (event) => `
              <li>
                ${escapeHtml(event.title)}
                <span class="calendar-date">${escapeHtml(event.start_label)}</span>
              </li>
            `
          )
          .join("")
      : "<li>Keine passenden Termine gefunden.</li>";

    return `
      <article class="calendar-card">
        <div class="calendar-inner">
          <h1>${escapeHtml(item.title || "Kalender")}</h1>
          <ul class="calendar-list">${eventMarkup}</ul>
        </div>
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
  // Small helper because item titles and URLs come from editable YAML.
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

renderCurrentItem();

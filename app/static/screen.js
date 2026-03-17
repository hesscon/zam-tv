const root = document.querySelector(".screen-shell");
const frame = document.getElementById("screen-frame");
const emptyState = document.getElementById("screen-empty");
const content = document.getElementById("screen-content");

const playlist = JSON.parse(root?.dataset.playlist || "[]");

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
  content.innerHTML = buildMarkup(item);

  if (item.type === "video") {
    const video = content.querySelector("video");
    if (video) {
      window.clearTimeout(timeoutId);
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
          <h1>Kalender</h1>
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

renderCurrentItem();

const fileInput = document.getElementById("media_files");
const dropzone = document.getElementById("upload-dropzone");
const selection = document.getElementById("upload-selection");
const cleanupForm = document.getElementById("cleanup-form");
const applicationLogs = document.getElementById("application-logs");

if (applicationLogs && window.location.hash === "#application-logs") {
  applicationLogs.focus({ preventScroll: true });
}

if (fileInput && dropzone && selection) {
  fileInput.addEventListener("change", () => {
    updateSelection(fileInput.files);
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragover");
    });
  });

  dropzone.addEventListener("drop", (event) => {
    const files = event.dataTransfer?.files;
    if (!files || !files.length) {
      return;
    }

    fileInput.files = files;
    updateSelection(files);
  });
}

if (cleanupForm) {
  cleanupForm.addEventListener("submit", (event) => {
    const confirmed = window.confirm("Wirklich alle nicht benutzten Dateien loeschen?");
    if (!confirmed) {
      event.preventDefault();
    }
  });
}

function updateSelection(files) {
  if (!files || !files.length) {
    selection.textContent = "Noch keine Dateien ausgewaehlt.";
    return;
  }

  selection.textContent = Array.from(files)
    .map((file) => file.name)
    .join(", ");
}

const dropzone = document.querySelector("#dropzone");
const input = document.querySelector("#vault-files");
const results = document.querySelector("#upload-results");
const list = document.querySelector("#vault-manage");
const empty = document.querySelector("#vault-empty");
const usageLine = document.querySelector("#vault-usage");
const errorBox = document.querySelector("#vault-error");

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(seconds) {
  return new Date(seconds * 1000).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

function render(documents, usage) {
  const rows = documents.map((doc) => {
    const row = document.createElement("li");
    row.className = "vault-row";
    const main = document.createElement("div");
    main.className = "vault-row-main";
    const title = document.createElement("strong");
    title.textContent = doc.title;
    const meta = document.createElement("span");
    const pages = `${doc.pages} page${doc.pages === 1 ? "" : "s"}`;
    meta.textContent = `${doc.filename} · ${doc.kind} · ${pages} · ${formatSize(doc.size)} · added ${formatDate(doc.added_at)}`;
    main.append(title, meta);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = "Delete";
    remove.setAttribute("aria-label", `Delete ${doc.title}`);
    remove.addEventListener("click", () => removeDocument(doc));
    row.append(main, remove);
    return row;
  });
  list.replaceChildren(...rows);
  empty.hidden = documents.length > 0;
  usageLine.textContent = `${usage.count} of ${usage.max_documents} documents · ${formatSize(usage.bytes)} of ${formatSize(usage.max_bytes)} used`;
}

async function load() {
  try {
    const response = await fetch("/api/vault");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "The vault could not be loaded.");
    showError("");
    render(data.mine.documents, data.mine.usage);
  } catch (error) {
    showError(error.message);
  }
}

function resultLine({ filename, outcome, reason }) {
  const item = document.createElement("li");
  if (outcome === "rejected") {
    item.className = "result-rejected";
    item.textContent = `${filename}: not added. ${reason}`;
  } else {
    item.className = "result-ok";
    item.textContent =
      outcome === "replaced"
        ? `${filename}: saved, replacing the copy you already had.`
        : `${filename}: saved.`;
  }
  return item;
}

async function upload(files) {
  const pdfs = [...files];
  if (pdfs.length === 0) return;
  const body = new FormData();
  for (const file of pdfs) body.append("files", file);
  dropzone.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("/api/vault/documents", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "The files could not be saved.");
    results.replaceChildren(...data.results.map(resultLine));
    showError("");
    render(data.documents, data.usage);
  } catch (error) {
    showError(error.message);
  } finally {
    dropzone.removeAttribute("aria-busy");
    input.value = "";
  }
}

async function removeDocument(doc) {
  if (!window.confirm(`Delete "${doc.title}" from your vault? Relay will stop using it for new forms.`)) return;
  try {
    const response = await fetch(`/api/vault/documents/${doc.id}`, { method: "DELETE" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "The document could not be deleted.");
    results.replaceChildren();
    await load();
  } catch (error) {
    showError(error.message);
  }
}

input.addEventListener("change", () => upload(input.files));

for (const type of ["dragenter", "dragover"]) {
  dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    dropzone.classList.add("is-over");
  });
}
for (const type of ["dragleave", "drop"]) {
  dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-over");
  });
}
dropzone.addEventListener("drop", (event) => upload(event.dataTransfer.files));

load();

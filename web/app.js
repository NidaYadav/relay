import { createHandoffUi } from "/static/handoff.js";

const home = document.querySelector("#home");
const brief = document.querySelector("#brief");
const sampleButton = document.querySelector("#sample-button");
const formUpload = document.querySelector("#form-upload");
const homeError = document.querySelector("#home-error");
const processingError = document.querySelector("#processing-error");
const retryButton = document.querySelector("#retry-button");
const worklog = document.querySelector("#worklog");
const result = document.querySelector("#task-result");
const backButton = document.querySelector("#back-button");

let activeSession = null;
let pollHandle = null;

const handoff = createHandoffUi({
  getSession: () => activeSession,
  onLog: (events) => renderLog(events),
  onChanged: () => refreshSession(),
  onError: (message) => showProcessingError(message),
});

function showHomeError(message) {
  homeError.textContent = message;
  homeError.hidden = false;
}

function showProcessingError(message) {
  processingError.textContent = message;
  processingError.hidden = false;
}

function setBusy(busy) {
  sampleButton.disabled = busy;
  formUpload.disabled = busy;
}

function vaultItem(doc) {
  const item = document.createElement("li");
  const title = document.createElement("strong");
  title.textContent = doc.title;
  const detail = document.createElement("span");
  const pages =
    doc.pages === 0 ? "could not be read" : `${doc.pages} page${doc.pages === 1 ? "" : "s"}`;
  detail.textContent = `${doc.kind} · ${pages}`;
  item.append(title, detail);
  return item;
}

async function loadVault() {
  try {
    const response = await fetch("/api/vault");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "The vault could not be listed.");
    document.querySelector("#vault-summary").textContent =
      data.mine.documents.length === 0
        ? ""
        : `${data.mine.documents.length} document${data.mine.documents.length === 1 ? "" : "s"} saved. Relay reads these for every form you choose.`;
    document
      .querySelector("#vault-list")
      .replaceChildren(...data.mine.documents.map((doc) => vaultItem(doc)));
    const empty = document.querySelector("#vault-empty");
    empty.hidden = data.mine.documents.length > 0;
    empty.textContent =
      "Your vault is empty. Add your documents (ID, bank statement, letters) on the vault page and Relay will read them for every form. Until then it will ask you every question.";
    document.querySelector("#demo-folder").textContent = `Synthetic documents in ${data.demo.folder}/`;
    document
      .querySelector("#demo-vault-list")
      .replaceChildren(...data.demo.documents.map(vaultItem));
  } catch (error) {
    showHomeError(error.message);
  }
}

async function beginSession(body) {
  homeError.hidden = true;
  handoff.reset();
  setBusy(true);
  try {
    const response = await fetch("/api/sessions", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "The PDFs could not be uploaded.");
    activeSession = data.session_id;
    home.hidden = true;
    brief.hidden = false;
    result.hidden = true;
    processingError.hidden = true;
    retryButton.hidden = true;
    worklog.replaceChildren();
    document.querySelector("#task-title").textContent = "Reading your documents";
    pollHandle = window.setInterval(refreshSession, 1200);
    await refreshSession();
  } catch (error) {
    showHomeError(error.message);
  } finally {
    setBusy(false);
  }
}

sampleButton.addEventListener("click", () => {
  const body = new FormData();
  body.set("sample", "true");
  beginSession(body);
});

formUpload.addEventListener("change", () => {
  const form = formUpload.files[0];
  homeError.hidden = true;
  if (!form) return;
  const body = new FormData();
  body.set("form_file", form);
  formUpload.value = "";
  beginSession(body);
});

async function refreshSession() {
  if (!activeSession) return;
  try {
    const response = await fetch(`/api/sessions/${activeSession}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "The session could not be read.");
    renderLog(data.events);
    if (data.status === "ready") {
      window.clearInterval(pollHandle);
      renderBrief(data);
    } else if (data.status === "failed") {
      window.clearInterval(pollHandle);
      showProcessingError(data.error || "Reading failed. Check the work log and retry.");
      retryButton.hidden = false;
      document.querySelector("#status-label").textContent = "Needs attention";
    }
  } catch (error) {
    window.clearInterval(pollHandle);
    showProcessingError(error.message);
  }
}

function renderLog(events) {
  const rows = events.map((event) => {
    const item = document.createElement("li");
    const agent = document.createElement("strong");
    agent.textContent = event.agent;
    const message = document.createElement("span");
    message.textContent = event.message;
    item.append(agent, message);
    item.className =
      event.level === "error"
        ? "log-error"
        : event.level === "warning"
          ? "log-warning"
          : "";
    return item;
  });
  worklog.replaceChildren(...rows);
}

function renderBrief(data) {
  const task = data.task;
  processingError.hidden = true;
  document.querySelector("#status-label").textContent = "Brief ready";
  document.querySelector("#task-title").textContent = task.task;
  document.querySelector("#task-summary").textContent = task.summary;
  document.querySelector("#deadline").textContent =
    task.deadline || "No deadline found — check the form";
  document.querySelector("#deadline-quote").textContent =
    task.deadline_quote ? `“${task.deadline_quote}”` : "";
  document.querySelector("#count-person").textContent = data.counts.person;
  document.querySelector("#count-documents").textContent = data.counts.documents;
  document.querySelector("#count-helper").textContent = data.counts.helper;

  const grouped = new Map();
  for (const field of data.fields) {
    if (!grouped.has(field.section)) grouped.set(field.section, []);
    grouped.get(field.section).push(field);
  }
  const questionBlocks = [...grouped].map(([title, fields]) => {
    const part = document.createElement("section");
    part.className = "question-part";
    const heading = document.createElement("h3");
    heading.textContent = title;
    const list = document.createElement("ol");
    list.className = "question-list";
    for (const field of fields) {
      const item = document.createElement("li");
      const number = document.createElement("span");
      number.className = "question-number";
      number.textContent = `${field.ord}.`;
      const body = document.createElement("div");
      body.className = "question-body";
      const label = document.createElement("span");
      label.className = "question-label";
      label.textContent = field.label;
      body.append(label);
      if (field.value) {
        const answer = document.createElement("strong");
        answer.className = "question-answer";
        answer.textContent = field.value;
        body.append(answer);
      }
      const source = sourceLine(field);
      if (source) {
        const line = document.createElement("span");
        line.className = "question-source";
        line.textContent = source;
        body.append(line);
      }
      const tag = document.createElement("span");
      tag.className = `question-tag tag-${tagKind(field)}`;
      tag.textContent = questionStatus(field);
      item.append(number, body, tag);
      list.append(item);
    }
    part.append(heading, list);
    return part;
  });
  document.querySelector("#questions").replaceChildren(...questionBlocks);
  document.querySelector("#export-link").href = `/api/sessions/${activeSession}/export.pdf`;

  const requested = task.evidence_required.map((entry) => {
    const item = document.createElement("li");
    item.textContent = entry;
    return item;
  });
  document.querySelector("#documents-requested").replaceChildren(...requested);
  const vaultDocs = data.documents.filter((doc) => doc.role === "evidence");
  document.querySelector("#vault-note").textContent =
    vaultDocs.length === 0
      ? "Your vault has no PDFs, so every question will be asked of you."
      : `Relay read ${vaultDocs.length} document${vaultDocs.length === 1 ? "" : "s"} from your vault.`;
  document
    .querySelector("#uploaded-documents")
    .replaceChildren(...vaultDocs.map((doc) => vaultItem({ ...doc, title: doc.filename })));
  result.hidden = false;
  handoff.render(data);
}

function sourceLine(field) {
  if (field.origin === "helper" && field.value) return "Answered by your helper";
  const evidence = field.evidence;
  if (!evidence) return "";
  const quote = evidence.quote ? `: “${evidence.quote}”` : "";
  return `From ${evidence.title}, page ${evidence.page}${quote}`;
}

function tagKind(field) {
  if (field.status === "done") return "done";
  if (field.status === "proposed") {
    return field.evidence?.verified && !field.evidence?.read_from_image ? "found" : "check";
  }
  return field.source === "helper" ? "helper" : "open";
}

function questionStatus(field) {
  if (field.status === "done") return "Answered";
  if (field.status === "proposed") {
    if (field.evidence?.read_from_image) return "Read from a scan — please check";
    return field.evidence?.verified ? "Found in your vault" : "Found — please check";
  }
  if (field.source === "helper") return "Needs another person";
  if (field.source === "documents") return "Not found — you answer";
  return "You answer";
}

retryButton.addEventListener("click", async () => {
  if (!activeSession) return;
  retryButton.disabled = true;
  try {
    const response = await fetch(`/api/sessions/${activeSession}/retry`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Retry could not start.");
    processingError.hidden = true;
    retryButton.hidden = true;
    result.hidden = true;
    document.querySelector("#status-label").textContent = "Reading";
    pollHandle = window.setInterval(refreshSession, 1200);
    await refreshSession();
  } catch (error) {
    showProcessingError(error.message);
  } finally {
    retryButton.disabled = false;
  }
});

document.querySelector("#forget-button").addEventListener("click", async () => {
  if (!activeSession) return;
  if (!window.confirm("Forget this session? Your stored answers and copied documents will be deleted.")) return;
  try {
    const response = await fetch(`/api/sessions/${activeSession}`, { method: "DELETE" });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || "The session could not be forgotten.");
    }
    backButton.click();
  } catch (error) {
    showProcessingError(error.message);
  }
});

backButton.addEventListener("click", () => {
  loadVault();
  window.clearInterval(pollHandle);
  handoff.reset();
  activeSession = null;
  brief.hidden = true;
  home.hidden = false;
});

loadVault();

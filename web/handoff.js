export function createHandoffUi({ getSession, onLog, onChanged, onError }) {
  const panel = document.querySelector("#helper-panel");
  const picker = document.querySelector("#helper-picker");
  const choices = document.querySelector("#helper-choices");
  const pickerError = document.querySelector("#helper-picker-error");
  const lastResult = document.querySelector("#helper-last-result");
  const preview = document.querySelector("#handoff-preview");
  const previewQuestions = document.querySelector("#preview-questions");
  const warning = document.querySelector("#leak-warning");
  const sendButton = document.querySelector("#send-helper");
  const sent = document.querySelector("#helper-sent");
  const link = document.querySelector("#helper-link");
  const linkStatus = document.querySelector("#helper-link-status");
  const cancelButton = document.querySelector("#cancel-helper");
  const review = document.querySelector("#helper-review");
  const answers = document.querySelector("#helper-answers");

  let latest = null;
  let handoffId = null;
  let pollHandle = null;

  function show(step) {
    picker.hidden = step !== "picker";
    preview.hidden = step !== "preview";
    sent.hidden = step !== "sent" && step !== "review";
    review.hidden = step !== "review";
  }

  function stopPolling() {
    window.clearInterval(pollHandle);
    pollHandle = null;
  }

  function fieldLabel(fieldId) {
    const field = latest?.fields.find((entry) => entry.id === fieldId);
    return field ? `${field.ord}. ${field.label}` : "Question";
  }

  async function request(path, body) {
    const response = await fetch(`/api/sessions/${getSession()}${path}`, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "That could not be done.");
    return data;
  }

  function buildPicker(fields) {
    const rows = fields.map((field) => {
      const row = document.createElement("label");
      row.className = "helper-choice";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = String(field.id);
      box.checked = field.source === "helper";
      const text = document.createElement("span");
      text.textContent = `${field.ord}. ${field.label}`;
      row.append(box, text);
      if (field.source === "helper") {
        const note = document.createElement("small");
        note.textContent = "Needs another person";
        row.append(note);
      }
      return row;
    });
    choices.replaceChildren(...rows);
    pickerError.hidden = true;
  }

  function lastOutcome(handoff) {
    if (!handoff) return "";
    if (handoff.status === "approved") return "Your helper's answers were added to your form.";
    if (handoff.status === "rejected") return "You rejected the last helper reply. Nothing was added.";
    if (handoff.status === "cancelled") return "The last helper request was cancelled.";
    return "";
  }

  function render(data) {
    latest = data;
    const open = data.fields.filter((field) => field.status !== "done");
    const active = data.handoffs.find((item) => item.status === "sent" || item.status === "answered");
    panel.hidden = open.length === 0 && !active;
    if (panel.hidden) {
      stopPolling();
      return;
    }
    if (active) {
      handoffId = active.id;
      link.href = new URL(active.url, window.location.origin).href;
      link.textContent = link.href;
      cancelButton.hidden = active.status !== "sent";
      lastResult.hidden = true;
      if (active.status === "sent") {
        linkStatus.textContent = "Waiting for your helper. You can cancel this request before they answer.";
        show("sent");
        startPolling();
      } else {
        showReply(active);
      }
      return;
    }
    stopPolling();
    const outcome = lastOutcome(data.handoffs[0]);
    lastResult.textContent = outcome;
    lastResult.hidden = !outcome;
    buildPicker(open);
    show("picker");
  }

  function showReply(handoff) {
    stopPolling();
    linkStatus.textContent = "Your helper answered. Review the answers before they enter your form.";
    cancelButton.hidden = true;
    const rows = handoff.items.map((item) => {
      const row = document.createElement("div");
      row.className = "reply-item";
      const question = document.createElement("p");
      question.className = "reply-question";
      question.textContent = item.question;
      const answer = document.createElement("p");
      answer.className = item.answer ? "reply-answer" : "reply-answer empty";
      answer.textContent = item.answer || "No answer given";
      row.append(question, answer);
      return row;
    });
    answers.replaceChildren(...rows);
    show("review");
  }

  function renderPreview(data) {
    handoffId = data.id;
    const rows = data.items.map((item) => {
      const row = document.createElement("div");
      row.className = "preview-question";
      const label = document.createElement("label");
      label.htmlFor = `preview-q-${item.field_id}`;
      label.textContent = fieldLabel(item.field_id);
      const box = document.createElement("textarea");
      box.id = `preview-q-${item.field_id}`;
      box.dataset.fieldId = String(item.field_id);
      box.rows = 2;
      box.maxLength = 300;
      box.value = item.question;
      box.addEventListener("input", () => {
        sendButton.disabled = true;
        warning.textContent = "Update the preview to check this exact wording before sending.";
        warning.hidden = false;
      });
      row.append(label, box);
      return row;
    });
    previewQuestions.replaceChildren(...rows);
    const counts = data.stays_with_you;
    document.querySelector("#stays-summary").textContent =
      `${counts.other_questions} other question${counts.other_questions === 1 ? "" : "s"}, ${counts.documents} PDFs and ${counts.pages} pages stay with you.`;
    const flagged = data.items.filter((item) => item.leak).map((item) => fieldLabel(item.field_id));
    warning.textContent = flagged.length
      ? `This wording may reveal one of your other answers (${flagged.join("; ")}). Edit it, then update the preview before sending.`
      : "";
    warning.hidden = flagged.length === 0;
    sendButton.disabled = data.leak_detected;
    show("preview");
  }

  async function prepare(fromEdits) {
    const items = fromEdits
      ? [...previewQuestions.querySelectorAll("textarea")].map((box) => ({
          field_id: Number(box.dataset.fieldId),
          question: box.value,
        }))
      : [...choices.querySelectorAll("input:checked")].map((box) => ({ field_id: Number(box.value) }));
    if (items.length === 0) {
      pickerError.textContent = "Choose at least one question to send.";
      pickerError.hidden = false;
      return;
    }
    try {
      renderPreview(await request("/handoffs", { items }));
    } catch (error) {
      onError(error.message);
    }
  }

  async function send() {
    sendButton.disabled = true;
    try {
      const data = await request(`/handoffs/${handoffId}/send`);
      link.href = new URL(data.url, window.location.origin).href;
      link.textContent = link.href;
      cancelButton.hidden = false;
      linkStatus.textContent = "Waiting for your helper. You can cancel this request before they answer.";
      show("sent");
      startPolling();
      onChanged();
    } catch (error) {
      warning.textContent = error.message;
      warning.hidden = false;
      sendButton.disabled = false;
    }
  }

  function startPolling() {
    stopPolling();
    pollHandle = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/sessions/${getSession()}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "The helper request could not be checked.");
        onLog(data.events);
        const current = data.handoffs.find((item) => item.id === handoffId);
        if (current && current.status !== "sent") {
          latest = data;
          render(data);
        }
      } catch (error) {
        stopPolling();
        onError(error.message);
      }
    }, 1800);
  }

  async function decide(decision) {
    try {
      await request(`/handoffs/${handoffId}/decision`, { decision });
      onChanged();
    } catch (error) {
      onError(error.message);
    }
  }

  async function cancel() {
    try {
      await request(`/handoffs/${handoffId}/cancel`);
      onChanged();
    } catch (error) {
      linkStatus.textContent = error.message;
    }
  }

  document.querySelector("#prepare-helper").addEventListener("click", () => prepare(false));
  document.querySelector("#update-preview").addEventListener("click", () => prepare(true));
  document.querySelector("#change-selection").addEventListener("click", () => {
    if (latest) render(latest);
  });
  sendButton.addEventListener("click", send);
  cancelButton.addEventListener("click", cancel);
  document.querySelector("#approve-helper").addEventListener("click", () => decide("approve"));
  document.querySelector("#reject-helper").addEventListener("click", () => decide("reject"));
  document.querySelector("#copy-helper-link").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(link.href);
      linkStatus.textContent = "Helper link copied.";
    } catch {
      linkStatus.textContent = "Copy was unavailable. Select and copy the link above.";
    }
  });

  return {
    render,
    reset() {
      stopPolling();
      handoffId = null;
      latest = null;
      panel.hidden = true;
      show("picker");
    },
  };
}

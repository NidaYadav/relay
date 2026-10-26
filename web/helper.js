const token = window.location.pathname.split("/").filter(Boolean).at(-1);
const error = document.querySelector("#helper-error");
const form = document.querySelector("#answer-form");
const questions = document.querySelector("#helper-questions");
const success = document.querySelector("#helper-success");

function questionBlock({ number, question }, total) {
  const block = document.createElement("div");
  block.className = "helper-question";
  const label = document.createElement("label");
  label.htmlFor = `answer-${number}`;
  const heading = document.createElement("span");
  heading.className = "eyebrow";
  heading.textContent = total > 1 ? `QUESTION ${number} OF ${total}` : "THE QUESTION";
  const text = document.createElement("span");
  text.className = "helper-question-text";
  text.textContent = question;
  label.append(heading, text);
  const box = document.createElement("textarea");
  box.id = `answer-${number}`;
  box.dataset.number = String(number);
  box.rows = 3;
  box.maxLength = 2000;
  block.append(label, box);
  return block;
}

async function loadPacket() {
  try {
    const response = await fetch(`/api/h/${encodeURIComponent(token)}`);
    const packet = await response.json();
    if (!response.ok) throw new Error(packet.detail || "This link no longer works.");
    questions.replaceChildren(...packet.questions.map((item) => questionBlock(item, packet.questions.length)));
    form.hidden = false;
    document.querySelector("#helper-title").focus();
  } catch (exception) {
    error.textContent = exception.message;
    error.hidden = false;
    document.querySelector("#helper-intro").hidden = true;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.hidden = true;
  const answers = [...questions.querySelectorAll("textarea")].map((box) => ({
    number: Number(box.dataset.number),
    answer: box.value,
  }));
  if (!answers.some((item) => item.answer.trim())) {
    error.textContent = "Answer at least one question before sending.";
    error.hidden = false;
    return;
  }
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch(`/api/h/${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Your answers could not be sent.");
    form.hidden = true;
    document.querySelector("#helper-intro").hidden = true;
    success.textContent = data.message;
    success.hidden = false;
  } catch (exception) {
    error.textContent = exception.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
});

loadPacket();

"use strict";
const messages = document.querySelector("#messages");
const input = document.querySelector("#message");
const send = document.querySelector("#send");
const cancel = document.querySelector("#cancel");
const retry = document.querySelector("#retry");
const editFailed = document.querySelector("#edit-failed");
const statusLine = document.querySelector("#status");
let pending = null;
const pendingKey = "helper-pending-message";
let timezone = "UTC";
function busy(value) {
  send.disabled = value; cancel.disabled = value; input.disabled = value; retry.disabled = value; editFailed.disabled = value;
}
function bubble(text, role) {
  document.querySelector("#welcome")?.remove();
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}
function answer(reply, fresh = false) {
  const node = bubble(reply.text, "assistant");
  if (reply.entries?.length) {
    const list = document.createElement("ul"); list.className = "entries";
    const names = {task: "Задача", reminder: "Напоминание", meeting: "Встреча"};
    for (const entry of reply.entries) {
      const item = document.createElement("li");
      const when = entry.scheduled_at ? new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "medium", timeStyle: "short", timeZone: timezone
      }).format(new Date(entry.scheduled_at)) : (entry.scheduled_on || "Без срока");
      item.textContent = `${names[entry.kind]}: ${entry.title} — ${when}`;
      list.append(item);
    }
    node.append(list);
  }
  if (fresh) document.dispatchEvent(new CustomEvent("assistant-reply", {detail: node.textContent}));
}
async function request(path, options = {}) {
  const response = await fetch(path, {credentials: "same-origin", ...options});
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(typeof body.detail === "string" ? body.detail : "Проверьте параметры запроса.");
    error.status = response.status;
    error.notApplied = response.headers.get("X-Request-Outcome") === "not-applied";
    throw error;
  }
  return body;
}
async function submit(text, repeat = false) {
  busy(true); retry.hidden = true; editFailed.hidden = true; statusLine.textContent = "Обрабатываю…";
  if (!repeat) {
    pending = {request_id: crypto.randomUUID(), text};
    sessionStorage.setItem(pendingKey, JSON.stringify(pending));
    bubble(text, "user");
  }
  // До ответа нового обращения его результат снова неизвестен.
  delete pending.notApplied;
  sessionStorage.setItem(pendingKey, JSON.stringify(pending));
  try {
    const reply = await request("/api/v1/chat/messages", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({request_id: pending.request_id, text: pending.text})
    });
    answer(reply, true); pending = null; sessionStorage.removeItem(pendingKey);
    input.value = ""; statusLine.textContent = "";
  } catch (error) {
    statusLine.textContent = `${error.message} Повтор отправит тот же запрос без дублирования.`;
    retry.hidden = false;
    if (error.notApplied) {
      pending.notApplied = true;
      sessionStorage.setItem(pendingKey, JSON.stringify(pending));
      editFailed.hidden = false;
      statusLine.textContent = `${error.message} Этот запрос не сохранён. Можно повторить отправку или изменить сообщение.`;
    } else {
      delete pending.notApplied;
      sessionStorage.setItem(pendingKey, JSON.stringify(pending));
    }
    if ([400, 403, 409, 422].includes(error.status)) {
      pending = null; sessionStorage.removeItem(pendingKey); retry.hidden = true;
      statusLine.textContent = error.message;
    }
  } finally {
    busy(false);
    // До выяснения результата нельзя заменить запрос новым идентификатором.
    if (pending) { send.disabled = true; cancel.disabled = true; input.disabled = true; }
    else { input.focus(); }
  }
}
document.querySelector("#form").addEventListener("submit", event => {
  event.preventDefault(); const text = input.value.trim(); if (text) submit(text);
});
cancel.addEventListener("click", () => submit("Отмена"));
retry.addEventListener("click", () => submit(pending.text, true));
editFailed.addEventListener("click", () => {
  if (!pending?.notApplied) return;
  input.value = pending.text; pending = null; sessionStorage.removeItem(pendingKey);
  retry.hidden = true; editFailed.hidden = true; busy(false); input.focus();
  statusLine.textContent = "Неотправленный запрос снят. Исправьте сообщение или введите новое.";
});
async function init() {
  busy(true);
  try {
    const capabilities = await request("/api/v1/capabilities");
    const demo = capabilities.ai_mode === "demo";
    document.querySelector("#ai-mode").textContent = demo
      ? "Деморежим: AI и распознавание имитируются локально, без ключей и запросов в OpenAI. Записи сохраняются в настоящую базу."
      : `${capabilities.ai_mode === "groq" ? "Groq" : "OpenAI"}: текст и записанный голос отправляются провайдеру для обработки.`;
    document.querySelector("#demo-help").hidden = !demo;
    timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const session = await request("/api/v1/session", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({timezone})});
    timezone = session.timezone;
    document.querySelector("#zone").textContent = `Часовой пояс: ${timezone}`;
    const history = await request("/api/v1/chat/messages");
    for (const row of history) {
      bubble(row.text, "user"); answer(row.response);
    }
    busy(false); input.focus();
    const stored = sessionStorage.getItem(pendingKey);
    if (stored) {
      pending = JSON.parse(stored);
      if (history.some(row => row.request_id === pending.request_id)) {
        pending = null; sessionStorage.removeItem(pendingKey);
      } else {
        bubble(pending.text, "user"); send.disabled = true; cancel.disabled = true;
        input.disabled = true; retry.hidden = false;
        editFailed.hidden = !pending.notApplied;
        statusLine.textContent = "Остался незавершённый запрос. Повторите отправку для проверки результата.";
      }
    }
  } catch (error) { statusLine.textContent = `${error.message} Обновите страницу для повтора.`; }
}
init();

// Настройка темы остаётся только в текущем браузере.
const themeButton = document.querySelector("#theme-toggle");
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const label = theme === "dark" ? "Светлая тема" : "Тёмная тема";
  themeButton.replaceChildren(document.createTextNode(theme === "dark" ? "☀ " : "☾ "));
  const caption = document.createElement("span"); caption.textContent = label;
  themeButton.append(caption); themeButton.setAttribute("aria-label", `Включить: ${label}`);
}
try { setTheme(localStorage.getItem("orbita-theme") === "light" ? "light" : "dark"); } catch { setTheme("dark"); }
themeButton.addEventListener("click", () => {
  const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  setTheme(theme); try { localStorage.setItem("orbita-theme", theme); } catch { /* Настройка действует до обновления. */ }
});
document.querySelectorAll("[data-prompt]").forEach(button => {
  button.addEventListener("click", () => {
    if (input.disabled) return;
    input.value = button.dataset.prompt; input.focus();
  });
});
input.addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !send.disabled) {
    event.preventDefault(); document.querySelector("#form").requestSubmit();
  }
});

// Chat client. Everything from the server is inserted with textContent, never as HTML.
(function () {
  "use strict";
  const log = document.getElementById("log");
  const form = document.getElementById("ask");
  const input = document.getElementById("question");
  let sessionId = null;
  try { sessionId = sessionStorage.getItem("gg-session"); } catch (e) { sessionId = null; }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function table(columns, rows) {
    const t = el("table");
    const head = el("tr");
    columns.forEach((c) => head.appendChild(el("th", "", c)));
    t.appendChild(head);
    rows.forEach((r) => {
      const tr = el("tr");
      columns.forEach((c) => tr.appendChild(el("td", "", r[c] === null ? "unknown" : String(r[c]))));
      t.appendChild(tr);
    });
    return t;
  }

  function show(answer) {
    const box = el("div", "bot");
    box.appendChild(el("p", "", answer.text));
    (answer.notes || []).forEach((n) => box.appendChild(el("p", "note", n)));
    if (answer.rows && answer.rows.length) box.appendChild(table(answer.columns, answer.rows));
    if (answer.sql) {
      const d = el("details");
      d.appendChild(el("summary", "", "SQL (" + answer.attempts + " attempt" + (answer.attempts === 1 ? "" : "s") + ")"));
      d.appendChild(el("code", "", answer.sql));
      box.appendChild(d);
    }
    log.appendChild(box);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    log.appendChild(el("div", "user", question));
    input.value = "";
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question, session_id: sessionId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      sessionId = data.session_id;
      try { sessionStorage.setItem("gg-session", sessionId); } catch (e) { /* storage unavailable */ }
      show(data);
    } catch (err) {
      log.appendChild(el("div", "bot error", "Request failed: " + err.message));
    }
    log.scrollTop = log.scrollHeight;
  });
})();

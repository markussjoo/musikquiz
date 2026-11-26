(() => {
  const TOKEN_KEY = "musikquiz_admin_token";
  let token = localStorage.getItem(TOKEN_KEY) || "";
  let quizzes = [];
  let selectedQuizId = null;
  let currentQuestions = [];
  let currentSubmissions = [];

  const loginView = document.getElementById("login-view");
  const dashboardView = document.getElementById("dashboard-view");
  const logoutBtn = document.getElementById("logout-btn");
  const loginForm = document.getElementById("login-form");
  const loginError = document.getElementById("login-error");

  const quizSelect = document.getElementById("quiz-select");
  const newQuizForm = document.getElementById("new-quiz-form");
  const qTypeSelect = document.getElementById("q-type");
  const qOptionsWrap = document.getElementById("q-options-wrap");

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str ?? "";
    return div.innerHTML;
  }

  async function api(path, options = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json" },
      options.headers || {}
    );
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(path, Object.assign({}, options, { headers }));
    if (res.status === 401) {
      logout();
      throw new Error("Sessionen har gått ut. Logga in igen.");
    }
    const contentType = res.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      throw new Error((data && data.error) || "Något gick fel.");
    }
    return data;
  }

  function logout() {
    token = "";
    localStorage.removeItem(TOKEN_KEY);
    dashboardView.classList.add("hidden");
    logoutBtn.classList.add("hidden");
    loginView.classList.remove("hidden");
  }

  function getSelectedQuiz() {
    return quizzes.find((q) => q.id === Number(selectedQuizId)) || null;
  }

  function updateShareBox() {
    const quiz = getSelectedQuiz();
    if (!quiz) return;
    const url = `${window.location.origin}/quiz/${quiz.slug}`;
    document.getElementById("share-url").textContent = url;
    document.getElementById("open-link-btn").href = url;
    const toggleBtn = document.getElementById("toggle-active-btn");
    toggleBtn.textContent = quiz.is_active ? "Stäng quiz" : "Öppna quiz";
  }

  async function loadQuizzes(preserveId = null) {
    const data = await api("/api/admin/quizzes");
    quizzes = data.quizzes || [];
    quizSelect.innerHTML = "";

    if (quizzes.length === 0) {
      quizSelect.innerHTML = `<option value="">Inga quiz ännu</option>`;
      selectedQuizId = null;
      return;
    }

    quizzes.forEach((q) => {
      const opt = document.createElement("option");
      opt.value = q.id;
      opt.textContent = `${q.title} (${q.is_active ? "Öppet" : "Stängt"})`;
      quizSelect.appendChild(opt);
    });

    if (preserveId && quizzes.some((q) => q.id === Number(preserveId))) {
      selectedQuizId = Number(preserveId);
    } else {
      selectedQuizId = quizzes[0].id;
    }
    quizSelect.value = selectedQuizId;
    updateShareBox();
    await Promise.all([loadQuestions(), loadSubmissions()]);
  }

  async function loadQuestions() {
    if (!selectedQuizId) return;
    const data = await api(`/api/admin/quizzes/${selectedQuizId}/questions`);
    currentQuestions = data.questions || [];
    document.getElementById("tab-q-count").textContent = currentQuestions.length;
    renderQuestions();
  }

  function renderQuestions() {
    const container = document.getElementById("questions-list");
    container.innerHTML = "";
    if (currentQuestions.length === 0) {
      container.innerHTML = `<div class="card muted">Inga frågor tillagda ännu.</div>`;
      return;
    }

    const typeLabels = {
      artist_song: "Artist + Låt",
      text: "Fritext",
      multiple_choice: "Flerval",
    };

    currentQuestions.forEach((q, idx) => {
      const div = document.createElement("div");
      div.className = "card";
      div.innerHTML = `
        <div class="row" style="justify-content: space-between; align-items: flex-start;">
          <div>
            <div class="question-num">Fråga ${idx + 1} · ${typeLabels[q.question_type] || q.question_type} · ${q.points} p</div>
            <h3 style="margin: 4px 0 6px;">${escapeHtml(q.prompt)}</h3>
            ${q.options && q.options.length ? `<div class="small muted">Alternativ: ${q.options.map(escapeHtml).join(", ")}</div>` : ""}
            <div class="small muted">Facit: <strong style="color: var(--success);">${q.correct_answer ? escapeHtml(q.correct_answer) : "Inget angivet"}</strong></div>
          </div>
          <button class="btn btn-danger btn-sm delete-q-btn" data-id="${q.id}">Ta bort</button>
        </div>
      `;
      container.appendChild(div);
    });

    container.querySelectorAll(".delete-q-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Ta bort den här frågan?")) return;
        await api(`/api/admin/questions/${btn.dataset.id}`, { method: "DELETE" });
        await loadQuestions();
      });
    });
  }

  async function loadSubmissions() {
    if (!selectedQuizId) return;
    const data = await api(`/api/admin/quizzes/${selectedQuizId}/submissions`);
    currentSubmissions = data.submissions || [];
    document.getElementById("tab-s-count").textContent = currentSubmissions.length;
    renderSubmissions();
    renderLeaderboard();
  }

  function renderSubmissions() {
    const container = document.getElementById("submissions-list");
    container.innerHTML = "";
    if (currentSubmissions.length === 0) {
      container.innerHTML = `<div class="card muted">Inga inskickade svar ännu.</div>`;
      return;
    }

    currentSubmissions.forEach((sub) => {
      const card = document.createElement("div");
      card.className = "card";
      const timeStr = new Date(sub.submitted_at).toLocaleString("sv-SE");
      const rowsHtml = sub.answers
        .map(
          (a) => `
          <tr>
            <td><strong>${escapeHtml(a.prompt)}</strong>${a.correct_answer ? `<div class="small muted">Facit: ${escapeHtml(a.correct_answer)}</div>` : ""}</td>
            <td>${a.answer_text ? escapeHtml(a.answer_text) : '<span class="muted">(Inget svar)</span>'}</td>
            <td style="white-space: nowrap;">
              <button class="btn btn-sm ${a.is_correct === true ? "btn-success" : "btn-secondary"} grade-btn"
                      data-ans="${a.id}" data-correct="true" data-pts="${a.max_points}">✓ ${a.max_points}p</button>
              <button class="btn btn-sm ${a.is_correct === false ? "btn-danger" : "btn-secondary"} grade-btn"
                      data-ans="${a.id}" data-correct="false" data-pts="0">✗ 0p</button>
              <input type="number" min="0" max="${a.max_points}" value="${a.awarded_points}"
                     class="pts-input" data-ans="${a.id}"
                     style="width: 62px; padding: 5px 8px; display: inline-block; margin-left: 4px;" />
            </td>
          </tr>
        `
        )
        .join("");

      card.innerHTML = `
        <div class="row" style="justify-content: space-between; margin-bottom: 12px;">
          <div>
            <h3 style="margin-bottom: 2px;">${escapeHtml(sub.username)}</h3>
            <span class="small muted">Inskickad ${escapeHtml(timeStr)}</span>
          </div>
          <span class="badge active">${sub.total_points} / ${sub.max_points} poäng</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fråga</th>
                <th>Deltagarens svar</th>
                <th>Rättning</th>
              </tr>
            </thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        </div>
      `;
      container.appendChild(card);
    });

    container.querySelectorAll(".grade-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api(`/api/admin/answers/${btn.dataset.ans}/grade`, {
          method: "PUT",
          body: JSON.stringify({
            is_correct: btn.dataset.correct === "true",
            awarded_points: Number(btn.dataset.pts),
          }),
        });
        await loadSubmissions();
      });
    });

    container.querySelectorAll(".pts-input").forEach((input) => {
      input.addEventListener("change", async () => {
        const pts = Math.max(0, Number(input.value) || 0);
        await api(`/api/admin/answers/${input.dataset.ans}/grade`, {
          method: "PUT",
          body: JSON.stringify({
            is_correct: pts > 0,
            awarded_points: pts,
          }),
        });
        await loadSubmissions();
      });
    });
  }

  function renderLeaderboard() {
    const tbody = document.getElementById("leaderboard-body");
    tbody.innerHTML = "";
    const sorted = [...currentSubmissions].sort((a, b) => b.total_points - a.total_points);
    if (sorted.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" class="muted">Inga resultat ännu.</td></tr>`;
      return;
    }
    sorted.forEach((s, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${idx + 1}</strong></td>
        <td>${escapeHtml(s.username)}</td>
        <td><strong>${s.total_points}</strong> / ${s.max_points} p</td>
        <td class="muted small">${new Date(s.submitted_at).toLocaleString("sv-SE")}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // Event listeners
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginError.classList.add("hidden");
    try {
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: document.getElementById("pin-input").value }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Fel PIN-kod.");
      token = data.token;
      localStorage.setItem(TOKEN_KEY, token);
      loginView.classList.add("hidden");
      dashboardView.classList.remove("hidden");
      logoutBtn.classList.remove("hidden");
      await loadQuizzes();
    } catch (err) {
      loginError.textContent = err.message;
      loginError.classList.remove("hidden");
    }
  });

  logoutBtn.addEventListener("click", logout);

  quizSelect.addEventListener("change", async () => {
    selectedQuizId = Number(quizSelect.value);
    updateShareBox();
    await Promise.all([loadQuestions(), loadSubmissions()]);
  });

  document.getElementById("toggle-new-quiz-btn").addEventListener("click", () => {
    newQuizForm.classList.toggle("hidden");
  });
  document.getElementById("cancel-new-quiz-btn").addEventListener("click", () => {
    newQuizForm.classList.add("hidden");
  });

  newQuizForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const created = await api("/api/admin/quizzes", {
      method: "POST",
      body: JSON.stringify({
        title: document.getElementById("new-quiz-title").value,
        slug: document.getElementById("new-quiz-slug").value,
        description: document.getElementById("new-quiz-desc").value,
      }),
    });
    newQuizForm.reset();
    newQuizForm.classList.add("hidden");
    await loadQuizzes(created.id);
  });

  document.getElementById("toggle-active-btn").addEventListener("click", async () => {
    const quiz = getSelectedQuiz();
    if (!quiz) return;
    await api(`/api/admin/quizzes/${quiz.id}`, {
      method: "PUT",
      body: JSON.stringify({ is_active: !quiz.is_active }),
    });
    await loadQuizzes(quiz.id);
  });

  document.getElementById("delete-quiz-btn").addEventListener("click", async () => {
    const quiz = getSelectedQuiz();
    if (!quiz || !confirm(`Ta bort "${quiz.title}" och alla dess frågor och svar?`)) return;
    await api(`/api/admin/quizzes/${quiz.id}`, { method: "DELETE" });
    await loadQuizzes();
  });

  document.getElementById("copy-link-btn").addEventListener("click", async () => {
    const url = document.getElementById("share-url").textContent;
    await navigator.clipboard.writeText(url);
    const btn = document.getElementById("copy-link-btn");
    btn.textContent = "Kopierad!";
    setTimeout(() => (btn.textContent = "Kopiera"), 1500);
  });

  qTypeSelect.addEventListener("change", () => {
    qOptionsWrap.classList.toggle("hidden", qTypeSelect.value !== "multiple_choice");
  });

  document.getElementById("add-question-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedQuizId) return;
    const options = document
      .getElementById("q-options")
      .value.split("\n")
      .map((s) => s.trim())
      .filter(Boolean);

    await api(`/api/admin/quizzes/${selectedQuizId}/questions`, {
      method: "POST",
      body: JSON.stringify({
        prompt: document.getElementById("q-prompt").value,
        question_type: qTypeSelect.value,
        options,
        correct_answer: document.getElementById("q-correct").value,
        points: Number(document.getElementById("q-points").value) || 1,
      }),
    });
    e.target.reset();
    qOptionsWrap.classList.add("hidden");
    await loadQuestions();
  });

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const target = btn.dataset.tab;
      ["questions", "submissions", "leaderboard"].forEach((name) => {
        document.getElementById(`tab-${name}`).classList.toggle("hidden", name !== target);
      });
    });
  });

  document.getElementById("refresh-subs-btn").addEventListener("click", loadSubmissions);

  document.getElementById("export-csv-btn").addEventListener("click", async () => {
    if (!selectedQuizId) return;
    const res = await fetch(`/api/admin/quizzes/${selectedQuizId}/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `quiz-${selectedQuizId}-resultat.csv`;
    a.click();
    URL.revokeObjectURL(url);
  });

  // Auto-login if token exists
  if (token) {
    loginView.classList.add("hidden");
    dashboardView.classList.remove("hidden");
    logoutBtn.classList.remove("hidden");
    loadQuizzes().catch(() => {});
  }
})();

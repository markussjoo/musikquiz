(() => {
  const loadingView = document.getElementById("loading-view");
  const errorView = document.getElementById("error-view");
  const errorMessage = document.getElementById("error-message");
  const usernameView = document.getElementById("username-view");
  const quizView = document.getElementById("quiz-view");
  const doneView = document.getElementById("done-view");

  const startForm = document.getElementById("start-form");
  const usernameInput = document.getElementById("username-input");
  const startError = document.getElementById("start-error");

  const quizForm = document.getElementById("quiz-form");
  const questionsContainer = document.getElementById("questions-container");
  const submitError = document.getElementById("submit-error");
  const submitBtn = document.getElementById("submit-btn");

  let currentQuiz = null;
  let currentUsername = "";

  function getTargetSlug() {
    const path = window.location.pathname;
    if (path.startsWith("/quiz/")) {
      return decodeURIComponent(path.replace("/quiz/", "").split("/")[0]);
    }
    const params = new URLSearchParams(window.location.search);
    return params.get("quiz");
  }

  function showOnly(section) {
    [loadingView, errorView, usernameView, quizView, doneView].forEach((el) => {
      el.classList.add("hidden");
    });
    section.classList.remove("hidden");
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function updateProgress() {
    if (!currentQuiz) return;
    const total = currentQuiz.questions.length;
    let answered = 0;

    currentQuiz.questions.forEach((q) => {
      if (q.question_type === "multiple_choice") {
        const checked = quizForm.querySelector(`input[name="q_${q.id}"]:checked`);
        if (checked && checked.value.trim()) answered++;
      } else if (q.question_type === "multi_fields" && Array.isArray(q.options)) {
        const anyFilled = q.options.some((f) => {
          const val = quizForm.querySelector(`input[name="q_${q.id}_${f.key}"]`)?.value.trim() || "";
          return val.length > 0;
        });
        if (anyFilled) answered++;
      } else if (q.question_type === "artist_song") {
        const artist = quizForm.querySelector(`input[name="q_${q.id}_artist"]`)?.value.trim() || "";
        const song = quizForm.querySelector(`input[name="q_${q.id}_song"]`)?.value.trim() || "";
        if (artist || song) answered++;
      } else {
        const val = quizForm.querySelector(`[name="q_${q.id}"]`)?.value.trim() || "";
        if (val) answered++;
      }
    });

    document.getElementById("answered-counter").textContent = `${answered} / ${total} besvarade`;
    const pct = total > 0 ? Math.round((answered / total) * 100) : 0;
    document.getElementById("progress-bar").style.width = `${pct}%`;
  }

  function renderQuestions(questions) {
    questionsContainer.innerHTML = "";
    questions.forEach((q, idx) => {
      const card = document.createElement("div");
      card.className = "question-card";

      let inputHtml = "";
      if (q.question_type === "multiple_choice" && Array.isArray(q.options) && q.options.length > 0) {
        inputHtml = q.options
          .map(
            (opt) => `
            <label class="option-label">
              <input type="radio" name="q_${q.id}" value="${escapeHtml(opt)}" />
              <span>${escapeHtml(opt)}</span>
            </label>
          `
          )
          .join("");
      } else if (q.question_type === "multi_fields" && Array.isArray(q.options) && q.options.length > 0) {
        const fieldsHtml = q.options
          .map((f) => {
            const isYear = f.key === "year";
            const placeholder = isYear
              ? "T.ex. 1984"
              : f.key === "artist"
              ? "T.ex. ABBA"
              : f.key === "title"
              ? "T.ex. Dancing Queen"
              : "Skriv ditt svar...";
            return `
              <div>
                <label class="small muted" for="q_${q.id}_${escapeHtml(f.key)}">${escapeHtml(f.label)} (${f.points || 1} p)</label>
                <input
                  id="q_${q.id}_${escapeHtml(f.key)}"
                  name="q_${q.id}_${escapeHtml(f.key)}"
                  type="text"
                  ${isYear ? 'inputmode="numeric" maxlength="10"' : ""}
                  placeholder="${placeholder}"
                />
              </div>
            `;
          })
          .join("");
        inputHtml = `<div class="grid-2">${fieldsHtml}</div>`;
      } else if (q.question_type === "artist_song") {
        inputHtml = `
          <div class="grid-2">
            <div>
              <label class="small muted" for="q_${q.id}_artist">Artist / Band</label>
              <input id="q_${q.id}_artist" name="q_${q.id}_artist" type="text" placeholder="T.ex. ABBA" />
            </div>
            <div>
              <label class="small muted" for="q_${q.id}_song">Låttitel</label>
              <input id="q_${q.id}_song" name="q_${q.id}_song" type="text" placeholder="T.ex. Dancing Queen" />
            </div>
          </div>
        `;
      } else {
        inputHtml = `
          <input name="q_${q.id}" type="text" placeholder="Skriv ditt svar här..." />
        `;
      }

      card.innerHTML = `
        <div class="question-header">
          <div>
            <div class="question-num">Fråga ${idx + 1}</div>
            <div class="question-prompt">${escapeHtml(q.prompt)}</div>
          </div>
          <span class="badge">${q.points} ${q.points === 1 ? "poäng" : "poäng"}</span>
        </div>
        ${inputHtml}
      `;
      questionsContainer.appendChild(card);
    });

    quizForm.addEventListener("input", updateProgress);
    quizForm.addEventListener("change", updateProgress);
    updateProgress();
  }

  async function loadQuiz() {
    const slug = getTargetSlug();
    const endpoint = slug ? `/api/quizzes/${encodeURIComponent(slug)}` : "/api/quiz/active";
    try {
      const res = await fetch(endpoint);
      const data = await res.json();
      if (!res.ok) {
        errorMessage.textContent = data.error || "Kunde inte ladda quizet.";
        showOnly(errorView);
        return;
      }
      currentQuiz = data;
      document.title = `${data.title} – Musikquiz`;
      document.getElementById("quiz-title").textContent = data.title;
      document.getElementById("quiz-description").textContent = data.description || "";
      document.getElementById("question-count-badge").textContent = `${data.questions.length} frågor`;

      const statusBadge = document.getElementById("quiz-status-badge");
      if (data.is_active) {
        statusBadge.textContent = "Öppet för svar";
        statusBadge.className = "badge active";
      } else {
        statusBadge.textContent = "Stängt";
        statusBadge.className = "badge closed";
        startForm.querySelector("button").disabled = true;
        startError.textContent = "Det här quizet är för närvarande stängt för nya svar.";
        startError.classList.remove("hidden");
      }

      showOnly(usernameView);
    } catch (err) {
      errorMessage.textContent = "Kunde inte nå servern. Försök igen om en stund.";
      showOnly(errorView);
    }
  }

  startForm.addEventListener("submit", (e) => {
    e.preventDefault();
    startError.classList.add("hidden");
    const name = usernameInput.value.trim();
    if (!name) {
      startError.textContent = "Skriv in ett användarnamn för att börja.";
      startError.classList.remove("hidden");
      return;
    }
    currentUsername = name;
    document.getElementById("active-quiz-title").textContent = currentQuiz.title;
    document.getElementById("display-username").textContent = currentUsername;
    renderQuestions(currentQuiz.questions);
    showOnly(quizView);
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  quizForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    submitError.classList.add("hidden");
    submitBtn.disabled = true;
    submitBtn.textContent = "Skickar...";

    const answers = currentQuiz.questions.map((q) => {
      let answerText = "";
      if (q.question_type === "multiple_choice") {
        const checked = quizForm.querySelector(`input[name="q_${q.id}"]:checked`);
        answerText = checked ? checked.value : "";
      } else if (q.question_type === "multi_fields" && Array.isArray(q.options)) {
        const fieldsObj = {};
        q.options.forEach((f) => {
          fieldsObj[f.key] = quizForm.querySelector(`input[name="q_${q.id}_${f.key}"]`)?.value.trim() || "";
        });
        answerText = JSON.stringify({ fields: fieldsObj });
      } else if (q.question_type === "artist_song") {
        const artist = quizForm.querySelector(`input[name="q_${q.id}_artist"]`)?.value.trim() || "";
        const song = quizForm.querySelector(`input[name="q_${q.id}_song"]`)?.value.trim() || "";
        if (artist && song) answerText = `${artist} - ${song}`;
        else answerText = artist || song;
      } else {
        answerText = quizForm.querySelector(`[name="q_${q.id}"]`)?.value.trim() || "";
      }
      return { question_id: q.id, answer_text: answerText };
    });

    try {
      const res = await fetch(`/api/quizzes/${encodeURIComponent(currentQuiz.slug)}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: currentUsername, answers }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Kunde inte skicka in svaren.");
      }
      document.getElementById("done-message").textContent =
        `Tack ${currentUsername}! Ditt svar för "${currentQuiz.title}" är registrerat.`;
      showOnly(doneView);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      submitError.textContent = err.message;
      submitError.classList.remove("hidden");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Skicka in mina svar ✓";
    }
  });

  document.getElementById("new-attempt-btn").addEventListener("click", () => {
    usernameInput.value = "";
    quizForm.reset();
    showOnly(usernameView);
  });

  loadQuiz();
})();

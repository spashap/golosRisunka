// Фремиум-мастер /free. Шаги раскрываются по одному, ожидание остаётся В ТОМ ЖЕ
// документе: object-URL превью, созданный до перехода, после навигации отзывается,
// и на iOS Safari родитель увидел бы битую картинку на самом тревожном экране воронки.
(function () {
  var DRAFT_KEY = "gr_free_draft", DRAFT_TTL = 4 * 3600 * 1000;
  var wiz = document.getElementById("free-wizard");
  if (!wiz) return;
  var steps = Array.prototype.slice.call(wiz.querySelectorAll(".wizard__step"));
  var dots = document.getElementById("free-dots");
  var state = { name: "", age: "", address: "", concern: "", duration: "", text: "" };
  var token = null, objUrl = null;

  // ---------- черновик: мама поздним вечером возвращается на то же место ----------
  function saveDraft() {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ s: state, _ts: Date.now() })); } catch (e) {}
  }
  function restoreDraft() {
    var raw; try { raw = localStorage.getItem(DRAFT_KEY); } catch (e) { return; }
    if (!raw) return;
    var d; try { d = JSON.parse(raw); } catch (e) { return; }
    if (!d._ts || Date.now() - d._ts > DRAFT_TTL) { try { localStorage.removeItem(DRAFT_KEY); } catch (e) {} return; }
    Object.keys(d.s || {}).forEach(function (k) { if (d.s[k]) state[k] = d.s[k]; });
    if (state.name) document.getElementById("f-name").value = state.name;
    ["age", "address", "concern", "duration"].forEach(function (k) {
      if (!state[k]) return;
      var el = wiz.querySelector('input[name="' + k + '"][value="' + state[k] + '"]');
      if (el) el.checked = true;
    });
    if (state.text) document.getElementById("f-text").value = state.text;
    if (state.name && state.age) addressUI();
  }

  function show(i) {
    steps.forEach(function (s) { s.classList.toggle("is-on", +s.dataset.step === i); });
    if (dots) Array.prototype.forEach.call(dots.children, function (d, n) {
      d.classList.toggle("is-active", n <= Math.min(i, 3));
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ---------- обращение: однозначные имена предвыбираем, спорные спрашиваем ----------
  var MALE_A = ["никита","илья","кузьма","лёва","лева","гоша","фома","савва","данила",
    "тёма","тема","дима","вова","миша","паша","гриша","серёжа","сережа","лёша","леша",
    "алёша","алеша","ваня","коля","толя","петя","витя","костя","боря","сева","стёпа",
    "рома","тима","яша","жора","митя","федя","сеня","юра","вася","гена","кеша"];
  var AMBIG = ["саша","женя","валя","мика","бусинка","шура","слава","сима","ника"];
  function guess(name) {
    var n = (name || "").trim().toLowerCase().replace(/ё/g, "е").split(/[\s,(/]+/)[0];
    if (!n || n.length < 3) return null;
    if (AMBIG.indexOf(n) >= 0) return null;
    if (MALE_A.indexOf(n) >= 0) return "он";
    if (!/^[а-я\-']+$/.test(n)) return null;
    if (/[ая]$/.test(n)) return "она";
    if (/[йь]$/.test(n)) return null;
    return "он";
  }
  function addressUI() {
    var field = document.getElementById("f-address-field");
    var label = document.getElementById("f-address-label");
    var g = guess(state.name);
    field.hidden = false;
    if (g && !state.address) {
      state.address = g;
      var el = wiz.querySelector('input[name="address"][value="' + g + '"]');
      if (el) el.checked = true;
    }
    // Заголовок «Пол ребёнка» не используем — это грамматическая настройка.
    label.textContent = g ? ("Обращение в тексте — " + (state.address || g) + ". Можно поменять:")
                          : "Как обращаться к ребёнку в разборе?";
  }

  document.getElementById("f-name").addEventListener("input", function (e) {
    state.name = e.target.value; state.address = ""; addressUI(); saveDraft();
  });

  wiz.addEventListener("change", function (e) {
    var t = e.target;
    if (!t.name) return;
    state[t.name] = t.value;
    saveDraft();
    if (t.name === "age") addressUI();
    if (t.name === "concern") {
      // «Перестал рисовать» переформулирует вопрос; нейтральный путь шаг пропускает.
      var q = document.getElementById("f-dur-q");
      var pron = state.address === "она" ? "она" : "он";
      q.textContent = t.value === "stopped"
        ? window.FREE_CONCERN_STOPPED_Q.replace("{on}", pron) : q.dataset.def || q.textContent;
      renderDurations();
      if (t.value === "neutral") { state.duration = ""; loadSummary(); }
      else show(2);
    }
    if (t.name === "duration") show(3);
  });

  // Подпись четвёртого варианта длительности зависит от тревоги и от обращения.
  function renderDurations() {
    var pron = state.address === "она" ? "она" : "он";
    var ego = state.address === "она" ? "неё" : "него";
    var risoval = state.address === "она" ? "рисовала" : "рисовал";
    wiz.querySelectorAll('#f-duration span[data-raw]').forEach(function (s) {
      var raw = s.dataset.raw;
      if (state.concern === "stopped" && /обычно/.test(raw)) raw = pron + " и раньше " + risoval + " мало";
      s.textContent = raw.replace("{ego}", ego).replace("{on}", pron).replace("{risoval}", risoval);
    });
    var tq = document.getElementById("f-text-q");
    tq.textContent = (tq.dataset.def || tq.textContent).replace("{ego}", state.address === "она" ? "её" : "его");
  }

  wiz.addEventListener("click", function (e) {
    var next = e.target.closest("[data-next]");
    if (next) {
      e.preventDefault();
      var i = +next.dataset.next;
      if (i === 0) {
        var err = document.getElementById("f-err0");
        if (!state.name.trim() || !state.age) {
          err.textContent = "Укажите имя и возраст"; err.hidden = false; return;
        }
        err.hidden = true;
        if (!state.address) state.address = guess(state.name) || "он";
        renderDurations();
        show(1);
      } else if (i === 3) {
        state.text = document.getElementById("f-text").value;
        loadSummary();
      }
      return;
    }
    var skip = e.target.closest("[data-skip]");
    if (skip) { e.preventDefault(); state.text = ""; loadSummary(); }
  });

  // ---------- вывод после вопросов: рендерит СЕРВЕР ----------
  function loadSummary() {
    var fd = new FormData();
    Object.keys(state).forEach(function (k) { fd.append(k === "text" ? "parent_text" : k, state[k]); });
    var box = document.getElementById("f-summary");
    box.innerHTML = "<p class='sub'>Секунду…</p>";
    show(4);
    fetch("/free/summary", { method: "POST", body: fd })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        box.innerHTML = html;
        var up = document.getElementById("f-upload");
        if (up) { token = up.dataset.token; window.FREE_WAIT_HINT = up.dataset.waitHint || ""; bindUpload(); }
        bindNoDrawing();
      })
      .catch(function () { box.innerHTML = "<p class='err'>Не получилось. Обновите страницу.</p>"; });
  }

  // ---------- загрузка: fetch, без навигации ----------
  function bindUpload() {
    var input = document.getElementById("f-file");
    if (!input) return;
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      if (!f) return;
      var err = document.getElementById("f-uperr");
      if (f.size > 15 * 1024 * 1024) {
        err.textContent = "Файл больше 15 МБ — выберите фото поменьше."; err.hidden = false; return;
      }
      err.hidden = true;
      if (f.type && f.type.indexOf("image/") === 0 && f.type !== "image/heic") {
        objUrl = URL.createObjectURL(f);
      }
      var fd = new FormData(); fd.append("file", f);
      input.disabled = true;
      fetch("/free/upload/" + token, { method: "POST", body: fd })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok) {
            input.disabled = false;
            if (res.j.error === "limit") { location.href = "/free/r/" + res.j.token; return; }
            err.textContent = ({
              cap: "Сегодня мы уже разобрали максимум рисунков. Оставьте почту — пришлём ссылку завтра.",
              format: "Формат: JPG, PNG, HEIC или WebP.",
              too_big: "Файл больше 15 МБ.",
              broken: "Файл повреждён или это не фотография."
            })[res.j.error] || "Не получилось загрузить. Попробуйте ещё раз.";
            err.hidden = false;
            return;
          }
          startWait();
        })
        .catch(function () { input.disabled = false; err.textContent = "Сеть недоступна."; err.hidden = false; });
    });
  }

  function bindNoDrawing() {
    var btn = document.getElementById("f-nodraw-btn");
    if (!btn) return;
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var v = document.getElementById("f-nodraw-email").value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) return;
      var fd = new FormData(); fd.append("email", v);
      fetch("/free/email/" + btn.dataset.token, { method: "POST", body: fd })
        .then(function () { document.getElementById("f-nodraw-ok").hidden = false; btn.disabled = true; });
    });
  }

  // ---------- ожидание: честные стадии из поля stage ----------
  function startWait() {
    document.getElementById("free-wizard").hidden = true;
    var box = document.getElementById("free-wait");
    box.hidden = false;
    var photo = document.getElementById("w-photo");
    if (objUrl) { photo.src = objUrl; } else { photo.src = "/free/img/" + token; }
    document.getElementById("w-hint").textContent =
      (window.FREE_WAIT_HINT || "").trim() ||
      "пока смотрим — обратите внимание сами на свой рисунок.";
    document.getElementById("w-link").href = "/free/r/" + token;
    document.getElementById("w-link").textContent = location.origin + "/free/r/" + token;
    document.getElementById("w-email-btn").addEventListener("click", function () {
      var v = document.getElementById("w-email").value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) return;
      var fd = new FormData(); fd.append("email", v);
      fetch("/free/email/" + token, { method: "POST", body: fd });
      this.disabled = true; this.textContent = "Пришлём";
    });
    poll(0);
  }

  function poll(tries) {
    fetch("/free/status/" + token).then(function (r) { return r.json(); }).then(function (s) {
      if (s.status === "done" || s.status === "rejected") { location.href = "/free/r/" + token; return; }
      document.getElementById("w-stage").innerHTML = s.label +
        ' <span class="dots-wait"><i></i><i></i><i></i></span>';
      document.getElementById("w-bar").style.width = Math.round(s.step / s.steps * 100) + "%";
      // После ~90 секунд полосу убираем и говорим прямо.
      if (tries === 45) {
        document.getElementById("w-barwrap").hidden = true;
        document.getElementById("w-stage").hidden = true;
        document.getElementById("w-late").hidden = false;
      }
      if (tries > 240) return;
      setTimeout(function () { poll(tries + 1); }, 2000);
    }).catch(function () { setTimeout(function () { poll(tries + 1); }, 3000); });
  }

  ["f-dur-q", "f-text-q"].forEach(function (id) {
    var el = document.getElementById(id); if (el) el.dataset.def = el.textContent;
  });
  restoreDraft();
})();

// Мастер /free: три экрана, каждый показывается вместо предыдущего.
// Ожидание остаётся В ТОМ ЖЕ документе: object-URL превью, созданный до перехода,
// после навигации отзывается, и на iOS Safari родитель увидел бы битую картинку на
// самом тревожном экране воронки.
(function () {
  var DRAFT_KEY = "gr_free_draft", DRAFT_TTL = 4 * 3600 * 1000;
  var wiz = document.getElementById("free-wizard");
  if (!wiz) return;
  var steps = Array.prototype.slice.call(wiz.querySelectorAll(".wizard__step"));
  var dots = document.getElementById("free-dots");
  var state = { name: "", band: "", address: "", concern: "", duration: "", text: "" };
  var token = null, objUrl = null, current = 0;

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
    ["band", "address", "concern", "duration"].forEach(function (k) {
      if (!state[k]) return;
      var el = wiz.querySelector('input[name="' + k + '"][value="' + state[k] + '"]');
      if (el) el.checked = true;
    });
    if (state.text) document.getElementById("f-text").value = state.text;
    if (state.name) addressUI();
  }

  // У каждого шага свой адрес: «Назад» в браузере возвращает на предыдущий ШАГ,
  // а не выбрасывает со страницы. Именно так это ведёт себя на телефоне, где кнопка
  // «назад» — основной способ исправить ответ.
  var STEP_IDS = ["name", "concern", "when", "result", "wait"];

  function show(i, push) {
    current = i;
    steps.forEach(function (s) { s.classList.toggle("is-on", +s.dataset.step === i); });
    if (dots) Array.prototype.forEach.call(dots.children, function (d, n) {
      d.classList.toggle("is-active", n <= Math.min(i, 2));
    });
    var hash = "#" + (STEP_IDS[i] || "name");
    if (push !== false && location.hash !== hash) {
      history.pushState({ step: i }, "", hash);
    }
    window.scrollTo(0, 0);
  }

  window.addEventListener("popstate", function (e) {
    // Возврат с экрана ожидания к мастеру тоже должен работать.
    var wait = document.getElementById("free-wait");
    if (wait && !wait.hidden) {
      wait.hidden = true;
      document.getElementById("free-wizard").hidden = false;
    }
    var i = (e.state && typeof e.state.step === "number")
      ? e.state.step : STEP_IDS.indexOf((location.hash || "#name").slice(1));
    if (i === 4) return;                 // на экран ожидания «вперёд» не возвращаем
    show(i < 0 ? 0 : i, false);
  });

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
    var line = document.getElementById("f-addr");
    var pick = document.getElementById("f-addr-pick");
    var nm = state.name.trim();
    if (!nm) { line.hidden = true; pick.hidden = true; return; }
    var g = state.address || guess(nm);
    if (g) {
      state.address = g;
      var el = wiz.querySelector('input[name="address"][value="' + g + '"]');
      if (el) el.checked = true;
      // «Миша · он · изменить» — обращение не отдельный шаг.
      document.getElementById("f-addr-text").textContent = nm + " · " + g + " · ";
      line.hidden = false;
      pick.hidden = true;
    } else {
      line.hidden = true;
      pick.hidden = false;   // Саша/Женя — спрашиваем явно
    }
  }

  document.getElementById("f-name").addEventListener("input", function (e) {
    state.name = e.target.value; state.address = ""; addressUI(); saveDraft();
  });
  document.getElementById("f-addr-edit").addEventListener("click", function (e) {
    e.preventDefault();
    document.getElementById("f-addr").hidden = true;
    document.getElementById("f-addr-pick").hidden = false;
  });

  // Слушаем И click: повторный тап по УЖЕ выбранному варианту не вызывает change,
  // и человек, вернувшийся назад, упирался в мёртвую кнопку.
  wiz.addEventListener("click", function (e) {
    var t = e.target.closest('input[type="radio"]');
    if (t && t.name === "concern" && t.checked) pickConcern(t.value);
  });

  wiz.addEventListener("change", function (e) {
    var t = e.target;
    if (!t.name) return;
    state[t.name] = t.value;
    saveDraft();
    if (t.name === "address") { addressUI(); renderDurations(); }
    if (t.name === "concern") pickConcern(t.value);
  });

  function pickConcern(value) {
    state.concern = value;
    saveDraft();
    var q = document.getElementById("f-dur-q");
    var pron = state.address === "она" ? "она" : "он";
    q.textContent = value === "stopped"
      ? window.FREE_CONCERN_STOPPED_Q.replace("{on}", pron) : (q.dataset.def || q.textContent);
    renderDurations();
    // Нейтральный путь: длительности нет, но свободный текст оставляем.
    document.getElementById("f-duration").parentNode.querySelector(".choice").hidden =
      (value === "neutral");
    q.hidden = (value === "neutral");
    show(2);
  }

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
    tq.textContent = (tq.dataset.def || tq.textContent)
      .replace("{ego}", state.address === "она" ? "её" : "его");
    var cq = document.getElementById("f-concern-q");
    cq.textContent = (cq.dataset.def || cq.textContent)
      .replace("его рисунках", (state.address === "она" ? "её" : "его") + " рисунках");
  }

  wiz.addEventListener("click", function (e) {
    var back = e.target.closest("[data-back]");
    if (back) { e.preventDefault(); history.back(); return; }
    var next = e.target.closest("[data-next]");
    if (!next) return;
    e.preventDefault();
    var i = +next.dataset.next;
    if (i === 0) {
      var err = document.getElementById("f-err0");
      if (!state.name.trim() || !state.band) {
        err.textContent = "Заполните имя и возраст"; err.hidden = false; return;
      }
      err.hidden = true;
      if (!state.address) state.address = guess(state.name) || "он";
      renderDurations();
      show(1);
    } else if (i === 2) {
      state.text = document.getElementById("f-text").value;
      loadSummary();
    }
  });

  // ---------- вывод после вопросов: рендерит СЕРВЕР ----------
  function loadSummary() {
    var fd = new FormData();
    Object.keys(state).forEach(function (k) { fd.append(k === "text" ? "parent_text" : k, state[k]); });
    var box = document.getElementById("f-summary");
    box.innerHTML = "<p class='sub'>Секунду…</p>";
    show(3);
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

  // ---------- загрузка: фото и почта одним шагом ----------
  function bindUpload() {
    var input = document.getElementById("f-file");
    var go = document.getElementById("f-go");
    var err = document.getElementById("f-uperr");
    if (!input || !go) return;

    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      if (!f) return;
      if (f.size > 15 * 1024 * 1024) {
        err.textContent = "Фото больше 15 МБ. Снимите ещё раз или выберите файл поменьше.";
        err.hidden = false; input.value = ""; return;
      }
      err.hidden = true;
      var img = document.querySelector("#f-upload img.preview");
      var txt = document.querySelector("#f-upload .fd-text");
      if (f.type && f.type.indexOf("image/") === 0 && f.type !== "image/heic") {
        objUrl = URL.createObjectURL(f);
        if (img) { img.src = objUrl; img.hidden = false; }
      }
      if (txt) txt.textContent = "Фото добавлено";
    });

    go.addEventListener("click", function () {
      var f = input.files && input.files[0];
      var mail = document.getElementById("f-email").value.trim();
      if (!f) { err.textContent = "Сначала добавьте фото рисунка."; err.hidden = false; return; }
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(mail)) {
        err.textContent = "Проверьте почту — на неё придёт копия разбора."; err.hidden = false; return;
      }
      err.hidden = true;
      var fd = new FormData(); fd.append("file", f); fd.append("email", mail);
      go.disabled = true; go.textContent = "Отправляем…";
      fetch("/free/upload/" + token, { method: "POST", body: fd })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok) {
            go.disabled = false; go.textContent = "Разобрать рисунок";
            if (res.j.error === "limit") { location.href = "/free/r/" + res.j.token; return; }
            err.textContent = ({
              cap: "На сегодня разборы закончились. Оставьте почту — пришлём ссылку завтра утром.",
              format: "Не тот формат. Подойдут JPG, PNG, HEIC и WebP.",
              too_big: "Фото больше 15 МБ. Снимите ещё раз или выберите файл поменьше.",
              broken: "Не удалось открыть файл — похоже, это не фотография.",
              email: "Проверьте почту — на неё придёт копия разбора."
            })[res.j.error] || "Не получилось загрузить. Попробуйте ещё раз.";
            err.hidden = false;
            return;
          }
          startWait();
        })
        .catch(function () {
          go.disabled = false; go.textContent = "Разобрать рисунок";
          err.textContent = "Нет связи. Проверьте интернет и попробуйте ещё раз.";
          err.hidden = false;
        });
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
    document.getElementById("free-wait").hidden = false;
    // Своя запись истории и здесь: «назад» с ожидания возвращает к выводу, а не
    // проматывает через два шага.
    history.pushState({ step: 4 }, "", "#wait");
    var photo = document.getElementById("w-photo");
    photo.src = objUrl || ("/free/img/" + token);
    document.getElementById("w-hint").textContent =
      (window.FREE_WAIT_HINT || "").trim() ||
      "пока смотрим — обратите внимание сами на свой рисунок.";
    var link = document.getElementById("w-link");
    link.href = "/free/r/" + token;
    link.textContent = location.origin + "/free/r/" + token;
    poll(0);
  }

  function poll(tries) {
    fetch("/free/status/" + token).then(function (r) { return r.json(); }).then(function (s) {
      if (s.status === "done" || s.status === "rejected") { location.href = "/free/r/" + token; return; }
      document.getElementById("w-stage").innerHTML = s.label +
        ' <span class="dots-wait"><i></i><i></i><i></i></span>';
      document.getElementById("w-bar").style.width = Math.round(s.step / s.steps * 100) + "%";
      // После ~90 секунд полосу убираем: почта уже есть, обещание письма честное.
      if (tries === 45) {
        document.getElementById("w-barwrap").hidden = true;
        document.getElementById("w-stage").hidden = true;
        document.getElementById("w-late").hidden = false;
      }
      if (tries > 240) return;
      setTimeout(function () { poll(tries + 1); }, 2000);
    }).catch(function () { setTimeout(function () { poll(tries + 1); }, 3000); });
  }

  ["f-dur-q", "f-text-q", "f-concern-q"].forEach(function (id) {
    var el = document.getElementById(id); if (el) el.dataset.def = el.textContent;
  });
  restoreDraft();
  // Заменяем текущую запись истории, чтобы первый «назад» с шага 2 вёл на шаг 1,
  // а не на страницу, с которой человек пришёл.
  history.replaceState({ step: 0 }, "", "#name");
})();

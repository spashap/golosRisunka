// Форма заказа: динамические блоки рисунков (до 3), превью фото,
// и ЧЕРНОВИК в localStorage — refresh не теряет введённое (кроме файлов).
(function () {
  var DRAFT_KEY = "gr_order_draft";
  var form = document.getElementById("order-form");
  var blocks = Array.prototype.slice.call(document.querySelectorAll(".drawing-block"));
  var addBtn = document.getElementById("add-drawing");

  // ---------- черновик ----------
  var DRAFT_TTL = 4 * 3600 * 1000;   // черновик живёт 4 часа

  function collectDraft() {
    var data = { _blocks: [], _ts: Date.now() };
    form.querySelectorAll("input, textarea, select").forEach(function (el) {
      if (!el.name || el.type === "file" || el.type === "hidden") return;
      if (el.value) data[el.name] = el.value;
    });
    blocks.forEach(function (b) { if (!b.hidden) data._blocks.push(b.dataset.n); });
    return data;
  }

  var saveTimer = null;
  function saveDraft() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      try { localStorage.setItem(DRAFT_KEY, JSON.stringify(collectDraft())); } catch (e) {}
    }, 300);
  }

  function restoreDraft() {
    var raw;
    try { raw = localStorage.getItem(DRAFT_KEY); } catch (e) { return; }
    if (!raw) return;
    var data;
    try { data = JSON.parse(raw); } catch (e) { return; }
    if (!data._ts || Date.now() - data._ts > DRAFT_TTL) {
      try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
      return;
    }
    // показать блоки рисунков, которые были открыты
    (data._blocks || []).forEach(function (n) {
      var b = document.querySelector('.drawing-block[data-n="' + n + '"]');
      if (b) b.hidden = false;
    });
    // значения — только в пустые поля (серверный ре-рендер с ошибками главнее)
    Object.keys(data).forEach(function (name) {
      if (name === "_blocks" || name === "_ts") return;
      var el = form.querySelector('[name="' + name + '"]');
      if (el && !el.value) el.value = data[name];
    });
  }

  form.addEventListener("input", saveDraft);
  form.addEventListener("change", saveDraft);
  form.addEventListener("submit", function () {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  });

  // ---------- блоки рисунков ----------
  function visibleCount() {
    return blocks.filter(function (b) { return !b.hidden; }).length;
  }
  function refresh() {
    addBtn.hidden = visibleCount() >= blocks.length;
  }

  // обязательные поля блока рисунка: фото, тема, месяц и год
  var addMsg = document.getElementById("add-drawing-msg");

  function blockMissing(block) {
    var n = block.dataset.n;
    var missing = [];
    var file = block.querySelector('input[type="file"]');
    if (!file || !file.files || !file.files.length) missing.push({ label: "фото рисунка", el: file });
    [["_theme", "тема рисунка"], ["_drawn_at_m", "месяц"], ["_drawn_at_y", "год"]].forEach(function (p) {
      var el = block.querySelector('[name="d' + n + p[0] + '"]');
      if (el && !el.value.trim()) missing.push({ label: p[1], el: el });
    });
    return missing;
  }

  function hideAddMsg() { if (addMsg) { addMsg.hidden = true; } }

  addBtn.addEventListener("click", function () {
    // нельзя добавить следующий, пока в предыдущем не заполнено обязательное
    var visible = blocks.filter(function (b) { return !b.hidden; });
    var last = visible[visible.length - 1];
    var missing = blockMissing(last);
    if (missing.length) {
      missing.forEach(function (m) {
        if (m.el) {
          m.el.classList.add("input--error");
          m.el.addEventListener("input", function h() {
            m.el.classList.remove("input--error");
            m.el.removeEventListener("input", h);
            hideAddMsg();
          });
          m.el.addEventListener("change", function h2() {
            m.el.classList.remove("input--error");
            m.el.removeEventListener("change", h2);
            hideAddMsg();
          });
        }
      });
      if (addMsg) {
        addMsg.textContent = "Сначала заполните рисунок " + last.dataset.n + ": " +
          missing.map(function (m) { return m.label; }).join(", ") + ".";
        addMsg.hidden = false;
      }
      return;
    }
    hideAddMsg();
    for (var i = 0; i < blocks.length; i++) {
      if (blocks[i].hidden) { blocks[i].hidden = false; break; }
    }
    refresh();
    saveDraft();
  });

  blocks.forEach(function (block) {
    var rm = block.querySelector(".db-remove");
    if (rm) {
      rm.addEventListener("click", function (e) {
        e.preventDefault();
        block.hidden = true;
        block.querySelectorAll("input, textarea, select").forEach(function (el) {
          el.value = "";
        });
        var img = block.querySelector("img.preview");
        if (img) { img.hidden = true; img.src = ""; }
        refresh();
        saveDraft();
      });
    }

    var fileInput = block.querySelector('input[type="file"]');
    if (fileInput) {
      fileInput.addEventListener("change", function () {
        var img = block.querySelector("img.preview");
        var f = fileInput.files && fileInput.files[0];
        if (!f || !img) return;
        if (f.size > 15 * 1024 * 1024) {
          alert("Файл больше 15 МБ — выберите фото поменьше.");
          fileInput.value = "";
          return;
        }
        var txt = block.querySelector(".fd-text");
        if (f.type && f.type.indexOf("image/") === 0 && f.type !== "image/heic") {
          img.src = URL.createObjectURL(f);
          img.hidden = false;
          if (txt) txt.textContent = "Фото принято: " + f.name;
        } else {
          // HEIC и прочее без браузерного превью — подтверждаем именем файла
          img.hidden = true;
          if (txt) txt.textContent = "Фото принято: " + f.name + " (превью недоступно для этого формата)";
        }
      });
    }
  });

  // ---------- проверка опечаток в email ----------
  var KNOWN = ["mail.ru","gmail.com","yandex.ru","ya.ru","yahoo.com","outlook.com",
    "hotmail.com","icloud.com","bk.ru","list.ru","inbox.ru","rambler.ru",
    "internet.ru","yandex.com","googlemail.com","live.com","me.com","proton.me"];

  function lev(a, b) {
    if (a === b) return 0;
    var m = a.length, n = b.length;
    if (!m || !n) return m || n;
    var row = [];
    for (var j = 0; j <= n; j++) row[j] = j;
    for (var i = 1; i <= m; i++) {
      var prev = row[0]; row[0] = i;
      for (var k = 1; k <= n; k++) {
        var cur = row[k];
        row[k] = Math.min(row[k] + 1, row[k - 1] + 1,
                          prev + (a[i - 1] === b[k - 1] ? 0 : 1));
        prev = cur;
      }
    }
    return row[n];
  }

  function suggestDomain(domain) {
    if (KNOWN.indexOf(domain) !== -1) return null;     // домен известен — ок
    var best = null, bestD = 3;
    KNOWN.forEach(function (d) {
      var dist = lev(domain, d);
      if (dist < bestD || (dist === bestD && best && d.length < best.length)) {
        bestD = dist; best = d;
      }
    });
    return bestD <= 2 ? best : null;                   // расстояние 1-2 = вероятная опечатка
  }

  var emailInput = form.querySelector('[name="email"]');
  var sgBox = document.getElementById("email-suggest");
  var sgVal = document.getElementById("email-suggest-val");
  var sgPending = false;   // есть неразрешённая подсказка — блокируем сабмит
  var sgDismissed = "";    // «оставить как есть» для этого значения

  function checkEmail() {
    if (!emailInput || !sgBox) return;
    var v = emailInput.value.trim().toLowerCase();
    var at = v.indexOf("@");
    sgBox.hidden = true; sgPending = false;
    if (at < 1 || v === sgDismissed) return;
    var fix = suggestDomain(v.slice(at + 1));
    if (fix) {
      sgVal.textContent = v.slice(0, at + 1) + fix;
      sgBox.hidden = false;
      sgPending = true;
    }
  }

  if (emailInput && sgBox) {
    emailInput.addEventListener("blur", checkEmail);
    emailInput.addEventListener("input", function () {
      sgBox.hidden = true; sgPending = false; sgDismissed = "";
    });
    document.getElementById("email-suggest-yes").addEventListener("click", function () {
      emailInput.value = sgVal.textContent;
      sgBox.hidden = true; sgPending = false;
      saveDraft();
    });
    document.getElementById("email-suggest-no").addEventListener("click", function () {
      sgDismissed = emailInput.value.trim().toLowerCase();
      sgBox.hidden = true; sgPending = false;
    });
    form.addEventListener("submit", function (e) {
      checkEmail();
      if (sgPending) {       // опечатка не подтверждена — не отправляем
        e.preventDefault();
        sgBox.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    });
  }

  // защита от двойного сабмита: длинная загрузка фото = нетерпеливый второй клик
  var submitBtn = form.querySelector('button[type="submit"]');
  form.addEventListener("submit", function (e) {
    if (e.defaultPrevented || !submitBtn) return;
    setTimeout(function () {          // после всех других обработчиков
      submitBtn.disabled = true;
      submitBtn.textContent = "Отправляем…";
    }, 0);
  });

  // маяк аналитики: начали заполнять форму (один раз)
  var started = false;
  form.addEventListener("input", function () {
    if (started) return;
    started = true;
    try { navigator.sendBeacon("/track/form-started"); } catch (e) {}
  });

  restoreDraft();
  refresh();
})();

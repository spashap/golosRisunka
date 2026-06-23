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

  // ---------- комбобоксы (тема / материалы) ----------
  // Нативный <input list> + <datalist> на мобильных показывает подсказку, но часто
  // НЕ даёт её выбрать (приходится дописывать слово вручную). Свой выпадающий список:
  // выбор по mousedown (успевает до blur), стрелки/Enter с клавиатуры, свободный ввод сохраняется.
  (function comboboxes() {
    var listEl = null, inputEl = null, idx = -1, committing = false;

    function presetsOf(input) {
      var dl = document.getElementById(input.getAttribute("data-combo"));
      if (!dl) return [];
      return Array.prototype.map.call(dl.querySelectorAll("option"),
        function (o) { return o.value; });
    }
    function close() {
      if (listEl && listEl.parentNode) listEl.parentNode.removeChild(listEl);
      if (inputEl) inputEl.setAttribute("aria-expanded", "false");
      listEl = null; inputEl = null; idx = -1;
    }
    function commit(input, val) {
      committing = true;                       // не переоткрывать список на свой же input-event
      input.value = val;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      committing = false;
      close();
    }
    function open(input) {
      close();
      var q = (input.value || "").trim().toLowerCase();
      var matches = presetsOf(input).filter(function (p) {
        return !q || p.toLowerCase().indexOf(q) !== -1;
      });
      if (!matches.length) return;
      var ul = document.createElement("ul");
      ul.className = "combo-list";
      matches.forEach(function (p) {
        var li = document.createElement("li");
        li.className = "combo-list__item";
        li.textContent = p;
        li.addEventListener("mousedown", function (e) {
          e.preventDefault();                  // удержать фокус и успеть до blur
          commit(input, p);
        });
        ul.appendChild(li);
      });
      var ctl = (input.closest && input.closest(".ctl")) || input.parentNode;
      ctl.style.position = "relative";
      ctl.appendChild(ul);
      listEl = ul; inputEl = input; idx = -1;
      input.setAttribute("aria-expanded", "true");
    }
    function highlight(items) {
      items.forEach(function (it, i) { it.classList.toggle("is-active", i === idx); });
      if (idx >= 0 && items[idx]) items[idx].scrollIntoView({ block: "nearest" });
    }
    function isCombo(el) { return el && el.matches && el.matches("input[data-combo]"); }

    document.addEventListener("focusin", function (e) { if (isCombo(e.target)) open(e.target); });
    document.addEventListener("input", function (e) {
      if (!committing && isCombo(e.target)) open(e.target);
    });
    document.addEventListener("keydown", function (e) {
      if (!listEl || e.target !== inputEl) return;
      var items = listEl.querySelectorAll(".combo-list__item");
      if (e.key === "ArrowDown") { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); highlight(items); }
      else if (e.key === "ArrowUp") { e.preventDefault(); idx = Math.max(idx - 1, 0); highlight(items); }
      else if (e.key === "Enter" && idx >= 0) { e.preventDefault(); commit(inputEl, items[idx].textContent); }
      else if (e.key === "Escape") { close(); }
    });
    document.addEventListener("focusout", function (e) {
      if (e.target === inputEl) setTimeout(close, 150);   // дать mousedown сработать
    });
    document.addEventListener("click", function (e) {
      if (listEl && !listEl.contains(e.target) && e.target !== inputEl) close();
    });
  })();

  restoreDraft();
  refresh();
})();

// Виджет оценки (звёзды + текст) — общий для бесплатного разбора и платного отчёта.
// Отправка без перезагрузки; подпись под звёздами меняется при выборе.
(function () {
  if (window.__grFeedbackInit) return;   // партиал может встретиться дважды
  window.__grFeedbackInit = true;

  var LABELS = {1: "Не помогло", 2: "Мало полезного", 3: "Кое-что подметили",
                4: "Полезно", 5: "Очень точно, узнали ребёнка"};

  document.addEventListener("change", function (e) {
    var inp = e.target;
    if (!inp.matches || !inp.matches(".rate__input")) return;
    var box = inp.closest("[data-feedback-form]");
    var lab = box && box.querySelector("[data-rate-label]");
    if (lab) lab.textContent = LABELS[inp.value] || "";
  });

  document.addEventListener("submit", function (e) {
    var form = e.target.closest && e.target.closest("[data-feedback-form] form");
    if (!form) return;
    e.preventDefault();
    var stars = form.querySelector(".rate__input:checked");
    if (!stars) { form.querySelector(".rate__stars").classList.add("rate__stars--shake"); return; }
    var btn = form.querySelector("button[type=submit]");
    var thanks = form.querySelector("[data-rate-thanks]");
    btn.disabled = true;
    fetch(form.action, { method: "POST", body: new FormData(form) })
      .then(function (r) {
        if (!r.ok) throw new Error("bad");
        if (thanks) thanks.hidden = false;
        btn.textContent = "Обновить оценку";
        var title = form.querySelector(".rate__title");
        if (title) title.textContent = "Ваша оценка";
      })
      .catch(function () { if (thanks) { thanks.hidden = false; thanks.textContent = "Не удалось отправить, попробуйте ещё раз."; } })
      .then(function () { btn.disabled = false; });
  });
})();

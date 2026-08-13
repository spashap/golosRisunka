// Страница готового разбора: оценка интерпретации + email после разбора.
// Плюс поллинг для случая, когда родитель вернулся по ссылке, а разбор ещё делается.
(function () {
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-vote]");
    if (!b) return;
    e.preventDefault();
    var fd = new FormData(); fd.append("vote", b.dataset.vote);
    fetch("/free/vote/" + b.dataset.id, { method: "POST", body: fd });
    var box = b.closest("[data-interp]");
    box.querySelectorAll("button").forEach(function (x) { x.disabled = true; });
    var th = box.querySelector("[data-thanks]"); if (th) th.hidden = false;
  });

  var mail = document.getElementById("f-mail");
  if (mail) {
    document.getElementById("f-mail-btn").addEventListener("click", function () {
      var v = document.getElementById("f-mail-input").value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) return;
      var fd = new FormData(); fd.append("email", v);
      var btn = this; btn.disabled = true;
      fetch("/free/email/" + mail.dataset.token, { method: "POST", body: fd })
        .then(function (r) {
          if (r.ok) document.getElementById("f-mail-ok").hidden = false;
          else btn.disabled = false;
        });
    });
  }

  var wait = document.getElementById("free-wait-page");
  if (wait) {
    (function poll(n) {
      fetch("/free/status/" + wait.dataset.token).then(function (r) { return r.json(); })
        .then(function (s) {
          if (s.status === "done" || s.status === "rejected") { location.reload(); return; }
          document.getElementById("w-stage").innerHTML = s.label +
            ' <span class="dots-wait"><i></i><i></i><i></i></span>';
          document.getElementById("w-bar").style.width =
            Math.round(s.step / s.steps * 100) + "%";
          if (n < 240) setTimeout(function () { poll(n + 1); }, 2000);
        }).catch(function () { if (n < 240) setTimeout(function () { poll(n + 1); }, 3000); });
    })(0);
  }
})();

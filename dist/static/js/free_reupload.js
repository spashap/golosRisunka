// Страница отказа по фото (/free/r/<token>, status=rejected): другое фото на тот же
// токен. Мастера на странице нет, поэтому free.js (он привязан к #free-wizard) не
// подходит — здесь только загрузка; после успеха ждём разбор на той же ссылке.
(function () {
  var up = document.getElementById("f-upload");
  var input = document.getElementById("f-file");
  var go = document.getElementById("f-go");
  var err = document.getElementById("f-uperr");
  if (!up || !input || !go) return;
  var token = up.dataset.token;

  input.addEventListener("change", function () {
    var f = input.files && input.files[0];
    if (!f) return;
    if (f.size > 15 * 1024 * 1024) {
      err.textContent = "Фото больше 15 МБ. Снимите ещё раз или выберите файл поменьше.";
      err.hidden = false; input.value = "";
      if (window.ymGoal) { window.ymGoal("free_file_too_big"); }
      return;
    }
    err.hidden = true;
    var img = up.querySelector("img.preview"), txt = up.querySelector(".fd-text");
    if (f.type && f.type.indexOf("image/") === 0 && f.type !== "image/heic" && img) {
      img.src = URL.createObjectURL(f); img.hidden = false;
    }
    if (txt) txt.textContent = "Фото добавлено";
  });

  go.addEventListener("click", function () {
    var f = input.files && input.files[0];
    var mail = document.getElementById("f-email").value.trim();
    if (!f) { err.textContent = "Сначала добавьте фото рисунка."; err.hidden = false; return; }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(mail)) {
      err.textContent = "Проверьте почту — на неё придёт разбор."; err.hidden = false; return;
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
            cap: "На сегодня разборы закончились. Мы отправили на почту ссылку — вернитесь завтра.",
            format: "Не тот формат. Подойдут JPG, PNG, HEIC и WebP.",
            too_big: "Фото больше 15 МБ. Снимите ещё раз или выберите файл поменьше.",
            broken: "Не удалось открыть файл — похоже, это не фотография.",
            email: "Проверьте почту — на неё придёт разбор.",
            already: "Этот разбор уже в работе — обновите страницу."
          })[res.j.error] || "Не получилось загрузить. Попробуйте ещё раз.";
          err.hidden = false;
          return;
        }
        location.href = "/free/r/" + token;
      })
      .catch(function () {
        go.disabled = false; go.textContent = "Разобрать рисунок";
        err.textContent = "Нет связи. Проверьте интернет и попробуйте ещё раз."; err.hidden = false;
      });
  });
})();

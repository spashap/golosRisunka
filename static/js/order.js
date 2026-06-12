// Форма заказа: добавление/удаление блоков рисунков (до 3) + превью фото.
// Ванильный JS, прогрессивное улучшение — без него форма работает с одним рисунком.
(function () {
  var blocks = Array.prototype.slice.call(document.querySelectorAll(".drawing-block"));
  var addBtn = document.getElementById("add-drawing");

  function visibleCount() {
    return blocks.filter(function (b) { return !b.hidden; }).length;
  }

  function refresh() {
    addBtn.hidden = visibleCount() >= blocks.length;
  }

  addBtn.addEventListener("click", function () {
    for (var i = 0; i < blocks.length; i++) {
      if (blocks[i].hidden) {
        blocks[i].hidden = false;
        break;
      }
    }
    refresh();
  });

  blocks.forEach(function (block) {
    var rm = block.querySelector(".db-remove");
    if (rm) {
      rm.addEventListener("click", function (e) {
        e.preventDefault();
        block.hidden = true;
        // очистить файл и поля скрытого блока, чтобы не ушли на сервер
        block.querySelectorAll("input, textarea, select").forEach(function (el) {
          if (el.type === "file") el.value = "";
          else el.value = "";
        });
        var img = block.querySelector("img.preview");
        if (img) { img.hidden = true; img.src = ""; }
        refresh();
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
        if (f.type && f.type.indexOf("image/") === 0 && f.type !== "image/heic") {
          img.src = URL.createObjectURL(f);
          img.hidden = false;
        }
      });
    }
  });

  refresh();
})();

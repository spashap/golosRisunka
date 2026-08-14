/* Первичная аналитика сайта. Живёт ОТДЕЛЬНО от счётчика Метрики намеренно:
   раньше весь маяк /t/e сидел внутри `{% if metrika_id %}`, и без чужого ID
   собственная аналитика молча выключалась целиком — включая воронку в админке.
   Здесь только свои данные; в Метрику дублируем, если счётчик на странице есть.

   Грузится из <head> БЕЗ defer: страницы (order_success) вызывают window.ymGoal
   в инлайн-скрипте по ходу разбора документа, а defer выполнил бы файл позже.
   Файл маленький и кэшируется — цена этого меньше, чем потерянные цели.

   Что шлём:
     goal    — клики/сабмиты по data-ym-goal / data-ym-goal-submit;
     engaged — первое взаимодействие ИЛИ 15 c видимого пребывания;
     scroll_25|50|75|100 — глубина прокрутки (по одному разу за страницу);
     sec_<имя> — блок [data-track-section] реально был на экране.
   Всегда добавляем `p` (адрес страницы): сам запрос идёт на /t/e, и без этого
   поля в базе выходило бы, что всё на сайте происходит на /t/e.
*/
(function () {
  "use strict";

  var sizeSent = false;

  function beacon(fields) {
    var data = fields || {};
    data.p = location.pathname;
    if (!sizeSent) {
      sizeSent = true;
      // Ширина ЭКРАНА от клиента: user-agent про верстку не знает (iPad в режиме
      // десктопа, узкое окно на ноутбуке) — а ломается всё именно по ширине.
      data.sw = String(window.innerWidth || (screen && screen.width) || 0);
      if ("ontouchstart" in window || navigator.maxTouchPoints > 0) { data.t = "1"; }
    }
    try { navigator.sendBeacon("/t/e", new URLSearchParams(data)); } catch (e) {}
  }
  window.grBeacon = beacon;

  window.ymGoal = function (goal, params) {
    if (!goal) { return; }
    if (window.ym && window.GR_YM_ID) {
      try { ym(window.GR_YM_ID, "reachGoal", goal, params || {}); } catch (e) {}
    }
    beacon({ g: goal });
  };

  // --- Цели по кликам/сабмитам. Делегирование на document: новая кнопка = новый
  //     атрибут data-ym-goal, JS дописывать не нужно (в т.ч. для динамических блоков).
  document.addEventListener("click", function (ev) {
    var el = ev.target.closest && ev.target.closest("[data-ym-goal]");
    if (el) { window.ymGoal(el.getAttribute("data-ym-goal")); }
  }, true);
  document.addEventListener("submit", function (ev) {
    var f = ev.target.closest && ev.target.closest("[data-ym-goal-submit]");
    if (f) { window.ymGoal(f.getAttribute("data-ym-goal-submit")); }
  }, true);

  // --- Вовлечённость: один маяк при ПЕРВОМ из — взаимодействие ИЛИ 15 c ВИДИМОГО
  //     пребывания. Порог совпадает с «отказом» Метрики; фоновые и предзагруженные
  //     вкладки время не копят, поэтому prerender не превращается в посетителя.
  (function () {
    var sent = false, visibleSec = 0, THRESHOLD = 15, tick = null;
    var EVENTS = ["scroll", "wheel", "click", "keydown", "touchstart"];
    function cleanup() {
      EVENTS.forEach(function (e) { document.removeEventListener(e, fire, true); });
      if (tick) { clearInterval(tick); tick = null; }
    }
    function fire() {
      if (sent) { return; }
      sent = true;
      beacon({ engaged: "1" });
      cleanup();
    }
    EVENTS.forEach(function (e) {
      document.addEventListener(e, fire, { capture: true, passive: true });
    });
    tick = setInterval(function () {
      if (document.visibilityState === "visible" && ++visibleSec >= THRESHOLD) { fire(); }
    }, 1000);
  })();

  // --- Глубина прокрутки. Считаем от ПРОКРУЧИВАЕМОГО расстояния, а не от высоты
  //     документа: иначе на коротком экране 100% недостижимы, а на длинном мобильном
  //     первые 25% набегают уже в первом свайпе.
  //     Если страница короче экрана (прокрутки нет) — не шлём НИЧЕГО: «100% прокрутки»
  //     там означало бы «человек ничего не сделал», и глубина перестала бы что-то значить.
  (function () {
    var MARKS = [25, 50, 75, 100], next = 0, ticking = false;
    function scrollable() {
      var h = Math.max(document.body ? document.body.scrollHeight : 0,
                       document.documentElement.scrollHeight);
      return h - window.innerHeight;
    }
    function check() {
      ticking = false;
      var max = scrollable();
      if (max < 200) { return; }              // нечего мерить
      var pct = ((window.pageYOffset || document.documentElement.scrollTop) / max) * 100;
      while (next < MARKS.length && pct >= MARKS[next] - 1) {
        window.ymGoal("scroll_" + MARKS[next]);
        next += 1;
      }
      if (next >= MARKS.length) {
        window.removeEventListener("scroll", onScroll, true);
      }
    }
    function onScroll() {
      if (!ticking) { ticking = true; requestAnimationFrame(check); }
    }
    window.addEventListener("scroll", onScroll, { capture: true, passive: true });
  })();

  // --- Видимость блоков: [data-track-section="имя"] -> цель sec_<имя>.
  //     Требуем ПОЛСЕКУНДЫ на экране и половину блока: на мобильном инерционный
  //     свайп пролетает всю страницу за секунду, и без выдержки «видел цены» означало
  //     бы «пролистал мимо цен».
  (function () {
    if (!("IntersectionObserver" in window)) { return; }
    var DWELL = 500, timers = {};
    function start() {
      var nodes = document.querySelectorAll("[data-track-section]");
      if (!nodes.length) { return; }
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          var name = en.target.getAttribute("data-track-section");
          if (!name) { return; }
          if (en.isIntersecting) {
            if (timers[name]) { return; }
            timers[name] = setTimeout(function () {
              window.ymGoal("sec_" + name);
              io.unobserve(en.target);            // один раз за загрузку страницы
            }, DWELL);
          } else if (timers[name]) {
            clearTimeout(timers[name]);
            timers[name] = null;
          }
        });
      }, { threshold: 0.5 });
      nodes.forEach(function (n) { io.observe(n); });
    }
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", start);
    } else {
      start();
    }
  })();
})();

"""Реестр целей сайта: единственный список того, что мы вообще считаем действием.

ЗАЧЕМ ЭТОТ ФАЙЛ. Цели живут в шаблонах как `data-ym-goal="имя"`, и до сих пор нигде
не было списка: что означает `free_step1`, какие цели важны, а какие — служебный шум.
Хуже того, Метрика показывает конверсию ТОЛЬКО по цели, заведённой в счётчике; пока
цель не создана, вызов `reachGoal` уходит в пустоту. Полсотни целей руками никто не
заводил — значит, в Метрике их не было, и Директу было не на чем учиться.
`scripts/metrika_goals_sync.py` создаёт по этому реестру недостающие цели.

ЧТО ЗАВОДИМ В МЕТРИКУ (`metrika=True`), а что нет. В Метрику идёт только осмысленный
набор: отчёты со ста целями нечитаемы, а на длинном хвосте («листнул карусель»,
«открыл FAQ») решения не принимают. Хвост никуда не пропадает — он и так пишется в
свою базу (`events`) и виден в /admin/actions.

DIRECT. `direct=True` — кандидат в цель автостратегии. Правило Директа: обучение
требует ~10 конверсий в неделю, поэтому оптимизироваться на «покупку» при нашем
объёме нельзя — цель просто не наберёт статистики. Лестница от объёма к деньгам:
`free_summary` -> `free_upload_submit` -> `order_form` -> `purchase`; берём самую
нижнюю (близкую к деньгам) из тех, что реально набирают объём.
"""
from __future__ import annotations

# --- Цели-действия (JS-события). name = то, что стоит в data-ym-goal. ------------
# (name, подпись, группа, в Метрику?, кандидат для Директа?)
ACTIONS: list[tuple[str, str, str, bool, bool]] = [
    # Шапка — на всех страницах
    ("header_order", "Шапка: «Заказать»", "шапка", True, False),
    ("header_login", "Шапка: «Войти»", "шапка", False, False),
    ("header_logo", "Шапка: логотип", "шапка", False, False),
    ("header_nav_examples", "Шапка: примеры", "шапка", False, False),
    ("header_nav_how", "Шапка: как это работает", "шапка", False, False),
    ("header_nav_prices", "Шапка: цены", "шапка", False, False),
    ("header_nav_blog", "Шапка: блог", "шапка", False, False),
    ("header_nav_check", "Шапка: бесплатная проверка", "шапка", True, False),
    ("header_cta_freecheck", "Шапка на /free-check: проверить бесплатно", "шапка", True, False),

    # Лендинг: две двери — платная и бесплатная
    ("landing_hero_order", "Лендинг: первый экран → заказать", "лендинг", True, False),
    ("landing_hero_free", "Лендинг: первый экран → бесплатно", "лендинг", True, False),
    ("landing_cases_free", "Лендинг: из кейсов → бесплатно", "лендинг", True, False),
    ("landing_worry_free", "Лендинг: из блока тревоги → бесплатно", "лендинг", True, False),
    ("landing_faq_open", "Лендинг: раскрыл вопрос FAQ", "лендинг", True, False),
    ("landing_blog_all", "Лендинг: все статьи", "лендинг", False, False),
    ("landing_samples_prev", "Лендинг: карусель примеров ‹", "лендинг", False, False),
    ("landing_samples_next", "Лендинг: карусель примеров ›", "лендинг", False, False),
    ("landing_reviews_prev", "Лендинг: отзывы ‹", "лендинг", False, False),
    ("landing_reviews_next", "Лендинг: отзывы ›", "лендинг", False, False),
    ("landing_reviews_dot", "Лендинг: отзывы точка", "лендинг", False, False),
    ("landing_blog_prev", "Лендинг: карусель блога ‹", "лендинг", False, False),
    ("landing_blog_next", "Лендинг: карусель блога ›", "лендинг", False, False),

    # Фремиум — вход, по которому идёт основной объём
    ("free_step1", "Фремиум: заполнил имя и возраст", "фремиум", True, False),
    ("free_summary", "Фремиум: дошёл до вывода", "фремиум", True, True),
    ("free_add_drawing", "Фремиум: выбрал файл рисунка", "фремиум", True, False),
    ("free_upload_submit", "Фремиум: отправил рисунок", "фремиум", True, True),
    ("free_no_drawing", "Фремиум: сохранил место (без рисунка)", "фремиум", True, False),
    ("free_to_order", "Фремиум: из разбора → к заказу", "фремиум", True, True),
    ("free_vote_yes", "Фремиум: «это про него»", "фремиум", True, False),
    ("free_vote_no", "Фремиум: «не про него»", "фремиум", True, False),
    ("free_retry", "Фремиум: загрузить другое фото", "фремиум", False, False),
    ("free_coloring_again", "Фремиум: принести свой рисунок", "фремиум", False, False),
    ("free_limit_open", "Фремиум: открыл прошлый разбор (лимит)", "фремиум", False, False),
    ("free_back", "Фремиум: шаг назад", "фремиум", False, False),

    # Платная форма и оплата
    ("order_submit", "Заказ: нажал «Оформить»", "заказ", True, False),
    ("order_submit_form", "Заказ: форма отправлена", "заказ", True, True),
    ("order_add_drawing", "Заказ: добавил ещё рисунок", "заказ", False, False),
    ("order_email_fix_yes", "Заказ: принял исправление email", "заказ", False, False),
    ("order_email_fix_no", "Заказ: отклонил исправление email", "заказ", False, False),
    ("checkout_pay", "Оплата: нажал «Оплатить»", "оплата", True, False),
    ("purchase", "ПОКУПКА (с выручкой)", "оплата", True, True),
    ("success_open_cabinet", "После оплаты: открыл кабинет", "оплата", False, False),

    # Кабинет и вход
    ("cabinet_download_pdf", "Кабинет: скачал PDF", "кабинет", True, False),
    ("cabinet_open_report", "Кабинет: открыл отчёт", "кабинет", False, False),
    ("cabinet_free_to_order", "Кабинет: из разбора → к заказу", "кабинет", True, False),
    ("cabinet_open_free", "Кабинет: открыл бесплатный разбор", "кабинет", False, False),
    ("cabinet_compare_soon", "Кабинет: интерес к сравнению («скоро»)", "кабинет", True, False),
    ("cabinet_email_change_soon", "Кабинет: смена email («скоро»)", "кабинет", False, False),
    ("cabinet_order_empty", "Кабинет: заказ из пустого состояния", "кабинет", False, False),
    ("cabinet_logout", "Кабинет: выход", "кабинет", False, False),
    ("login_request_code", "Вход: запросил код", "вход", False, False),
    ("login_verify", "Вход: ввёл код", "вход", False, False),
    ("login_resend", "Вход: выслать код заново", "вход", False, False),
    ("login_recover_open", "Вход: не приходит код", "вход", True, False),
    ("login_recover_submit", "Вход: восстановление по данным ребёнка", "вход", False, False),
    ("login_recover_back", "Вход: назад из восстановления", "вход", False, False),
    ("login_order", "Вход: перешёл к заказу", "вход", False, False),
    ("loginstub_order", "Заглушка входа: к заказу", "вход", False, False),

    # Контент
    ("blogpost_order", "Статья: к заказу", "блог", True, False),
    ("blogpost_sample", "Статья: к примеру отчёта", "блог", True, False),
    ("blogpost_sample_btn", "Статья: кнопка примера", "блог", False, False),
    ("blogpost_back_blog", "Статья: назад в блог", "блог", False, False),
    ("sample_order", "Пример: к заказу", "примеры", True, False),
    ("sample_open_full", "Пример: открыть полный отчёт", "примеры", True, False),
    ("sample_back", "Пример: назад", "примеры", False, False),
    ("error_home", "Ошибка: на главную", "служебное", False, False),

    # Посадочная под платный трафик /free-check. Цель у каждого CTA своя: на холодном
    # трафике важно знать, КАКОЙ блок довёл до мастера, — иначе страницу нечем править.
    ("freecheck_hero_cta", "Проверка: первый экран", "проверка", True, True),
    ("freecheck_cards_cta", "Проверка: кнопка под карточками", "проверка", True, False),
    ("freecheck_steps_cta", "Проверка: кнопка под «как это работает»", "проверка", True, False),
    ("freecheck_nodrawing_cta", "Проверка: «начать без фотографии»", "проверка", True, False),
    ("freecheck_curiosity_cta", "Проверка: «посмотреть по-новому»", "проверка", True, False),
    ("freecheck_final_cta", "Проверка: финальная кнопка", "проверка", True, False),

    # Сбои и отказы. Заводим в Метрику намеренно: по такой цели строится сегмент,
    # а к сегменту — записи Вебвизора, то есть можно СМОТРЕТЬ, как человек упирается.
    ("order_block_incomplete", "Заказ: не пустила своя же проверка", "сбои", True, False),
    ("order_file_too_big", "Заказ: фото больше 15 МБ", "сбои", True, False),
    ("order_blocked_email_typo", "Заказ: отправку остановила опечатка в email", "сбои", True, False),
    ("order_draft_restored", "Заказ: вернулся к брошенной форме", "сбои", True, False),
    ("free_file_too_big", "Фремиум: фото больше 15 МБ", "сбои", True, False),
    ("free_upload_no_file", "Фремиум: нажал «разобрать» без фото", "сбои", True, False),
    ("free_upload_bad_email", "Фремиум: не принята почта", "сбои", True, False),
    ("free_upload_network_error", "Фремиум: обрыв связи при загрузке", "сбои", True, False),
    ("free_wait_late", "Фремиум: ждёт дольше 90 секунд", "сбои", True, False),
    ("free_wait_gave_up", "Фремиум: ожидание истекло", "сбои", True, False),

    # Глубина прокрутки (static/js/track.js)
    ("scroll_25", "Прокрутка 25%", "глубина", True, False),
    ("scroll_50", "Прокрутка 50%", "глубина", True, False),
    ("scroll_75", "Прокрутка 75%", "глубина", True, False),
    ("scroll_100", "Прокрутка до конца", "глубина", True, False),
]

# --- Блоки страниц: data-track-section="имя" -> цель sec_<имя> -------------------
# Отвечают на вопрос «до какого блока лендинга человек доскроллил», которого у нас
# не было вообще: engaged — да/нет, и всё.
# Порядок = порядок на странице: по нему админка строит «до какого блока дочитали».
SECTIONS: list[tuple[str, str]] = [
    ("hero", "Лендинг 1: первый экран"),
    ("more_than_drawing", "Лендинг 2: «Больше чем рисунок»"),
    ("whats_inside", "Лендинг 3: что внутри отчёта"),
    ("how_we_read", "Лендинг 4: как мы читаем рисунок"),
    ("cases", "Лендинг 5: «Например, такие ситуации»"),
    ("samples", "Лендинг 6: примеры отчётов"),
    ("no_myths", "Лендинг 7: «Бережно, не гадания»"),
    ("how", "Лендинг 8: как это работает"),
    ("trust", "Лендинг 9: почему можно доверять"),
    ("prices", "Лендинг 10: цены"),
    ("worry", "Лендинг 11: блок тревоги (дверь во фремиум)"),
    ("faq", "Лендинг 12: вопросы"),
    ("blog", "Лендинг 13: статьи"),
    ("article", "Статья блога: тело статьи"),
    # Посадочная /free-check — свой порядок блоков, префикс fc_.
    ("fc_hero", "Проверка 1: первый экран"),
    ("fc_cards", "Проверка 2: карточки «что заинтересовало»"),
    ("fc_how", "Проверка 3: как это работает"),
    ("fc_nodrawing", "Проверка 4: «нет рисунка под рукой»"),
    ("fc_curiosity", "Проверка 5: «а если ничего не беспокоит»"),
    ("fc_trust", "Проверка 6: без страшных выводов"),
    ("fc_final", "Проверка 7: финальный призыв"),
]

# --- Цели-страницы (type=url). Просмотр страницы — тоже конверсия, и его нельзя
# получить из reachGoal: на странице заказа человек может ничего не нажать. -------
# (идентификатор, подпись, условие «URL содержит», в Директ?)
URL_GOALS: list[tuple[str, str, str, bool]] = [
    # ⚠️ Условие «/free/» СО СЛЕШЕМ намеренно: подстрока «/free» ловила бы ещё и
    # /free-check, и цель молча считала бы посадочную за вход в мастер.
    ("page_free", "Открыл бесплатный разбор (/free/)", "/free/", False),
    ("page_free_check", "Открыл посадочную «Бесплатная проверка»", "/free-check", True),
    ("page_order", "Открыл форму заказа (/order)", "/order", True),
    ("page_checkout", "Дошёл до оплаты (/pay/)", "/pay/", False),
    ("page_success", "Страница «заказ принят»", "/order/success/", False),
]

# Динамические имена: суффикс подставляется в шаблоне. В Метрику не заводим (их
# сотни и они множатся с каждой статьёй), но админке нужно уметь их сворачивать.
DYNAMIC_PREFIXES: list[tuple[str, str]] = [
    ("landing_sample_open_", "Лендинг: открыл пример отчёта"),
    ("landing_price_order_", "Лендинг: заказ из блока цен"),
    ("landing_blog_open_", "Лендинг: открыл статью"),
    ("blog_open_", "Блог: открыл статью"),
    ("free_concern_", "Фремиум: что зацепило"),
    ("sec_", "Досмотрел до блока"),
]


def section_goals() -> list[tuple[str, str, str, bool, bool]]:
    """Блоки как обычные цели-действия: sec_<имя>."""
    return [(f"sec_{key}", label, "глубина", True, False) for key, label in SECTIONS]


def metrika_actions() -> list[tuple[str, str]]:
    """(идентификатор, подпись) — то, что должно существовать в счётчике."""
    return [(n, label) for n, label, _grp, in_metrika, _d
            in ACTIONS + section_goals() if in_metrika]


def direct_targets() -> list[tuple[str, str]]:
    """Кандидаты в цель автостратегии Директа, от объёма к деньгам."""
    return [(n, label) for n, label, _g, _m, d in ACTIONS if d]


def label_for(goal: str) -> str:
    """Человеческая подпись цели для админки; динамические — сворачиваются в группу."""
    for name, label, _g, _m, _d in ACTIONS + section_goals():
        if name == goal:
            return label
    for prefix, label in DYNAMIC_PREFIXES:
        if goal.startswith(prefix):
            return f"{label}: {goal[len(prefix):]}"
    return goal


def group_for(goal: str) -> str:
    for name, _label, grp, _m, _d in ACTIONS + section_goals():
        if name == goal:
            return grp
    for prefix, _label in DYNAMIC_PREFIXES:
        if goal.startswith(prefix):
            return "динамические"
    return "прочее"

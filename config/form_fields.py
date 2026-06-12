"""Конфиг полей формы заказа (spec §5: рендер и валидация — по конфигу).

Менять состав полей = править этот файл. type: text | textarea | ym | select.
type "ym" = два числовых селекта «месяц + год» (input type=month отвергнут
заказчиком: в части браузеров требует ввода названия месяца текстом).
years_back — глубина списка лет от текущего года.
К каждому рисунку — свой блок DRAWING_FIELDS; данные ребёнка — один блок CHILD_FIELDS.
"""

CHILD_FIELDS = [
    {"key": "name", "label": "Имя ребёнка", "type": "text", "required": True,
     "placeholder": "Алиса"},
    {"key": "gender", "label": "Пол", "type": "select", "required": True,
     "options": [("ж", "Девочка"), ("м", "Мальчик")]},
    {"key": "birth_ym", "label": "Месяц и год рождения", "type": "ym", "required": True,
     "years_back": 18,
     "hint": "Нужен, чтобы оценивать навыки относительно возраста"},
]

DRAWING_FIELDS = [
    {"key": "drawn_at", "label": "Когда нарисован (месяц и год)", "type": "ym",
     "required": True, "years_back": 8,
     "hint": "Поможет отслеживать развитие со временем"},
    {"key": "theme", "label": "Что было задано / тема рисунка", "type": "text",
     "required": True, "placeholder": "Свободная тема / нарисовать семью / персонаж мультфильма"},
    {"key": "materials", "label": "Чем рисовал(а)", "type": "text", "required": False,
     "placeholder": "Фломастеры, карандаши, краски…"},
    {"key": "mood", "label": "Настроение во время рисования", "type": "text",
     "required": False, "placeholder": "Спокойное, увлечённое, торопилась…"},
    {"key": "time_spent", "label": "Сколько времени рисовал(а)", "type": "text",
     "required": False, "placeholder": "Примерно 20 минут"},
    {"key": "noticed", "label": "Что бросилось вам в глаза", "type": "textarea",
     "required": False, "placeholder": "Например: впервые нарисовала глаза с ресницами"},
    {"key": "extra", "label": "Дополнительный контекст", "type": "textarea",
     "required": False, "placeholder": "Всё, что считаете важным рассказать"},
]

# письмо/«куда прислать отчёт»
EMAIL_FIELD = {"key": "email", "label": "Email для отчёта", "type": "email",
               "required": True, "placeholder": "you@example.com"}


def context_to_story(child: dict, drawing: dict) -> str:
    """Поля формы → свободный текст «истории» для промпта (тот же формат,
    что родители давали в тестах)."""
    lines = [
        f"Имя художника: {child.get('name', '')}",
        f"Пол: {child.get('gender', '')}",
        f"Месяц/год рождения: {child.get('birth_ym', '')}",
        f"Дата рисунка: {drawing.get('drawn_at', '')}",
        f"Тема рисунка: {drawing.get('theme', '')}",
    ]
    optional = [("Материалы", "materials"), ("Настроение", "mood"),
                ("Время рисования", "time_spent"),
                ("Что бросилось в глаза родителю", "noticed"),
                ("Дополнительно", "extra")]
    for label, key in optional:
        if drawing.get(key):
            lines.append(f"{label}: {drawing[key]}")
    return "\n".join(lines)

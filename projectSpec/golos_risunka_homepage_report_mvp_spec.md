# Голос рисунка — MVP Homepage + Report Template Improvement Spec

**Audience:** Claude Code / implementation agent  
**Product:** golosrisunka.ru  
**Scope:** MVP conversion improvement for homepage + low-risk report template add-ons  
**Priority:** high  
**Version:** 1.0

---

## 0. Core instruction for Claude Code

You are responsible for implementation quality, layout, responsive design, code cleanliness, and integration into the existing project.

The marketing message and Russian copy in this document are controlled copy. Do **not** freely rewrite user-facing Russian text. You may only adjust punctuation/spacing if needed for layout or typography, and only when meaning is unchanged.

There are two different instruction levels:

1. **Report template changes = APPLY.**  
   These are required MVP add-ons. Implement exactly as static/template additions. Do not change the report engine, scoring logic, per-section generation, or analysis logic.

2. **Homepage changes = STRONG DIRECTION, not a hardcoded apply command.**  
   Use this spec as the intended message, section priority, and copy. You may arrange the page design yourself so it fits the current style and codebase, but preserve the message and Russian copy as much as possible.

---

## 1. Product positioning to implement

The product must no longer feel like only “analysis of a child drawing”.

Primary positioning:

> Спокойный персональный отчёт о развитии ребёнка по его рисункам — без диагнозов, с понятными занятиями для дома.

The front page must communicate four parent benefits:

1. **Calm:** no scary interpretations, no fake diagnosis.
2. **Understanding:** what is visible in the drawing and age-stage skills.
3. **Pride:** visible strengths of the child.
4. **Action:** simple home activities for parents.

Core product logic to show everywhere:

> Видимая деталь рисунка → спокойное объяснение → простое занятие для дома

Do not sell trauma detection, hidden emotions, family problems, diagnosis, or “secret meaning of colors”.

---

# PART A — REPORT TEMPLATE ADD-ONS

## A1. Implementation tone: APPLY

Implement these report changes as required.

Do **not** change:

- scoring algorithm;
- report generation engine;
- per-child/per-drawing generated analysis sections;
- category calculation;
- existing report cover structure;
- existing conclusion logic;
- existing footer/legal line.

Only add constant/static template blocks.

Expected result: existing reports become safer and clearer for parents, especially around scores like 6/10 or 7/10.

---

## A2. Add short score explanation box near “Сводные оценки”

### Placement

In every generated PDF report, add a small explanation box immediately after the **“Сводные оценки”** list/table and before the first detailed section.

If layout constraints require it, place it directly under the score table on the same page, or at the top of the next page before “Разбор по направлениям”.

### Visual direction

- calm info box;
- no red/warning styling;
- use existing brand colors / soft background;
- compact, readable, parent-friendly;
- should not look like legal disclaimer or medical warning.

### Exact Russian copy

```text
Как читать оценки

Оценки относятся к конкретному рисунку или серии рисунков, а не к ребёнку «в целом». Средний балл не означает проблему — иногда направление просто меньше видно в выбранном сюжете. Подробнее — в разделе «Как читать оценки в отчёте» в конце PDF.
```

---

## A3. Add final appendix page: “Как читать оценки в отчёте”

### Placement

Add a new constant page near the end of every report.

Preferred placement:

1. generated conclusion;
2. new appendix page “Как читать оценки в отчёте”;
3. standard report footer/contact/legal line.

If the current PDF layout has strict footer behavior, ensure the appendix page includes the same footer style as other pages.

### Page break

Start this appendix on a new page.

### Exact Russian copy

```text
Как читать оценки в отчёте

Оценки помогают быстро увидеть, какие навыки ярче проявились в конкретном рисунке или серии рисунков. Это не оценка ребёнка как личности, не школьная отметка и не психологическая диагностика.

Важно понимать:

• Оценка относится к рисунку, а не к ребёнку в целом.
Например, если на рисунке изображено одно дерево без людей или персонажей, направление «сюжет и взаимодействие» может быть выражено слабее. Это не значит, что ребёнок плохо общается.

• Средняя оценка не означает проблему.
Она может означать, что навык проявился частично или что выбранная тема дала меньше материала для наблюдения.

• Высокая оценка показывает сильную сторону именно в этой работе.
Например, уверенная линия, крупный масштаб, аккуратное закрашивание или продуманная композиция могут говорить о хорошо проявленных графических навыках.

• Один рисунок не показывает всё развитие ребёнка.
Более точную картину даёт серия рисунков за разные периоды, особенно если сохранять работы с датами.

• Главная цель отчёта — не поставить балл, а подсказать, что уже хорошо получается и какие простые занятия можно попробовать дома.

Этот отчёт — спокойное образовательное наблюдение за видимыми навыками в рисунке. Он не заменяет консультацию специалиста, если у родителей есть серьёзные вопросы о состоянии, поведении или развитии ребёнка.
```

---

## A4. Report acceptance criteria

Report template change is complete only when:

- every generated PDF includes the short score explanation box near “Сводные оценки”;
- every generated PDF includes the final appendix page;
- page numbering/footer still looks correct;
- no text overlaps, clipping, broken page breaks, or orphan headers;
- the report still clearly says it is educational observation, not medical/psychological diagnosis;
- existing report content remains intact;
- existing examples still generate successfully.

Recommended manual QA:

- generate at least one report with 1 drawing;
- generate at least one report with 2–3 drawings;
- inspect the page with “Сводные оценки”;
- inspect the final appendix page;
- verify the appendix does not look like an error, legal warning, or scary disclaimer.

---

# PART B — HOMEPAGE IMPROVEMENT

## B1. Implementation tone: STRONG DIRECTION

The homepage is already warm and usable. Do not rebuild from zero unless easier technically.

Improve it strategically:

- keep the soft family/child-development visual style;
- keep navigation, examples, steps, reviews, trust, price, FAQ, blog if useful;
- make the first screen and first half of the page much clearer about the real product value;
- show the output/report more strongly, not only the input/drawings;
- make “not diagnosis / no myths” a visible trust advantage, not only a footer/FAQ disclaimer.

Claude Code may choose final layout, but should follow the priority and copy below.

---

## B2. Recommended section order

Recommended homepage order after revision:

1. Header/navigation.
2. Hero: clear promise + CTA + report/output visual.
3. “Что внутри отчёта” high-value block.
4. Mini-report logic block: visible detail → explanation → activity.
5. Real examples / report carousel.
6. “Без мифов и страшных трактовок” trust block.
7. How it works.
8. Parent reviews.
9. Trust/guarantee/privacy.
10. Pricing.
11. FAQ.
12. Blog.
13. Footer.

This order is not mandatory if design constraints suggest a better arrangement, but the first 4 items must appear early on the page, before pricing.

---

## B3. Header

Current header is acceptable.

Keep:

- logo: “Голос рисунка”;
- nav links: Примеры, Как это работает, Цены, Блог;
- login link;
- CTA.

Recommended CTA text:

```text
Получить отчёт
```

No need to mention AI in header or homepage.

Do not claim human expert review unless the business actually provides it.

---

## B4. Hero block

### Message goal

The hero must answer in 5 seconds:

- What is this?
- What do I get?
- Will it scare me?
- Why is it worth 2999 ₽?

### Replace current poetic hero as the main sales message

The phrase “У каждого рисунка есть голос. Услышьте его.” may remain as a small brand line or visual accent, but should not be the main H1 for cold traffic.

### Exact hero H1

```text
Поймите, что показывает рисунок ребёнка — спокойно и без диагнозов
```

### Exact hero lead

```text
Персональный PDF-отчёт на 6–7 страниц: сильные стороны ребёнка, 8 направлений развития, объяснения по деталям рисунка и простые занятия для дома.
```

### Exact secondary text under lead

```text
Без страшных трактовок по цветам. Без «скрытых диагнозов». Только видимые навыки, возрастной этап и понятные рекомендации для родителей.
```

### Primary CTA

```text
Получить отчёт — 2999 ₽
```

### Hero note / microcopy

Replace “PDF за час” as the leading value. Speed is useful, but it should not make the product feel cheap.

Use:

```text
1–3 рисунка · обычно готов в течение часа · ничего специально рисовать не нужно
```

### Hero trust chips / badges

Use some or all of these badges near the CTA or report mockup:

```text
6–7 страниц
8 направлений
Занятия для дома
Без диагнозов
Рисунки видите только вы
Возврат 7 дней
```

### Hero visual direction

Current hero uses polaroid drawing cards with score badges. This is warm, but it shows mostly the **input**.

Recommended hero visual should show the **output**:

- a PDF/report mockup or stacked pages;
- one visible cover page with child drawing;
- small preview of score table or report section;
- badges: “6–7 страниц”, “8 направлений”, “занятия для дома”.

Child drawing polaroids can remain as secondary decoration, but the report must be visually central.

---

## B5. Add high block: “Что внутри отчёта”

### Purpose

Make 2999 ₽ feel justified. Cold traffic must understand this is not a short “interpretation”, but a structured personalized report.

### Exact title

```text
Что внутри персонального отчёта
```

### Exact subtitle

```text
Это не короткая расшифровка рисунка, а спокойный разбор на 6–7 страниц с понятными выводами и занятиями.
```

### Exact feature list

```text
• 1–3 рисунка одного периода
• Возраст, материалы и контекст рисования
• 8 направлений развития с оценками
• Объяснения, привязанные к видимым деталям рисунка
• Короткие занятия для родителей после каждого направления
• Рекомендации: что поддержать дальше
• PDF на почту + личный кабинет
```

### Design direction

Use cards/checklist/report-preview layout. Do not hide this content inside a carousel.

---

## B6. Add mini-report logic block

### Purpose

This is the strongest proof of product logic. It shows that the service does not make mystical interpretations. It connects visible detail to explanation and practical action.

### Exact title

```text
Как строится вывод в отчёте
```

### Exact subtitle

```text
Каждое наблюдение должно быть связано с тем, что действительно видно в рисунке.
```

### Exact example copy

```text
Видимая деталь
Персонаж нарисован крупно, линии уверенные, исправлений почти нет.

Что это показывает
В этом рисунке хорошо проявлены уверенность исполнения и работа с масштабом.

Что попробовать дома
Дать большой лист и предложить нарисовать героя непрерывной линией — 10 минут без оценки результата.
```

### Exact closing line

```text
Так устроен отчёт: не общие фразы, а наблюдение → объяснение → простое действие.
```

### Design direction

Recommended layout:

- 3 connected cards;
- arrows between them;
- or vertical timeline on mobile.

Do not make this look like medical diagnosis or psychological testing.

---

## B7. Update examples section

Current examples carousel is useful. Keep it, but improve section framing.

### Recommended title

```text
Посмотрите, как выглядит отчёт
```

### Recommended subtitle

```text
Откройте реальные примеры: внутри — рисунок, контекст, оценки, объяснения и задания для родителей.
```

### Add score explanation near examples

Add small note under score bars/cards or under the carousel:

```text
Оценки относятся к конкретному рисунку, а не к ребёнку в целом. Средний балл не означает проблему — иногда направление просто меньше видно в выбранном сюжете.
```

### Design direction

The report cards should communicate depth, not only scores.

If possible, each example card should visually hint at:

- drawing;
- child age;
- 2–3 score bars;
- short insight;
- “Как развивать” / activity cue;
- open full example CTA.

Current report cards can stay, but consider adding one small “занятие” line to each card if available.

---

## B8. Add trust block: “Без мифов и страшных трактовок”

### Purpose

This should be a major conversion/trust section. Russian-speaking parents often know scary myths about children’s drawings. The product should clearly separate itself from fake diagnosis.

### Exact title

```text
Без мифов и страшных трактовок
```

### Exact subtitle

```text
Мы не ищем скрытые диагнозы по цветам и символам. Мы смотрим на видимые навыки и возрастной этап рисунка.
```

### Exact two-column copy

Left column title:

```text
Мы не делаем
```

Left column items:

```text
• не ставим диагнозы по рисунку
• не говорим, что чёрный цвет означает депрессию
• не ищем «скрытые травмы» по одному изображению
• не оцениваем личность ребёнка
```

Right column title:

```text
Мы делаем
```

Right column items:

```text
• смотрим на видимые элементы рисунка: линию, форму, детали, композицию, сюжет и движение руки
• учитываем возраст и контекст
• показываем сильные стороны и зоны роста
• даём простые занятия для дома
```

### Design direction

This block should feel calming, not defensive. Avoid red warning icons. Use soft check/cross or “нет/да” cards.

---

## B9. How it works section

Current section is good. Update copy slightly to match positioning.

### Exact title

```text
Как это работает
```

### Exact subtitle

```text
Три шага — и персональный отчёт у вас на почте.
```

### Step 1

Title:

```text
Загрузите рисунки
```

Text:

```text
Подойдёт 1–3 рисунка, которые ребёнок уже нарисовал. Ничего специально рисовать не нужно.
```

### Step 2

Title:

```text
Добавьте короткий контекст
```

Text:

```text
Возраст, материалы, тема и что было задано — форма занимает 2–3 минуты.
```

### Step 3

Title:

```text
Получите PDF-отчёт
```

Text:

```text
Обычно в течение часа. Отчёт придёт на почту и будет доступен в личном кабинете.
```

---

## B10. Reviews section

Current review structure is acceptable.

Design recommendation:

- keep the rotating quote format if it works well on mobile;
- consider making the strongest anxiety-relief quote visible first, not hidden in rotation.

Strongest existing quote to show first:

```text
«Сын месяц рисовал только чёрной ручкой, я успела напридумывать себе всякого. Отчёт спокойно показал, что он сейчас осваивает контур — и правда, через месяц вернулись цвета.»
```

Important legal/credibility note:

If these are not real reviews from actual testers/customers, do not present them as real customer testimonials. Either replace with verified real reviews or label appropriately as closed testing / sample feedback only.

---

## B11. Trust/guarantee block

Current trust block is good. Keep the three ideas:

- refund;
- privacy;
- honest observations.

Recommended copy refinement.

### Exact section title

```text
Почему нам можно доверять
```

### Card 1

Title:

```text
Возврат денег
```

Text:

```text
Если отчёт не понравился, напишите в течение 7 дней — вернём оплату без лишних вопросов.
```

### Card 2

Title:

```text
Рисунки видите только вы
```

Text:

```text
Работы ребёнка не публикуются, не используются в рекламе и не передаются третьим лицам.
```

### Card 3

Title:

```text
Наблюдения по видимым деталям
```

Text:

```text
Каждый вывод должен быть связан с тем, что видно в рисунке. Это образовательное наблюдение, а не диагностика.
```

---

## B12. Pricing section

MVP must focus on the single-period report. The future progress report can remain as “скоро”, but should not compete with MVP CTA.

### Exact section title

```text
Выберите отчёт
```

### Exact subtitle

```text
Для старта доступен отчёт по 1–3 рисункам одного периода. Отчёт о развитии во времени появится позже.
```

### Main product card

Title:

```text
Отчёт по рисункам
```

Subtitle:

```text
1–3 рисунка одного периода
```

If using discount price, ensure it is legally/ethically true. If the old price is not a real previous/current price, use launch wording instead.

Recommended launch price display:

```text
Цена на запуске: 2999 ₽
```

Feature list:

```text
• Персональный PDF на 6–7 страниц
• Единый отчёт по 1–3 рисункам
• 8 направлений развития с оценками и объяснениями
• Занятия для родителей после каждого направления
• PDF на почту + личный кабинет
• Возврат денег в течение 7 дней
```

CTA:

```text
Заказать отчёт — 2999 ₽
```

### Future product card

Keep as secondary/disabled.

Title:

```text
Отчёт о развитии во времени
```

Badge:

```text
скоро
```

Subtitle:

```text
Сравнение рисунков «тогда и сейчас»
```

Feature list:

```text
• 2 набора рисунков с интервалом от 6 месяцев
• Динамика по каждому из 8 направлений
• Что изменилось и что развивать дальше
• PDF на почту + личный кабинет
```

Disabled note:

```text
Появится после запуска MVP
```

---

## B13. FAQ updates

Keep useful existing FAQ items. Add/adjust the following items.

### FAQ: age

Question:

```text
Какой возраст ребёнка подходит?
```

Answer:

```text
От 3 до 12 лет. Отчёт учитывает возрастной этап развития рисунка: то, что типично для трёх лет, оценивается иначе, чем для девяти.
```

### FAQ: what to send

Question:

```text
Что нужно прислать?
```

Answer:

```text
Фото 1–3 рисунков, которые ребёнок уже нарисовал, и короткие ответы о контексте: возраст, материалы, тема, было ли задание. Ничего специально рисовать не нужно.
```

### FAQ: speed

Question:

```text
Как быстро придёт отчёт?
```

Answer:

```text
Обычно в течение часа после оплаты. PDF придёт на почту и будет доступен в личном кабинете.
```

### FAQ: diagnosis

Question:

```text
Это психологическая диагностика? Это не диагноз?
```

Answer:

```text
Нет, это не диагноз. Это образовательное наблюдение за навыками, которые видны в рисунке: линия, форма, детали, композиция, сюжет, контроль движений и возрастной этап. Мы не делаем выводов о психологическом состоянии ребёнка по одному рисунку.
```

### FAQ: scores

Question:

```text
Что означают оценки 6/10, 8/10 или 9/10?
```

Answer:

```text
Оценки относятся к конкретному рисунку или серии рисунков, а не к ребёнку в целом. Средний балл не означает проблему. Иногда направление просто меньше видно в выбранном сюжете — например, если на рисунке один объект и нет персонажей.
```

### FAQ: generic/template concern

Question:

```text
Как понять, что отчёт не общий шаблон?
```

Answer:

```text
В отчёте выводы должны быть привязаны к конкретным деталям рисунка: линии, композиции, цветовым решениям, деталям, сюжету, материалам и возрасту ребёнка. Именно поэтому мы просим не только фото, но и короткий контекст.
```

### FAQ: worrying drawing

Question:

```text
А если рисунок меня тревожит?
```

Answer:

```text
Отчёт поможет спокойно посмотреть на видимые признаки рисунка и отделить наблюдения от популярных мифов. Но если вас серьёзно беспокоит состояние, поведение или безопасность ребёнка, лучше обратиться к профильному специалисту — отчёт не заменяет консультацию.
```

### FAQ: refund

Question:

```text
А если отчёт мне не понравится?
```

Answer:

```text
Напишите нам в течение 7 дней — вернём деньги без лишних вопросов.
```

### FAQ: privacy

Question:

```text
Кто увидит рисунки моего ребёнка?
```

Answer:

```text
Только вы. Рисунки не публикуются, не используются для рекламы и не передаются третьим лицам.
```

---

## B14. Blog section

Current blog carousel is useful for SEO and warming cold traffic. Keep it.

Recommended title remains acceptable:

```text
Разбираемся в детском рисунке
```

Subtitle:

```text
Спокойные ответы на частые родительские вопросы — в нашем блоге.
```

Do not place the blog above the main offer, report preview, or price. Blog is secondary conversion support.

---

## B15. SEO/meta copy

Update page title and metadata if available in templates.

### Recommended title tag

```text
Голос рисунка — отчёт о развитии ребёнка по рисункам
```

### Recommended meta description

```text
Персональный PDF-отчёт по детским рисункам: 8 направлений развития, объяснения по деталям рисунка и занятия для родителей. Без диагнозов и страшных трактовок.
```

### Recommended Open Graph title

```text
Поймите рисунок ребёнка спокойно и без диагнозов
```

### Recommended Open Graph description

```text
Загрузите 1–3 рисунка и получите персональный PDF-отчёт: сильные стороны, 8 направлений развития, объяснения и простые занятия для дома.
```

---

## B16. Design principles

Use design to make the service feel:

- warm;
- trustworthy;
- parent-friendly;
- educational;
- not medical;
- not mystical;
- not cheap/AI-generic.

Avoid:

- dark clinical design;
- red alert/warning style;
- overuse of psychology symbols;
- scary trauma/fear visuals;
- making scores the dominant visual without explanation.

Prefer:

- report mockups;
- soft paper/card visuals;
- child drawing thumbnails;
- calm badges;
- checklist cards;
- visible “inside the report” previews;
- strong mobile readability.

---

## B17. Mobile requirements

On mobile, above the fold should include:

- clear H1;
- one-sentence value proposition;
- primary CTA;
- at least one trust cue: “без диагнозов” or “возврат 7 дней”;
- some visual proof of report output, not only drawings.

Important content should not be hidden only inside horizontal carousels.

Carousel controls must remain usable on mobile.

---

## B18. Analytics suggestions

Keep existing Yandex goals where possible. Add new goals for new conversion-critical elements if analytics infrastructure supports it.

Suggested goal names:

```text
landing_hero_order
landing_report_inside_view
landing_mini_logic_view
landing_antimyth_view
landing_sample_open
landing_price_order_snapshot
landing_faq_scores_open
landing_faq_diagnosis_open
```

Do not break existing data-ym-goal attributes unless necessary.

---

# PART C — COPY GOVERNANCE

## C1. Do not use these claims

Do not add claims like:

```text
узнайте скрытые страхи ребёнка
выявим травму по рисунку
поймём психологическое состояние ребёнка
узнайте, что ребёнок не говорит словами
диагностика личности по рисунку
чёрный цвет означает тревогу/депрессию
рисунок семьи показывает реальные отношения в семье
```

These are outside the ethical/product boundary.

---

## C2. Safe language to use

Use phrases like:

```text
образовательное наблюдение
видимые навыки
возрастной этап
сильные стороны
зоны роста
простые занятия для дома
без диагнозов
без страшных трактовок
наблюдение по деталям рисунка
```

---

## C3. AI wording

Do not proactively mention AI on the homepage unless legal/product policy requires it.

Also do not claim “human psychologist reviews every report” unless that is actually true.

Safe neutral wording:

```text
персональный отчёт
выводы привязаны к деталям рисунка
образовательное наблюдение
```

---

# PART D — FINAL ACCEPTANCE CHECKLIST

## D1. Report template

Must pass:

- [ ] short score explanation box added near “Сводные оценки”;
- [ ] final appendix page added to every report;
- [ ] existing report generation still works;
- [ ] no engine/scoring logic changed;
- [ ] PDF layout is clean;
- [ ] footer/legal language remains visible;
- [ ] sample reports regenerate correctly.

## D2. Homepage

Must pass:

- [ ] hero clearly sells personal 6–7 page report, not only “drawing analysis”;
- [ ] first screen includes calm/non-diagnosis message;
- [ ] report output is visually shown high on page;
- [ ] “Что внутри отчёта” appears before pricing;
- [ ] visible detail → explanation → activity block appears before pricing;
- [ ] anti-myth / no diagnosis block appears before or near trust section;
- [ ] examples still open full sample reports;
- [ ] pricing focuses on MVP snapshot report;
- [ ] progress report remains secondary/soon;
- [ ] FAQ includes score explanation;
- [ ] page works well on mobile;
- [ ] no fake psychological promises added.

---

## E. Summary for implementation

The current product quality is stronger than the old homepage message. The homepage must show that the buyer receives a structured personal development report, not a quick mystical interpretation of a drawing.

The report itself is already strong enough for MVP. Do not rebuild it now. Add only the required score explanation box and final appendix page, because they reduce parent anxiety and protect the product ethically.

The winning message:

> Видимая деталь рисунка → спокойное объяснение → простое занятие для дома


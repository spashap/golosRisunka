# Handoff — "Voice of the Drawing" product philosophy 2.3 (for the English version)

**Audience:** whoever builds/adapts the English-language version of the product.
**Purpose:** transfer the *new* product concept that the Russian site (golosrisunka.ru) moved to in this work cycle, so the English version can adopt the same philosophy rather than the old one.
**Source of truth (RU codebase):** prompt `pipeline/prompt.py` (PROMPT_VERSION 4.0), schema `pipeline/schema.py`, linter `pipeline/lint.py`, report template `templates/report.html`, landing `templates/landing.html` + `app/routes.py` (FAQ/meta/JSON-LD), admin texts `config/report_texts.json`. Task specs: `projectSpec/pipe-change/task1*.md`, `task2-landing-pivot.md`. Current-state audit: `CURRENT_REPORT_STATE.md`.

---

## 0. The one-paragraph version

The product analyzes a child's drawings (1–3, one period) and returns a warm, personal PDF that reads **the child as a person** through the drawing — their character, themes, inner world, mood, interests — and tells the parent **how to understand and support them**. Drawing skills are still covered, but as *support*, not the point. Any psychological/emotional reading is allowed **only** inside a strict "safe frame" (attribution + hypothesis + visible detail + return-to-the-child). The whole site (hero → sections → FAQ → samples) must *deliver* that promise, and position us as **careful and methodical — not fortune-tellers**.

---

## 1. Why this exists (the pivot)

The original report was technically good and warm but described **only drawing skills** (motor control, colour, composition, technique) and nothing about the child as a person. It failed real target mothers. Verbatim feedback that drove the change:

> "The report doesn't change — it stays an analysis of drawing skills. Motor skills, imagination, but no more. That's not interesting to most parents. I'd be disappointed for that money. Parents want to understand what's in the child's soul, their psychological state — and drawings are the main thing that can help with that. But you don't use it. All the development tips are about drawing. 99% of parents do NOT want to raise an artist."

Root cause: in removing pseudo-psychology (diagnosing by colour/symbols) we over-corrected into "pure skills" and threw out exactly what the parent pays for — the feeling that their child was understood as a person.

**North star:** a parent reads the report and feels *"This is about MY child — who they are, their soul — not about how they hold a pencil. I'm understood. This is worth paying for."*

---

## 2. ⚠️ Market caveat — READ BEFORE ADAPTING

The Russian pivot deliberately leans into **more** psychological interpretation than EU/US norms, because the Russian audience expects and wants depth (the constraint there is *trust*, not regulation).

**For the English version (US/UK/EU) this is the single biggest thing to recalibrate.** Anglophone markets are far more sensitive about psychological claims regarding children, and the legal/ethical bar is higher. Recommended posture for English:

- Keep the **safe frame (Section 4) airtight** — it is non-negotiable in English, not optional polish.
- Consider **dialing zone-3 down** (less "mood/psychological register", more "themes, interests, what the child chooses to express"). The zone-2 content (character through choices, worlds & themes, how to connect/support) is the safe, high-value core and travels well. Zone-3 (emotional/psychological reading) is the risky part — keep it lighter, always framed, always "ask the child."
- Make **"educational observation, not a diagnosis"** ironclad and prominent (positive-identity wording, see Section 9), and keep the "if you're seriously worried, see a professional" line.
- Avoid anything that could read as clinical assessment of a minor. "We reveal what the child *expresses*" — never "we detect hidden problems/traumas."

Treat Sections 3–9 as the *concept*; translate the *intent*, then tune the zone-3 intensity to your market's risk tolerance.

---

## 3. The three zones (how content is balanced)

- **Zone 1 — drawing skills** (motor, colour, technique, composition). SUPPORT, not the point. Keep short and modest.
- **Zone 2 — personality through the child's choices** (which worlds/themes draw them; what their choices of line, colour, density, subject may say about temperament, interests, inner world; how to understand & support the *child*). **This is the centre of the product.**
- **Zone 3 — emotional/psychological interpretation** (mood, emotional register, themes). Allowed **only** in the safe frame. This is where the report gives the parent "soul" — and the riskiest zone (see Section 2).

Target mix: personality-led directions lead; skills support. Zone-3 present but always framed.

---

## 4. The safe frame (the spine — nothing in zone 3 ships without it)

Any statement about a child's emotion, mood, state, temperament, or character is allowed **only when all four hold at once**:

1. **Attribution** — attributed to a named tradition/author, not asserted by us. *"In the projective tradition (Machover, 1949) this is associated with…", "according to Lowenfeld…"* — never "this means". Attribution must be to a **real** tradition/author; never invent sources. **Vary the source** (don't repeat one name > ~2× per report; a generic, name-free attribution like "in the practice of reading children's drawings this is often read as…" is a valid frame).
2. **Hypothesis, not verdict** — "may suggest", "is sometimes associated with", "can be read as", "looks like". Never "the child has anxiety", "this means…".
3. **Anchored to a visible detail** — the interpretation springs from a concrete element actually visible in *this* drawing.
4. **Return to the child** — ends with an invitation to check: *"best to ask [name] herself what's happening with this character and where it's flying"* and/or *"one drawing can't tell you if this is stable or a one-day mood — a series shows more clearly."*

**Worked example (the gold-standard tone):**
> "In the projective tradition (Machover, 1949), a densely dark background is sometimes associated with experiencing strong emotions. Here a warm bird is flying *through* that sky — read this way, it looks like an image of light passing through something difficult. This is a hypothesis, not a conclusion: it's best to ask Lisa herself what's happening with her bird and where it's flying."

---

## 5. Always forbidden (the frame does NOT rescue these)

- Bare diagnosis / state-as-fact: "the child has anxiety/depression", "the drawing shows the child is unhappy".
- Catastrophizing / scary readings: "serious problem", "see a doctor urgently", "hidden trauma".
- Diagnosing hidden problems/traumas from a photo. (We reveal what the child **expresses**, never "we detect hidden problems".)
- "Fix/cure/solve a problem." We help **understand and support**, never treat.
- Fortune-telling by colour/symbol ("black = depression", "red = aggression").
- Command tone ("buy", "you must"). Use "you could / you might try".
- Fate-as-fact ("will become an artist/designer", "has the makings of a writer", "this profession suits them").
- Fake testimonials / fake clients (see Section 8).

---

## 6. The report structure (sections, in order)

The model returns **data only** (strict JSON); the template owns all presentation. Schema (`pipeline/schema.py`):

| Field | What it is |
|---|---|
| `child` `{name, age_display}` | name shown as "First L." (first name + initial) |
| `context_summary` | 1–3 sentences paraphrasing what the parent told us (theme, materials, circumstances) |
| `introduction` | warm, image-rich opening tied to what's visible; neutral description; frames it as educational observation |
| **`about_child`** | **the heart** — a narrative portrait paragraph: which worlds/themes draw the child, temperament/approach via visible choices, what matters to them. Top-level synthesis (NOT a retell of the mood dimension). |
| `dimensions[]` | the 7 directions (below), each `{key, title, score 1–10, observation, research_note, activities[]}` |
| **`understanding_recommendations[]`** | ~half the value: how to **understand & connect** with the child — questions to ask, what to notice in their themes, support phrases. NOT about drawing technique. |
| `art_recommendations[]` | the other (smaller) half: creative activities, materials, what to be inspired by |
| `specialists[]` `{area, reason}` | optional — type of specialist as a "if you want to go deeper" **resource**, never alarm; must include a **non-art** option when content warrants (see Section 7c) |
| `development_directions[]` `{title, text}` | optional — **life-wide** growth directions, 3 layers (see Section 7d) |
| `conclusion` | warm close about the *child*; no trait/personality-as-fact claims |
| `insufficient_input` / `insufficient_reason` | refusal branch for unusable input (validated separately — does NOT require the other fields) |

### The 7 directions (keys are fixed; first four lead, last three support and are shorter)

| # | key | RU title | EN suggested | Zone | Measures |
|---|-----|----------|-------------|------|----------|
| 1 | `world_and_themes` | Мир и темы рисунка | World & themes | 2 (lead) | which worlds/subjects the child chooses by their own will → interests, imagination |
| 2 | `character_in_line_color` | Характер в линии и цвете | Character in line & colour | 2 (+a bit of 3) | what execution choices (bold/cautious line, pressure, density, scale) may say about temperament — **frame required** |
| 3 | `mood_and_expression` | Настроение и выразительность | Mood & expression | 3 | emotional register read from the visible, in the **full** safe frame (the main "depth" carrier; strictest framing) |
| 4 | `story_and_characters` | История и герои | Story & characters | 2 | plot, characters, who's centred → view of world/people (no "unsociable" verdicts) |
| 5 | `creativity` | Креативность и воображение | Creativity & imagination | 1/2 | originality, authorial solutions, departure from template |
| 6 | `technique_and_materials` | Техника и владение материалом | Technique & materials | 1 (support) | technique, colour, composition, neatness — kept compact |
| 7 | `fine_motor` | Моторика и детализация | Fine motor & detail | 1 (support) | fine motor control, precision, detailing |

---

## 7. Key mechanics

### a) Scoring (1–10) — honest, age-relative, varied (not flattering)
- The score is about the **drawing/series**, not the child as a person, and always **relative to what's typical for the age** (5–6 typical, 7–8 notable, 9–10 rare/striking, 3–4 below typical, 1–2 barely present). A 4-year-old and a 9-year-old get genuinely different maps.
- **Score variety is required**: the map must NOT be a flat wall of identical 9s — that reads as flattery and *lowers* trust. A real map looks like 9/8/9/8/7/8/9. This is variety, **not** forced lows: if a direction is genuinely a 9, give it a 9 — never shave a strong axis to comply. Go below 7 only where there's a real visible reason, explained kindly as a growth zone.
- Every score must be justified in its `observation` via a concrete visible detail.

### b) Recommendations split in two
Half about **understanding/connecting** with the child (questions to ask, what to notice, support phrases), half **creative activities** (smaller). The old product was ~all art technique — that was the core complaint.

### c) Specialists as a resource (not alarm)
When the drawing gives reason, name a *type/area* of specialist as "if you'd like to go deeper", tied to a visible detail. **Must not default to only an art teacher** after a whole personality portrait. Add a **non-art** option matched to what showed (e.g. strong narrative/inner-world themes → child psychologist working with projective methods, framed as "to understand her inner world better"; strong speech/communication → speech/neuro specialist). Always opportunity, never "something's wrong."

### d) Development directions = life-wide (not "art careers")
Each point in 3 layers: (1) a **trait from the portrait**; (2) **how to grow that trait in life, beyond drawing** (tell stories, discuss books/films about hard choices, keep a "worlds journal"…); (3) **broad fields + careers strictly "as an example"**, in the frame. Hard rule for layer 3: "for example/as an example" + plural/varied ("often feeds an interest in…", "such children are often drawn to…") + tied to a visible trait + field-first, careers as examples within it. Banned: "has the makings of X", "profession Y suits them", "will become Z". Keep art as *one* field, never the only one. Section heading: "Where to grow the child's strengths"; framing note: "not a prediction of who the child will become — a hint of which direction may be joyful to grow in. The named fields are examples, not a forecast."

### e) The "fog" / honest upsell
By **one** drawing you genuinely can't separate a stable trait from a one-day mood. So interpretive sections (esp. zone 3) for a single drawing naturally leave that question open ("a series across different days would show more precisely"). This is a feature, not a weakness — and it's the honest basis for the upsell (send more drawings → clearer picture). The model does **not** write sales lines; those are injected separately (next item).

### f) Admin-controlled end-of-report texts (pass-through, no logic)
`config/report_texts.json`, read at render time, lets a non-dev edit the blocks appended to the end of the report:
- **3 upsell texts**, one each for orders of 1 / 2 / 3 drawings (pipeline picks by drawing count). Empty = nothing shown.
- **disclaimer** (main + per-drawing-count add-on, e.g. for 1 drawing: "this is one moment, not the full picture") + a **free text block**.
Principle: changes in one place, no code. The English version should mirror this so marketing/legal can tune end-of-report copy without deploys.

---

## 8. The linter (programmatic backstop — concept to replicate)

The prompt alone isn't 100% (sampling drifts), so after JSON validation the report is run through a linter; violations are fixed by a **repair pass** (a second model call). Concept (`pipeline/lint.py`):

- **HARD bans — checked on EVERY field, regardless of framing**: bare diagnosis/state-as-fact constructions, command tone, catastrophizing, fate-as-fact, brand-banned phrases.
- **Frame-check — only on interpretation fields** (`introduction`, `about_child`, `conclusion`, dimension `observation`/`research_note`, `specialists.reason`): a sensitive term (anxiety/mood/character/inner-world…) is a violation **only if it lacks the safe frame nearby** (a hypothesis hedge; for clinically-heavy terms, also an attribution). Do **not** frame-check the suggestion lists (`understanding_/art_recommendations`, `development_directions`) or the `context_summary` — those are ideas/tasks/paraphrase where "the character's mood", "the cat's character" are legitimate (same reason the original linter never scanned `activities`). HARD bans still apply there.
- **Artifact exception**: a sensitive word describing the *artwork* (e.g. "anxious sky", "the hero's mood") is fine; the frame is required only when it's about the *child*. Implemented as: if an artifact-noun follows the term, allow.
- **Repair instruction = "ADD the safe frame / soften — do NOT delete the meaning."** Critical: a naive "remove banned words" repair would gut the new depth. The repair loop only adopts a rewrite if it *reduces* violations, so false positives can't damage good text.
- **Hedge vocabulary must be broad** (this bit us): recognize person/number variants ("may/can/could", plural forms) and "suppose/presumably", or the linter false-positives on already-correct hypotheses. For English: build the HARD patterns, the hedge list ("may/might/can be read as/suggests/perhaps"), the attribution list (tradition/author names), and the artifact-noun list in English.

For English, the **HARD ban set should probably be wider** (per Section 2) and the frame-check stricter.

---

## 9. Landing / marketing philosophy (the page must deliver the hero's promise)

The slogan promised "hear the child's voice"; the old report broke that promise with skill-measurement. Now the report keeps it, so the **page** must too. Principles:

- **Hero stays** ("children often say in drawings what they can't yet put into words" / "every drawing has a voice"). It was right all along.
- **What you learn** = personality-led (what excites the child, their character/approach, the mood in their drawings, the stories/heroes that matter, how to understand & support them) — skills last.
- **"How a conclusion is built"** example = personality (visible detail → gentle hypothesis → what to ask the child), not a skills example.
- **Illustrative scenarios** (trust block, important for skeptical buyers): 3–4 concrete "for example, a situation like this…" cases showing parent-worry → what the report reveals → what tip it gives. **Always explicitly framed as examples, never as real clients.** No fabricated testimonials.
- **Anti-fortune-teller positioning** (this replaced the old "we don't read the child / only skills" section, which contradicted the hero): keep the contrast "them vs us", but now **WE = careful, serious, by methods** (Piaget, Lowenfeld, Vygotsky as the "we're real, not guessing" signal); **THEM = myths, 'black = depression', fortune-telling, diagnosing from one photo, scaring with hidden traumas.**
- **Disclaimers as positive identity, not apology**: "a tool that helps understand the child through their drawing — a careful observation and a hint, not a diagnosis and not fortune-telling." Keep "if seriously worried → see a professional." The word "diagnosis" appears only in the soft-negative ("without diagnoses"), never as the promise.
- **Verbs allowed**: reveal, show, see, understand, discern, help-understand, support, suggest. **Banned**: diagnose, fix/cure, predict-as-fact.
- **SEO**: keep your existing ranking keywords (in RU these were "анализ детского рисунка по фото" etc. + the keyword FAQ questions); blend the new emotional message with them rather than overwriting.
- **Sample cards** lead with the drawing (big) + the portrait quote (`about_child`), with small score bars — the drawing and the child, not skill scores.

---

## 10. Tone & voice
Warm, human, confident; serious and scientific as the antidote to esotericism, but never dry. Speak to a parent who loves their child and wants to understand them — not to a buyer of "skill scores." Restraint on superlatives: a concrete visible detail is more convincing than stacked adjectives; 1–2 sincere warm accents per report, the rest calm expert tone.

---

## 11. Operational lessons from this cycle (carry these over)

- **Gemini call needs a per-request timeout.** Without it, a hung network/proxy call blocks the worker forever (order stuck "generating", retries never fire). We added a configurable timeout (~180s) so a hung call aborts → retries → fails cleanly. Add this from day one in the English worker.
- **Linter false-positives on narrow hedge vocabulary** sterilize good text. Build the hedge/attribution/artifact lists generously and frame-check only interpretation fields (Section 8).
- **Mobile native `<datalist>` is broken** for selection — it shows a suggestion but won't let you tap it (the user must type the whole word). Use a small custom combobox (commit on `mousedown` to beat blur, keyboard-navigable, free text preserved) instead of `<input list> + <datalist>`.
- **Committed generated assets + git pull = root-owned files** the web user can't overwrite → 500s. Either don't regenerate when the file exists, or chown on deploy.
- **Required new schema fields break old saved reports** on re-render — regenerate fresh rather than re-render historical JSON.

---

## 12. Suggested order of work for the English version
1. Adopt the **report concept** (Sections 3–7) and write the English system prompt with the **safe frame** (Section 4) and your market's zone-3 intensity (Section 2).
2. Build the **schema** (Section 6) and the **linter** with English HARD/hedge/attribution/artifact lists (Section 8).
3. Wire the **admin end-of-report texts** (7f).
4. Generate 2–4 **sample reports**, review the voice and the safe frame on real drawings (this is where you calibrate), then lock.
5. Build the **landing** to deliver the hero's promise (Section 9), keeping your SEO keywords.
6. Add the operational guards (Section 11).

The Russian implementation is the reference for *structure and intent*; the English version's job is to translate the **concept** and **tune the psychological-depth dial down** to a safe level for the Anglophone market.

# Taste Skill: distilled anti-slop frontend rules (doc-mine)

PROVENANCE: doc-mined (read-only, NO install) from github.com/Leonxlnx/taste-skill (MIT, by Leonxlnx).
"The Anti-Slop Frontend Framework for AI Agents." The repo ships a `skill.sh` installer; this file
lifts the **stack-agnostic design RULES only**, reframed for generic outputs (HTML decks, dashboards,
reports, the occasional landing page). The React/Next/Tailwind-v4/RSC stack defaults and the
official-design-system package table (Fluent/Carbon/Polaris/etc.) were skipped as stack-specific.

Keep the upstream MIT attribution (Leonxlnx/taste-skill) intact in any redistribution.

WHY it's worth lifting: its core ethos is anti-AI-slop discipline applied to the visual/frontend layer,
and it ships a mechanical pre-ship checklist. It even independently lands on the hard em-dash ban.

## The 3 dials (adopt for any deck/UI brief)
- DESIGN_VARIANCE 1-10 (1=perfect symmetry, 10=artsy chaos)
- MOTION_INTENSITY 1-10 (1=static, 10=cinematic/physics)
- VISUAL_DENSITY 1-10 (1=art-gallery airy, 10=cockpit/packed-data)
- Baseline 8/6/4. State the dial values explicitly per brief, do not run a silent baseline.

## Brief-inference first (before any build)
State a one-line design read: "Reading this as: [page kind] for [audience], [vibe] language, leaning
[system/aesthetic]." Ask ONE clarifying question only if the read genuinely diverges, else proceed.

## Anti-slop forbidden list (the core lift, stack-agnostic)
- **ZERO em-dashes / en-dashes** anywhere user-visible (headlines, body, captions, buttons, alt text).
  The upstream pre-flight FAILs on a single one.
- No pure `#000000` or `#ffffff`. Use off-black (zinc-950 / charcoal) + off-white.
- No neon/outer glows by default. Use inner borders or subtle tinted shadows.
- No "AI purple/blue-glow" aesthetic. neutral base (zinc/slate/stone) + ONE high-contrast accent.
- No three-equal feature cards. use asymmetric grid / zigzag / scroll-pinned / horizontal-scroll.
- No div-based fake screenshots / fake dashboards / fake terminals (the #1 LLM tell). real screenshot,
  generated image, or skip.
- No hand-rolled decorative SVG illustrations (single geometric mark / wordmark only).
- No generic names/data: "John Doe", "Acme", "99.99%", "1234567" -> realistic locale-appropriate names
  + organic messy numbers. fake-precise stats must be real or labeled mock.
- No startup-slop verbs (Elevate, Seamless, Unleash) -> concrete verbs.
- No scroll cues ("Scroll", "↓ scroll to explore").
- No decorative status dots (only real semantic state).
- No version labels in hero (V0.6, BETA), no version footers (v1.4.2, Build 0048) on marketing pages.
- No section-numbering eyebrows (00/INDEX, 001 · Capabilities).
- No decoration text strip at hero bottom (BRAND. MOTION. SPATIAL.).
- No pills/labels overlaid on photos; no photo-credit captions as decoration.
- No `border-t`+`border-b` on every row of long lists/spec tables. group or card it.
- No locale/time/weather strips unless the brief is genuinely place-focused.

## Typography
- Display: tight tracking + tight leading (their token: `text-4xl md:text-6xl tracking-tighter leading-none`).
- Body: relaxed leading, cap line length at ~65ch, muted (gray-600).
- Discourage Inter by default (Geist / Outfit / Cabinet Grotesk / Satoshi first); Inter OK for
  neutral/Linear-style or a11y/public-sector.
- Serif discipline: sans-serif display is NOT boring, it is standard. serif only for genuinely
  editorial/luxury AND justified. BANNED AI-default display serifs: Fraunces, Instrument_Serif.
- Italic descender clearance: italics with `y g j p q` need extra leading + bottom padding so
  descenders do not clip. audit every display italic.
- Emphasis = italic/bold of the SAME font. never inject a serif word into a sans headline.

## Color
- Max 1 accent. saturation < 80%. ONE palette per project (do not drift warm<->cool greys mid-page).
- Color-consistency lock: once the accent is chosen, use it identically on every section. audit before
  ship.
- **Named-brand override.** Taste Skill flags the premium-consumer beige/cream + brass/clay/oxblood
  palette (bg #f5f1ea/#f7f5f1, accent #b08947/#b6553a, espresso text) as its #2 AI-tell, and bans it as
  a *default*. The escape hatch is explicit: it's acceptable ONLY when the brand brief explicitly names
  those colors. So the rule to carry forward is: (a) never let a warm-luxury beige/brass palette leak as
  a DEFAULT onto work that didn't ask for it, (b) when a brief does NOT name that family, rotate to a
  different one (cold-luxury silver/chrome, forest+bone+amber, cobalt+cream, terracotta+slate).

## Layout discipline
- Hero fits the initial viewport: headline <=2 lines, subtext <=20 words AND <=4 lines, CTAs visible
  without scroll. fix by font-scale or copy cut, never overflow. hero top padding cap ~`pt-24`.
- Hero stack max 4 text elements (eyebrow / headline / subtext / CTAs). BANNED in hero: tagline-below-
  CTAs, trust micro-strip, pricing teaser, feature bullets, social-proof avatars (move below).
- Eyebrow restraint (their #1-violated rule): small uppercase wide-tracking label, max 1 per 3 sections
  (hero counts as 1). mechanical check: uppercase-tracking instances <= ceil(sectionCount/3).
- Zigzag alternation cap: left-image/right-text alternating = max 2 consecutive. 3rd = fail. break with
  full-width / vertical-stack / bento / marquee.
- Section-layout-repetition ban: a layout family used max twice. 8 sections -> >=4 distinct layout
  families.
- Split-header ban: "left big headline + right small explainer paragraph" -> stack vertically (max-width
  65ch). split only if the right column is a real visual/interactive element.
- Bento: exact cell count (N items -> N cells, no empty tiles) + >=2-3 cells with real visual variation
  (image/gradient/pattern), not all white text cards.
- "Used by" logo wall: under hero as its own section, real SVG logos only, never plain-text wordmarks.
- Nav: single line at desktop, height <=80px.

## Motion (if you have a GSAP-class animation library available)
- Motivated motion only: before animating, name what it communicates (hierarchy / storytelling /
  feedback / state). not "looked cool."
- Motion claimed = motion shown: if MOTION_INTENSITY > 4, actually animate (entry + scroll-reveal +
  hover).
- Marquee max 1 per page.
- Forbidden: `window.addEventListener("scroll")`, scroll progress in React state, rAF loops touching
  React state. use ScrollTrigger / IntersectionObserver / CSS `animation-timeline: view()` / motion
  values.
- GSAP canonical skeletons: sticky-stack (`start:"top top"`, `pin:true` per card except last) +
  horizontal-pan (pin wrapper, slide inner track, `scrub:1`).
- Reduced motion mandatory above MOTION_INTENSITY 3: gate behind `prefers-reduced-motion`,
  infinite/parallax/scroll-hijack must collapse.

## Adopt the Pre-Flight gate (mechanical, single-fail = not done)
The strongest transferable idea: a mechanical pre-ship checklist run on every visual output. Bolt the
relevant boxes onto your render pipeline: zero em-dashes, one theme + one accent + one radius system
page-wide, WCAG-AA contrast on every CTA/form, hero-fits-viewport, eyebrow count <= ceil(sections/3),
no 3+ consecutive same-layout sections, no fake screenshots, real images, every animation justified in
one sentence.

## How to apply
- Decks (e.g. pandoc HTML + headless-chrome render): pull the anti-slop list + typography + color-lock +
  hero/eyebrow/zigzag layout rules + the pre-flight gate into the deck pass. ignore the React stack bits.
- Any real frontend (a React-ish surface): the full ruleset applies.
- Content / social visuals: the generic-data + fake-precise-number + concrete-verb rules reinforce an
  anti-slop wordlist.
- Brand exception: a named-brand palette is a legitimate override to the anti-default color rules;
  everywhere else, rotate palette families and treat warm-luxury beige/brass as a banned default.

## Install-eligibility (if you ever want the live skill, not just the rules)
Gate any install behind your own stand-down check + confirm repo age >= 7 days + source-read
`skill.sh`/scripts before running `npx skills add Leonxlnx/taste-skill`. This file lifts the RULES only;
the live skill is not installed.

## External references
Study before designing; do not copy.
- **land-book.com**: real landing pages, browsable by industry. Use it for a reference board before a site build, and pick 3 references that fit the subject, not the prettiest ones.
- **uncut.wtf**: free display and text fonts that are not Inter. Check the licence per font before shipping.
- Situational: **svgl.app** (clean SVG logos, only when a page legitimately shows partner or source logos), **cta.gallery** (CTA patterns).
- Skipped on purpose: uicolors.app (Tailwind shade scales; useless for hand-written CSS with a fixed palette) and bg.ibelick.com (decorative backgrounds are the template look this file cuts).

## Design engineering lifts (emilkowalski/skills @ a81dbca, MIT)
PROVENANCE: doc-mined, read-only, NOTHING installed. Pinned to commit a81dbca07f2217b7103e510c0f13f8d5b017afc9 (newest commit at least 7 days old when read). The repo is markdown only (17 skills + 2 cheatsheets); no scripts or hooks. Author Emil Kowalski (Sonner, Vaul). Rules below are paraphrased; short quotes are his.

**Precedence over the Motion section above:** where these conflict, this section wins. In particular, the "MOTION_INTENSITY > 4 means entry + scroll-reveal + hover" line no longer licenses a scroll reveal on every section (see M3).

**Top 5:** X1 (16px inputs), X2 (gate hover), M1 (frequency gate), B7 (absolute dates after a week), B1 (worst-case run with the overflow mask off).

### Motion (10)
- **M1. Frequency gate before any animation.** Keyboard-triggered or seen 100+ times a day: no animation. Tens of times a day (hover, row highlight, tab switch): colour or opacity only, 150ms or less. Occasional (drawer, modal, toast): standard. Rare or first visit: room for delight. Why: at high frequency any duration reads as delay ("Raycast has no open/close animation").
- **M2. Data does not move for style.** No count-ups on load, no chart redraw on mount or refresh, no rows fading in when data arrives. Animate a number only when the user caused the change. Why: people are reading or acting on it.
- **M3. No fade-in-on-scroll per section.** One hero entrance on a marketing page is fine; repeated reveals fail. Why: they hold content back from fast scrollers on every visit.
- **M4. Easing by job.** Entering or exiting: ease-out. Moving on screen: ease-in-out. Hover or colour: ease. Constant motion: linear. Never ease-in on UI. Prefer strong curves over the weak built-ins: `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`, `--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)`. Why: ease-in delays the moment the user is watching.
- **M5. Duration budget.** Press feedback 100 to 160ms, tooltip 125 to 200ms, dropdown 150 to 250ms, drawer or modal 200 to 500ms (aim under 300ms). Explanatory or marketing motion may run longer. Why: "a 180ms dropdown feels more responsive than a 400ms one".
- **M6. Animate transform and opacity only; never `transition: all`.** Swap width/height/padding for `scale()`, top/left/margin for `translate()`, animated `box-shadow` for `filter: drop-shadow()`. Why: layout properties re-lay the page every frame, and mid-range phones are the bar, not a laptop.
- **M7. Reduced motion means gentler, not zero.** Under `prefers-reduced-motion: reduce` keep short opacity and colour fades, drop movement, stop loops. Why: fades still explain state; movement causes the sickness.
- **M8. Infinite loops on a persistent element need a meaning.** If the loop does not signal something live, run it once or keep the static end state. Why: a loop that never stops pulls the eye forever.
- **M9. Nothing appears from nothing.** Never `scale(0)`; start near `scale(0.95)` with opacity 0. Popovers grow from their trigger; modals stay centred. Why: physical plausibility.
- **M10. Exit faster than enter; transitions over keyframes for anything re-triggered.** A release or dismiss snaps back in about 200ms; CSS transitions retarget mid-flight while keyframes restart from zero. Why: slow where the user decides, fast where the system responds.

### Mobile-native fixes (10)
- **X1. Inputs at 16px or more on phones.** iOS Safari zooms into any input, select or textarea under 16px and does not zoom back. Fix the font size (e.g. inside `@media (pointer: coarse)`); never `maximum-scale=1` or `user-scalable=no`. Why: the zoom leaves a cropped, drifted page, and disabling zoom is an accessibility failure.
- **X2. Gate hover behind `@media (hover: hover) and (pointer: fine)`.** Same for JS `mouseenter` effects: a tap fires them and they stick until the next tap. Touch gets `:active` instead. Why: sticky hover is the most common "website on a phone" tell.
- **X3. Press feedback on press, not release.** `:active` with a subtle `scale(0.97)` (0.95 to 0.98), 100 to 160ms ease-out; in JS listen to `pointerdown`. Why: feedback on finger-down is what makes a tap feel heard.
- **X4. Kill the tap flash and the tap delay together.** `html { -webkit-tap-highlight-color: transparent }` plus `touch-action: manipulation` on buttons and links, but only once every tappable has its own `:active` (X3). Why: the grey flash fights designed feedback; the delay reads as lag.
- **X5. Safe areas for fixed bottom UI.** `viewport-fit=cover` in the viewport meta, then `padding-bottom: calc(Npx + env(safe-area-inset-bottom, 0px))` on fixed bars and floating buttons. Without the meta tag `env()` is 0. Why: the home indicator overlaps bottom-pinned CTAs.
- **X6. `theme-color` per colour scheme.** One `<meta name="theme-color">` for light and one for dark, matching the colour at the very top of the page, not the brand accent. Why: one value gives dark mode a white status bar or the reverse.
- **X7. Viewport units.** App shell or bottom-pinned UI: `100dvh`. Hero or first screen: `min-height: 100svh`. Avoid plain `100vh` for either. Why: `100vh` is the height with the URL bar hidden, so content overflows on load.
- **X8. Scroll containment.** Inner scrollers (side panels, sheets, a map frame) get `overscroll-behavior: contain`; never a `touchmove` + `preventDefault` hack. Native horizontal scrollers beat JS carousels; if a JS gesture owns one axis, give the element `touch-action: pan-y` or `pan-x`. Why: stops the page behind from moving and keeps scroll passive.
- **X9. Right keyboard per field.** `type="tel"`, `type="email"`, `inputmode="numeric"`, `enterkeyhint="send"`. Why: the phone shows the keyboard that matches the job.
- **X10. `user-select: none` on controls only, never on body.** Why: users copy addresses, phone numbers, error text.

Every mobile fix is reported as "verified from code" or "needs a phone". Desktop device emulation reproduces none of sticky hover, tap delay, input zoom, safe areas or the keyboard.

### Break-ui stress checklist (12)
Rule zero: change the DATA, not the markup, and use plausible worst values (real long names, the schema's max length), never "aaaa".
- **B1. Look at four sizes with the mask off.** Real container width, 320px, widest layout, browser zoom 200%; plus dark mode where supported. Temporarily drop `body { overflow-x: hidden }` while testing. Why: that rule hides every horizontal overflow instead of fixing it.
- **B2. Long unbreakable strings.** Emails, URLs, regulation numbers, long legal company names, place names. Fix with `overflow-wrap: anywhere` on the string and `min-width: 0` on its flex or grid column (`minmax(0, 1fr)`). Why: one string with no spaces pushes every sibling off the row.
- **B3. Trailing actions and badges never shrink.** `flex-shrink: 0` on icons, avatars, buttons; `white-space: nowrap` on short badges, then decide what yields. Why: squished icons and two-line badges.
- **B4. Truncate, wrap or clamp per field, never globally.** Wrap what identifies a thing (route, title). End-truncate secondary metadata and keep the full value reachable (`title` attribute or detail view). Middle-truncate file names, hashes, paths. Never truncate numbers, amounts, dates or anything compared.
- **B5. Counts at 0, 1 and many.** Check that an empty state exists, that "1 items" cannot render, and that a huge count still fits. Use two strings or `Intl.PluralRules`.
- **B6. Format numbers by locale, never raw.** `Intl.NumberFormat`; a German reader expects `1.284`, an English page `1,284`. Guard `null`, `undefined`, `NaN` and float noise like `0.30000000000000004`. Use `tabular-nums` for numbers in columns or that change live.
- **B7. Relative time turns absolute after about a week.** "340d ago" is unreadable; show the date. Also check "just now" and future dates. Why: relative time only helps when it is recent.
- **B8. Missing optional fields leave no trace.** Omit the line rather than render an orphan dash or an empty row; or reserve the height on purpose.
- **B9. Tall scripts and diacritics are not clipped.** Tight `line-height` with `overflow: hidden` clips accents and stacked marks.
- **B10. Images fail safely.** Fixed dimensions or `aspect-ratio` so slow images do not shift layout, `object-fit: cover` for odd ratios, and a fallback when the URL 404s.
- **B11. Hover-only actions do not exist on touch.** Anything revealed or explained only on hover needs a tap path.
- **B12. Report before fixing, worst first.** Rank each break as Broken (unreadable or unreachable), Ugly (readable but wrong) or Fragile (one step from breaking, e.g. no length limit). Some breaks are design calls (truncate or wrap); list them for the operator.

### Type details (2)
- **T1. Tracking scales with size.** Display text gets negative tracking (about -0.02em at large sizes), body sits near 0, small caps labels slightly positive. Never one `letter-spacing` for all sizes.
- **T2. Leading runs inverse to size.** Tight (about 1.05 to 1.15) on large headings, looser on body, looser still for scripts with tall marks. Space in `rem`/`em` so a raised text size does not break the layout.

### Component and library picks (4)
- **L1. Plain CSS transitions first; WAAPI (`element.animate()`) for scripted motion; a motion library only for springs, gestures or exit animations.** Why: most pages need no library, and CSS keeps running smoothly while the page is busy.
- **L2. Do not hand-roll dialogs, dropdowns or toasts as divs with manual focus.** His pick is base-ui (React); the non-React equivalent is native `<dialog>`, `<details>`, or the modal your CSS framework already loads. Why: focus trapping, Escape and dismissal come for free.
- **L3. Long lists: virtualize or paginate, and say which.** Rendering 1,000+ rows at once is a performance break as well as a visual one.
- **L4. Satori for generated OG images** (HTML/CSS to SVG/PNG), if a site wants per-article share cards.

Skipped on purpose: base-ui, cmdk, Sonner, input-otp, Leva, NumberFlow, torph, Cobe, zustand, clsx, cva, next-themes, dnd kit (a React app stack); recharts and Liveline (static SVG charts are enough); shiki (no code-heavy pages). Not lifted: springs, drag physics, clip-path tricks, 3D transforms, the `write-swift`, `animate-expo` and `ask-sonner` skills. Revisit them for a gesture-driven app.

## Taste Skill v2.1 lifts (@ f05a86f, MIT)
PROVENANCE: doc-mined, read-only, NOTHING installed or run. Pinned to commit f05a86f7a4e925eda7a4886581f09eabe80e3f8f (newest commit on `main` at least 7 days old when read). That commit is a v2.5 work-in-progress state on top of release 2.1.5, so it holds everything in v2.1 plus some v2.5 checks; rule ids below are from that commit. Every rule was checked line by line against the source; anything not in the source was cut. Quotes are short and attributed to Leonxlnx.

What v2 changed underneath (so the older sections above read in context): the repo no longer ships one SKILL.md of rules. It ships a folder: a research library (247 curated sites plus 65 professional sites), a script that deals the art direction, a real-browser inspector at 1440, 768 and 390, and a look-and-fix loop on its own screenshots (top 3 problems, up to 3 rounds). In v2.1 the script dealt three directions and the agent picked one; at this commit it deals one and the agent may redraw once with a stated reason ("models given a choice took the same five directions for 19 of 25 pages"). The 3 dials are gone. The older skills moved to `taste-skill-classics`.

**Supersedes (where this section and an older line above disagree, this section wins for pages; app screens follow the app rules here):**
- Eyebrow cap "max 1 per 3 sections": now zero eyebrows on pages (`eyebrow` FAIL on any). An app screen may keep one small tracked context label per screen.
- "Bento: exact cell count..." and bento as a zigzag breaker: no bento of boxed cards on pages (`bento` WARN, FAIL when 2 or more cards are half empty), no list drawn as boxes (`boxed-list` FAIL).
- "No border-t + border-b on every row... group or card it": "card it" is out. Lists are rows of type separated by space. Real tables and form fields keep their lines on any surface.
- "Use inner borders or subtle tinted shadows": no shadow on anything at rest and no 1px outlined boxes on pages (3 or more FAIL). Separate surfaces by a tone step or space.
- Body text "muted (gray-600)": running text in full ink, 7:1 or more (`grey-body`). Muted ink is for secondary notes only.
- "Emphasis = italic/bold of the same font": no styled accent word in a headline at all, italic included (`mixed-font-headline`).
- Fonts "Geist / Outfit / Cabinet Grotesk / Satoshi first": Outfit and Inter are on their stock-font list (`default-font` WARN). "Stock Geist or Inter on #f8f8f8" is a named dashboard tell. Pick type per brief.
- Palette rotation "terracotta+slate" and "cobalt+cream": terracotta is a FAIL family and yellow cream a WARN family (bands below). Use bone or stone for warmth, not cream.
- Layout alternatives "scroll-pinned / horizontal-scroll": no sideways rails on desktop (`sideways-rail` WARN), and pinned bands covering a third of the screen or more must release below 1100px (`sticky-band` FAIL).
- "Any real frontend: the full ruleset applies": the page rules do not apply to app screens (dashboards, cockpits). Use the app rules below.
- The 3 dials stay only as shorthand in a brief. The direction from the table below is the real decision.

**Not superseded (the stricter rule stays):** zero em and en dashes (their lint only WARNs past 4 em dashes on a page); X1 inputs at 16px or more on phones (their text floors are 13px and 15px); M1, M2 and M3 over their motion minimum (see conflicts); a named-brand palette override.

### Art directions (25 at this commit; v2.1 had 20, v2.5 added the last 5)
Fit = the brief shape it suits. Fail = its own listed pitfall.

| id | Name | Essence | Fit | Fail |
|---|---|---|---|---|
| name-as-monument | The name as a monument | The name set so large it becomes architecture | Short, strong name; bold or luxury | A long name set small is just a logo |
| sentence-as-layout | The sentence is the layout | Plain sentences, each beside its proof | Claims you can show with a photo or figure | Over about 32 characters; a sentence with no proof is a slogan |
| pinned-poster | The pinned poster | A fixed title while a series of pictures changes under it | A consistent photo series | Title unreadable on the panel; empty screens under the pin |
| colour-chapters | Colour chapters | Each section one flat colour field | The subject owns real colours | Weak contrast per field; cards on fields; over 6 colours |
| place-carries-it | The place carries it | One full-bleed photo of the place; design steps back | Hotels, venues, places | A weak hero photo; text stacked on the image |
| page-is-the-object | The page is the object | The page built as the subject's printed artefact | It has a real menu, ticket or card | A borrowed artefact reads as costume |
| one-motif | One motif | One shape from the subject, at many scales | A clear shape exists in product or mark | More than one shape; motif not traceable in one clause |
| product-performs | The product performs | Working fragments of the real software | Software with one signature interaction | Fake grey-bar UI |
| quiet-instrument | The quiet instrument | Radical understatement, narrow exact column | A simple, finished tool | Emptiness that looks undecided; text under 16px |
| hero-object | The object, large | One object photographed, cropped by the screen | A strong product photo exists | Small centred catalogue shot |
| specimen-catalogue | The specimen catalogue | Each item alone on a flat tile at one scale | Six or more showable items | Under six items; labels or shadows on tiles |
| borrowed-category | Dressed as something else | A dull subject in a vivid category's manners | The audience lacks a feeling another field owns | Borrowing "tech startup" |
| contact-sheet | The contact sheet | Dozens of small frames in strict rows | Range and volume of work is the point | Under about 20 images |
| editorial-report | The printed annual | Report layout: masthead, exact axis, solid blocks | Findings, a programme, serious content | An inexact axis reads as random indents |
| loud-flat-poster | Loud and flat | Flat saturated colour, heaviest type | A loud subject | Outlines, offset shadows, rotated text |
| split-stage | The split stage | Half fixed photo, half calm scrolling column | Atmosphere must stay while facts are read | Identical splits all the way down |
| dense-tiles | The well-kept board | Edge-to-edge board of tiles, no hero | Many small true things | Weight 0 at this commit: not dealt |
| uneven-photographs | Photographs at uneven sizes | Gallery-wall photos at varied sizes on a grid | A strong photo set, calm tone | Placement off the column lines |
| dark-room | The dark room | Tinted dark field, lit exhibits, sparse light type | Sold on atmosphere and material | Grey on black; glows; text under 7:1 |
| type-only-statement | Type and nothing else | First screen is type, colour and space only | Nothing worth photographing up top | Weak copy; four heading-plus-paragraph sections |
| clear-product | The product, clearly | Plain sentence, then the real product, large | The product can be shown truthfully | Boxes, icons above features, three identical columns |
| shop-window | The shop window | Large sharp product photos, an obvious way to buy | A shop with consistent photography | Few or mismatched pictures; a 3-item carousel |
| calm-editorial | The calm magazine | Short pieces, one good picture each, given room | The subject has its own story | Long paragraphs; fake pull quotes |
| spec-sheet | The spec sheet | Exact numbers, materials and names, set well | Real specific figures exist | Invented numbers; a box around every fact |
| clear-service | The clear service | What, for whom, cost, how to start, in that order | A service with real prices, hours, steps | Vague claims; the booking hidden at the bottom |

### Matching a direction to a surface
- **Service business site:** clear-service first ("the booking hidden at the bottom" is its named failure, so the main contact action stays on the first screen). Then sentence-as-layout (each claim beside a real photo; keep lines under about 32 characters for phones), spec-sheet for hard facts (real figures only, no box around each fact), and one-motif only if a shape from the mark can be named in one clause.
- **Essay or research site:** editorial-report first (the exact axis suits long essays). Then type-only-statement (honest for an author with nothing to photograph; "weak copy has nowhere to hide"), sentence-as-layout for claim-plus-chart pages, calm-editorial only where an essay has a real picture.
- **Deck:** dark-room fits a dark brand deck (tinted dark ground, one warm accent "used once per screen at most", running text 7:1). editorial-report and type-only-statement for text-led slides, spec-sheet for findings with figures ("one accent used like a signal"). colour-chapters for a light deck (one field per chapter, 6 colours max, contrast checked per field).
- **App screen (dashboard, cockpit):** page directions do not apply. Of the 7 app styles, true-black-flat (elevation by lightness alone, #000, #111, #2a2a2a, no borders or shadows on cards) matches a dark-default dashboard; achromatic-ledger (no brand colour in chrome, one chart hue on the main data) matches "colour goes on data, not chrome". Choose one, not both.

### Slop-inspector checklist (run with your own browser tooling, widths 1440, 768, 390)
Their gate: any FAIL means "the page is not done"; a WARN needs "a reason you could say out loud to a designer". Kind: DOM = computable in one `page.evaluate`; FILM = needs screenshots while scrolling; LINT = static source scan. Keep the thresholds in one table at the top of whatever script runs these, so tuning them is one visible edit.

**Page FAIL**
- `headline-lines`: any h1 to h6, or the first screen's main line, wraps past 2 lines at any width. DOM.
- `eyebrow`, `numbering` (01/02, "Step 2"), `emoji`, `mono` outside code: any one. DOM + LINT.
- `micro-label`: 3 or more tiny uppercase tracked labels (1 or 2 is WARN). DOM.
- `gradient`, `gradient-text`, `text-shadow`, `button-fx`, `shadow` on an element at rest: any (a neutral scrim over a photo is the one allowed gradient). DOM.
- `hairline`: 2 or more thin rules or dividers outside real tables and form fields (1 is WARN). `outlined-box`: 3 or more 1px outlined boxes (1 or 2 WARN). DOM.
- `icon-cards`: a row of identical cards each topped with a small icon. DOM.
- Palette bands (HSL): `palette-terracotta` hue 6 to 30, sat 0.38 to 0.85, light 0.42 to 0.72; cream hue 22 to 62, sat 0.16 or more, light 0.88 to 0.995 (`palette-cream` WARN alone, `palette-claude` FAIL with terracotta); `palette-purple` hue 244 to 295, sat 0.42 or more, light 0.3 to 0.8. DOM.
- `contrast` (text under 4.5:1, large display under 3:1), `font-count` over 3 families (3 is WARN), `synthetic-bold`, `body-size` under 15px, `small-text` more than 3 blocks under 13px. DOM.
- `few-pictures`: under 3 photos, raster images or interface fragments at desktop width; SVG drawings do not count. DOM.
- `wordy-page`: over 95 words per screen (over 70 WARN). DOM.
- `overflow` (page scrolls sideways), `cut-text`, `broken-image`, `edge-text` (text within 12px of a phone edge or 16px of a desktop edge). DOM.
- `focal-point`: desktop first screen with largest type under 4.5vw and no picture holding 30% of the viewport. `no-title`: no visible h1, or the h1 not on the first screen. DOM.
- `off-centre`: left and right margins differ by at least the larger of 40px (14px on phone) and 4.5% of the width. `lopsided`: 2 or more sections with all content on one side. `untitled-section`: 2 or more sections with text and no heading. DOM.
- `picture-in-headline`, `picture-in-sentence`, `form-in-sentence`, `hero-in-card` (width 700 or more), `builder-note`, `boxed-list`, `lone-heading`. DOM.
- `no-nav`: fewer than 2 links in the top 160px (3 on phone) and no menu button. DOM.
- `giant-footer`: footer text at 7vw or more on desktop. `credit-wall`: 3 or more credit links or mentions in the footer. DOM.
- `upscaled-picture`: a picture shown larger than its natural size (they ask for a source 1.5x the shown size, 2x for the hero). DOM.
- `colour-sprawl`: 4 or more hues across grounds, type and buttons (3 is WARN). `colour-ground`: over 60% of the page on coloured grounds with 2 or more hues (over 35% WARN). DOM.
- `sticky-band`: below 1100px, a fixed or sticky element at least 80% wide and 33 to 97% of the screen tall. DOM.
- `drawn-illustration`: a large SVG drawing (3 or more small ones is `svg-doodles` WARN). DOM.
- `covered-text`, `text-over-text`, `never-readable`, `empty-screens` (2 or more desktop screens under 20% filled), `late-title` (title not readable 1.2s after load), `reduced-hidden` (2 or more first-screen text blocks invisible under reduced motion). FILM.

**Page WARN worth keeping:** `hero-words` over 10; `wordy-hero` over 45 words on the first screen; `grey-body` under 7:1; `measure` over 88 characters a line; `text-wall` paragraphs over 70 words; `wordy-section` over 130 words; `size-count` over 9 sizes; `all-centred` over 72% centred with 4+ headings; `long-page` over 16 screens; `first-action` no button on the first screen; `ellipsis`; `side-scroll` and `sideways-rail`; `default-link` (#0000ee, #551a8b showing); `placeholder-contact`; `repeated-picture`; `font-fallback`. LINT WARNs: `copy` (unlock, seamless, elevate and the like), `cta-copy` (Learn more, Get started, Submit), `transition-all`, `ease-in`, `scale-zero`, `h-screen` (100vh), `bounce` (pulse dots).

**App mode (dashboards, cockpits).** Skipped there: eyebrow, page mono, numbering, hairline, outlined-box, dashed, icon-cards, card-rows, shadow, glass (page version), grey-body, measure, body-size, small-text, first-action, few-pictures, focal-point, still-page, empty-screens, off-centre, lopsided, untitled-section, bento. Added:
- FAIL: `sidebar-phone` (sidebar over 30% of a phone width), `heavy-shadow` (a panel shadow heavy enough to read as floating), `glass`, `rainbow-chart` (over 6 hues; over 4 WARN), `placeholder-data` (Acme, John Doe, example.com), `tiny-text` (more than 2 blocks under 11px), `no-title` (no h1), `cut-text`.
- WARN: `numeric-align` (6+ numeric cells, half or more left-aligned), `tabular` (6+ figures, under half tabular), `colour-sprawl` (over 12% of the first screen strongly coloured; their studied screens sit near 3%), `no-data-hue` (charts with no hue on the data), `heavy-borders`, `radius-mix` (over 3 panel radii), `app-title-size` (h1 over 34px, 28px on phone), `kpi-size` (a figure at 48px or more), `size-count` (over 10), `icon-tiles` (4+ boxed icons), `unused-canvas`, `below-fold`, `ragged-row`, `panel-void`, `mono` over 15% of text, `sentence-title`, `app-wordy` (over 4 sentences of 12+ words). LINT: `framework-colour` (stock Tailwind blue, green, red, amber).

Dropped: all scene and replay checks, `long-pin`, `pinned-over-picture`, data-ui fragment checks, video checks, `range-slider`, `switch-list`, `decorative-control`, `drag-bar`, `result-first`, `dev-server`, font and entrance "not dealt" checks (their draw sheet is not used here).

### App-screen rules
Distilled by them from 23 real product screens. Their order of what separates real screens from generated ones: colour on data, not chrome (median about 3% coloured pixels); KPIs are type, not tiles (no icon circles, no sparklines); flat surfaces (a 1px line or one tone step, "a border or a shadow, never both"); no hero header (title 18 to 32px, a noun such as "Overview"); charts with almost no chrome (no legend for one series, 3 to 5 faint gridlines, a 2px straight line); quiet navigation (active item a grey pill or brighter label); tables are rules and alignment (no zebra, no header band, 12px grey sentence-case headers, numbers right-aligned in tabular figures); honest states (zero prints as zero, a missing value as a grey dash, an empty section keeps its frame).
- Allowed on app screens with limits: 1px borders at about 1.1 to 1.3:1 against the ground (#1a1a1a on #000, #2e2e2e on #111); row rules 3 to 7% darker than the surface; labels 12 to 14px, nothing under 11px; pills only inside rows, 16 to 24px tall, pale tint with dark text of the same hue; shadows only on what floats.
- Banned: status colour on a zero or undefined change (use grey or words, "+4 (new)"); a navy or slate dark theme (true neutral darks instead); the accent on chrome (tinted nav row with a left bar, coloured tab pills); KPI figures at 48px or more (16 to 40px); pagination under a short list (cap rows, "View all", the total).
- Their warning from testing: quiet alone lost blind rounds. Every block the brief names shows its header and first rows on the 1440x900 first screen; the screen names its product and scope; the most frequent job is one click away; colour on a change means good or bad, not up or down; give it "one element only this product has".
- Their missing-value grey dash conflicts with B8 (omit the orphan dash). In app table cells use the grey dash so columns stay aligned; elsewhere B8 holds.

### Asset licence rule
Their `assets.mjs` searches Openverse, Wikimedia Commons, the Art Institute of Chicago and the Met (footage: Commons, Internet Archive Prelinger, NASA), keyless, and by default keeps only CC0, public domain, CC BY and CC BY-SA. The rule, lifted:
- Use only CC0, PD, CC BY or CC BY-SA on client or public pages. NC and ND are out "for a client's site". CC BY-SA: an altered version (recoloured, combined) must be shared under the same licence, so do not recolour a BY-SA picture for a client.
- Download into the project, never hotlink. Record file, title, creator, licence and source page in the build report.
- CC BY and BY-SA need title, creator, source link and licence link; put them behind one small "Image credits" link that opens a dialog, never a footer wall (3 or more credits in the open is `credit-wall` FAIL). PD and CC0 need no credit on the page; the client's own photos need none.
- A found picture is never presented as the client's own product, room, person or team, and a caption names only what the picture shows.
- Read each record's note: some pictures carry personality rights or a trademark, or are public domain only in the United States.
- Fetch from these archives through a remote fetch service or a reviewed script, not their Node script (doc-mine only).

### Conflicts to know about
- **Motion minimum.** Their `still-page` FAILs a page where fewer than 8 elements move during load and one scroll (under 16 WARN). That clashes with M2 and M3 and with a quiet essay site. Not adopted: the motion rules above win, and `still-page` is report-only. App screens are exempt in their app mode anyway. Their own fix text agrees on one point: "never a fade on every section".
- **Named-brand palette.** A brand colour that a brief names explicitly stays, even if it sits near a banned band; it never leaks onto work that did not ask for it.
- **Pure black.** "No pure #000" holds on pages. On app screens, true-black-flat uses #000 as its ground by design; allowed there only.
- **Pictures.** `few-pictures` FAILs a desktop page with under 3 real pictures. Essay pages will trip it; treat it as WARN there and say why in the report.
- **Em dashes.** Theirs WARNs past 4 on a page; the rule here is zero. Zero wins.

## Jakub Krehel lifts (@ 592aedc, MIT)
PROVENANCE: doc-mined, read-only, NOTHING installed or run. Pinned to commit 592aedc44d7d5b3e29740984252902f3e5402a1c (newest commit at least 7 days old when read), github.com/jakubkrehel/skills. Mined 4 skills only: better-accessibility, better-writing, interface-review with teardown, state-machine. Claims that could not be backed against the source were cut.

Not repeated here because the design engineering lifts above already cover them: 16px inputs and no zoom lock (X1), right keyboard per field (X9), reduced motion as fades (M7), native dialogs (L2), 320px and 200% zoom (B1), tap path for hover (B11), counts and plurals (B5), locale numbers (B6), missing fields (B8). A rule below cites its WCAG 2.2 criterion where one applies; anything without one is a recommendation, not a blocker.

### Accessibility (11)
- **A1. Every control and image has a name that says what it does.** Icon-only buttons and image links name the action ("Chat with us", "Close dialog"), never the glyph ("X", "Trash icon"). A logo link takes its name from the logo's alt ("Company home"). Every `<img>` has an `alt`: `""` if decorative, the meaning if informative, the action if it is a link. If a control shows a word, its accessible name starts with that word (2.5.3).
- **A2. Never remove the focus ring without a checked replacement.** Style `:focus-visible`, not `:focus`. Best is the browser ring plus `outline-offset: 2px`. A custom ring must reach 3:1 against every colour it crosses (1.4.11). Never `outline: none` alone, and leave forced-colors mode alone.
- **A3. Actions are `<button>`, navigation is `<a href>`.** A div or span with a click handler has no keyboard path (2.1.1). A disclosure header is `<button aria-expanded>`. A link with `href="#"` that opens a modal is a button.
- **A4. A `role="tab"` needs the tab key map, or drop the role.** Arrow keys move between tabs, one Tab stop for the set (roving `tabindex`: active 0, others -1), each tab `aria-controls` a `role="tabpanel"`. If that is too much, use plain buttons with `aria-pressed`.
- **A5. Overlays move focus in and give it back.** On open, focus goes inside the dialog or drawer; on close, back to the control that opened it. The dialog is named by `aria-labelledby` pointing at its title. A modal makes the background `inert`. This extends L2: a native dialog still needs the name and the focus return.
- **A6. Colour never carries status alone (1.4.1).** Pair it with text, an icon or a shape.
- **A7. Anything that updates on its own for more than 5 seconds needs a pause (2.2.2), and a refresh must not take away focus, scroll or a text selection.**
- **A8. Announce changes through one live region that exists from page load.** Render an empty `role="status"` element first, then change its text. `role="alert"` only for urgent errors not tied to a field. Never `aria-live="assertive"` for routine news.
- **A9. Forms: a real label, the right autocomplete, errors that announce.** A placeholder is never a label. Fields about the user carry a valid `autocomplete` token (`name`, `email`, `tel`, `organization`; 1.3.5). Never block paste. Keep submit enabled and validate on submit; on failure set `aria-invalid="true"`, point `aria-describedby` at the inline error and focus the first bad field. A pending submit keeps its label beside the spinner and uses `aria-disabled`, not `disabled`, so focus does not drop.
- **A10. Targets at least 24 by 24 CSS px, or spaced so a 24px circle around each does not touch another (2.5.8).** Decorative layers (glows, scrims, map overlays) get `pointer-events: none`. `aria-hidden="true"` never sits on a focusable element or its ancestor.
- **A11. One `<main>`, a skip link, and nothing hidden under sticky chrome.** Exactly one `<main>` holding the page's primary content, including its h1. When navigation comes first, a "Skip to content" link is the first focusable element. A sticky header sets `scroll-padding-block-start` to its height so a focused element or jumped-to anchor is not hidden (2.4.11).

### UI writing (5)
- **W1. Buttons start with a verb that names the action.** "Send quote", "Book a call", "Export PDF". Never "OK", "Yes", "No" or "Submit". Use "select" or a plain verb, not "click", on phone-heavy pages.
- **W2. Link text names where it goes and makes sense alone.** Screen-reader users jump through a list of links. "Read the method", never "here". Two "Learn more" links on one page each get their topic ("Learn more about the method").
- **W3. An error is an instruction, next to the field that failed.** Say what to enter: "Enter a phone number with country code, like +44 20 7946 0958", not "Invalid phone". No "Oops", no "!", no blame, no "Please" in routine instructions. Show a known rule as helper text before the user types. A placeholder shows a realistic example in the accepted format, never an instruction.
- **W4. Status strings come in pairs and say what happened.** In progress is "-ing verb plus object" ("Sending request"); done is "object plus past tense" ("Request sent"), with no "successfully". Failed says what did not happen and the next step. Partial gives both counts ("9 of 12 sources answered"). Unavailable says why and what unlocks it, beside the control.
- **W5. An empty state says what belongs here and offers one next step.** A filtered empty state names the query and offers "Clear filters". Never park information there that people need later, because it vanishes once content exists.

### UI states (3)
- **S1. List the states from the code branches before polishing anything.** One line each, named as the product names them. A state the code cannot reach is not a state; a state the design shows but the code lacks is listed as missing, not built. Combine states only where the code branches on the combination. After any visual fix, check every listed state again, because a fix for one often breaks another.
- **S2. Every live view has a designed loading, stale and partial state.** First paint shows the frames and card titles, never blank columns. When a refresh fails, the old data is marked stale with its age on the data itself, not only in a corner timestamp. A page where some sources answered and others failed is a normal state: healthy panels render beside the failed one, and the header says how many answered.
- **S3. Test states by feeding data at the seam, never by editing the renderer.** Fixtures look like the product (real names, real timestamps, real counts), and a loading fixture stays pending until you change it. For a dashboard the seam is usually its JSON API: save a real response, edit it, and serve it from a scratch page outside the repo.

### Reviewing a UI change (4)
- **R1. Read the removed lines.** On a UI diff, search only the deleted lines for `aria-|role=|alt=|for=|focus|outline|tabindex|prefers-`. A hit is a lead, not a finding. Clear it first if the same diff replaced it (an outline swapped for a `box-shadow` ring on the same `:focus-visible`, a div turned into a real `<button>`, a colour literal turned into a variable with the same value).
- **R2. Give every finding one status by cause: Introduced, Regression or Pre-existing.** A break on an untouched page caused by a changed shared stylesheet or CSS variable is Introduced. List at most 3 pre-existing problems, worst first, marked as not this change's fault.
- **R3. Review the pages the changed file renders in, not the file.** One hop by default; a second hop only for shared CSS variables, theme files and shared partials. Cap at 5 pages and say how many you skipped, because an unstated cutoff reads as full coverage. Open the report with the base commit, the head, and the files excluded.
- **R4. A new control or variant ships with every state, and a review never changes the checkout.** Check hover, focus, disabled, loading, error, empty and narrow width exist. No `git checkout`, `switch` or `stash` during review; read with `git show` or render a throwaway `git worktree`. With nothing to review, say so and ask; never fall back to the last commit on your own.

Skipped on purpose: the i18n machinery (ICU messages, locale catalogues), the React and Tailwind snippets, the roving-tabindex combobox and full widget key maps, drag alternatives, the "type the name to confirm" and undo-over-confirm patterns, their `better-*` hand-off and Block or Approve verdict format, the state-machine switcher page, and all of teardown (it draws technical illustrations of objects; no UI review content). Conflict: their flow vocabulary uses "Get started", which the `cta-copy` lint flags. The lint wins.

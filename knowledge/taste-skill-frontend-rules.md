# Taste Skill — distilled anti-slop frontend rules (doc-mine)

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

Build a complete, static, single-page marketing website for "Tenet" using React + Tailwind. It has two jobs: (1) a landing page for potential customers (startup teams, founders, business heads, lead engineers) and (2) a companion to our seed pitch deck for VCs. There is NO backend. Everything is static, with no API calls, no auth, no database. The only "form handling" is a mailto: redirect.

================================================================
1. PRODUCT CONTEXT (use this copy; do not invent facts)
================================================================
Tenet = shared AI memory and decision records for teams, so work converges in fewer iterations.

Problem: AI makes producing work cheap, but deciding is not. Each person works with their own AI chat, so context is scattered, pushbacks vanish after the meeting or chat ends, and teams reopen settled decisions instead of converging. Today's tools store the work, not the decision behind it.

Solution: one shared memory per project, with every decision on record.
- Shared AI memory: every collaborator's findings, pushbacks and forecasts feed one project memory.
- Decision records: each decision keeps what was decided, who approved it, and the challenges raised.
- A master agent per project: keeps memory current, answers questions, flags work that drifts from approved decisions.

Workflow (4 steps): Contribute -> Challenge -> Decide -> Maintain.
1. Contribute: each person shares what matters from their AI work to the project memory.
2. Challenge: teammates add pushbacks, risks and forecasts in one place.
3. Decide: the owner records the call, with approvers and reasoning.
4. Maintain: the master agent keeps everyone current and flags drift.
Product lives inside Docs, Slides and Sheets.

Principle: "Think privately. Choose what becomes shared. Challenge, decide, revisit." People research with their own AI assistant, then push a prompt, a response, or both into project memory.

Tagline options: Hero H1 = "Work converges when decisions are on record." Supporting line = "Shared AI memory and decision records for teams, so work converges in fewer iterations." Insight line (use as a full-bleed band) = "Producing work is cheap now. Deciding isn't."

HONESTY RULES (important): There is no working product yet. A Figma prototype and a partially working MVP exist. Never claim live customers, logos, user counts, testimonials or certifications (no SOC2/ISO badges). Label every product visual "Illustrative UI · MVP in development". Use "Private beta" / "Early access" language. Do not use stock photos or fake company logos.

================================================================
2. THEME: "LOCKED IN" (follow this consistently everywhere)
================================================================
Concept: Tetris-style blocks. Pieces fall, then lock into place and form a tidy skyline. Chaos -> convergence. This is the only decorative motif, so use it everywhere instead of photos or generic illustrations.

Color tokens (define as CSS variables / Tailwind theme):
- ink: #0A1E28 (dark section background, primary text on light)
- ink-2: #0F2B36 (cards on dark)
- cream: #F5F0E6 (default page background)
- paper: #FAF9F4 (cards on cream)
- coral: #DE5569 (primary accent, primary CTA)
- sun: #F2CF4B (highlight, eyebrow labels on dark)
- teal: #1A9A96 (positive/"decided" states)
- plum: #6A3F7B
- ember: #EC7A39
- muted text on cream: #5B6B72; muted text on ink: #9DB0B8
Rule: coral is the single main accent. The other block colors (sun, teal, plum, ember) are used only for blocks, card top-borders, bullets and small status chips, never for large text blocks.

Typography: Google Fonts. Headings = "Urbanist" (600/700, tight tracking -0.02em, very large: H1 up to 96px desktop, 44px mobile). Body = "Lato" (400/700), 17-18px, line-height 1.6. Eyebrow labels = Urbanist 700, uppercase, letter-spacing 0.18em, 12-13px, preceded by a small filled square in the accent color (e.g. "■ THE PROBLEM"). Section chapter numbers like "01 / The problem" in the PromptForce style.

Shape and feel: 8px radius cards (square-ish, like blocks), soft long shadows on paper cards, 6px colored top-border tab (about 72px wide) on cards in sun/teal/plum/coral/ember, large generous whitespace, 12-column grid, max width 1200px. Confident, editorial, calm. Not corporate-stock, not cyberpunk.

Signature motifs (build these as reusable components):
1. <BlockPiece> — SVG/CSS tetromino built from square cells with 2px gaps. Colors from the palette. Sizes S/M/L.
2. <Skyline> — a strip of stacked blocks along the bottom edge of the hero, footer and final CTA (like the deck's cover). Blocks drop in with staggered delay and lock with a tiny bounce on load / when scrolled into view.
3. <FallGuide> — a thin dotted vertical line with a small arrow at the end, above a falling piece (from the deck cover).
4. Section dividers: small 3-5 block clusters in the corner of section headers (top-right), as in the deck.
Motion: subtle only. Pieces fall and lock (translateY, ease-out-back, 600-900ms, stagger 60ms), cards fade-up 16px on scroll-in, hover lifts cards 4px. Respect prefers-reduced-motion (disable all falling animation, show final state). No parallax, no autoplay video, no carousels.

Section rhythm: alternate cream and ink backgrounds so the page feels like a deck: Hero (ink) -> Problem (cream) -> Insight band (coral) -> Solution (cream) -> How it works (ink) -> Demo (cream) -> Positioning (cream) -> Who it's for (ink) -> Pricing (cream) -> Investors (ink) -> FAQ (cream) -> Beta form + footer (ink).

================================================================
3. PAGE STRUCTURE (top to bottom, with copy)
================================================================

NAV (sticky, blurred background, 72px): Logo wordmark "Tenet" (Urbanist 700) with a tiny 2x2 colored block mark. Links (smooth-scroll anchors): How it works · Why Tenet · Pricing · Investors · FAQ. Right side: primary coral button "Join the beta" (scrolls to #beta). Mobile: hamburger with full-screen ink menu.

HERO (ink): 
- Small pill: "■ PRIVATE BETA · SEED ROUND NOV 2026" 
- H1: "Work converges when decisions are on record."
- Sub: "Shared AI memory and decision records for teams, so work converges in fewer iterations."
- CTAs: "Join the beta" (coral, filled) and "Watch the walkthrough" (outlined, scrolls to #demo). Below, small muted: "Built for teams that think with AI. Early access, no card needed."
- Right side visual: a floating "Decision record" card (DR-042 · Move onboarding to a self-serve trial · status chip "Decided" in teal · Owner Priya, Head of Growth · Approvers Arjun (CEO), Meera (Eng Lead) · two challenges raised with resolutions · a coral "Drift flagged by master agent" banner). Tag above it: "ILLUSTRATIVE UI · MVP IN DEVELOPMENT". Around it, tetrominoes fall slowly into place with FallGuides.
- Bottom edge: <Skyline> in all palette colors.

PROBLEM (cream) — eyebrow "01 / The problem", H2 "Teams iterate in parallel and drift apart". Three paper cards with colored top tabs:
 01 Context split across AI chats — "Each person works with their own AI, so findings get passed around one by one."
 02 Pushbacks get lost — "Challenges, forecasts and trade-offs vanish once the meeting or chat ends."
 03 Loops never close — "Teams reopen settled decisions and circle back instead of converging."
Below, a pull-quote with a coral left bar: "When my juniors come back with follow-ups to a task, it's hard to understand how they reached a conclusion or what they took from their AI conversation. When the context gets bloated, it's also hard to stop them once they've drifted from the actual problem." Attribution: "— Business Head, Series B startup (customer interview)".

INSIGHT BAND (full-bleed coral, cream text, huge type): "Producing work is cheap now. Deciding isn't." Sub: "AI lets every team produce more docs, decks and analyses than leaders can review. Today's tools store the work, not the decision behind it." Decorative sun and ink blocks at the corners.

SOLUTION (cream) — "02 / The solution", H2 "One shared memory for the team, with every decision on record". Three cards: Shared AI memory, Decision records, A master agent per project (the third card is ink-colored with a sun border to stand out). Copy as in section 1.

HOW IT WORKS (ink) — "03 / How it works", H2 "Inside Docs, Slides and Sheets". An interactive 4-step stepper (Contribute, Challenge, Decide, Maintain) with numbers 01-04, a colored block per step (coral, sun, teal, plum) and dashed arrows between steps. Clicking/hovering a step updates a large mock panel on the right that visually builds the DR-042 decision record progressively:
 - Contribute: shows a "Shared to project memory" item with the prompt/response toggle ("Push a prompt, a response, or both").
 - Challenge: adds Meera's pushback ("Trial users may overload support in week one.") and Arjun's forecast ("Sales-led deals drop 20%.").
 - Decide: adds resolutions ("Add in-app guide; review tickets after 14 days." and "Keep sales-assist for 50+ seat accounts.") and the teal "Decided" chip with owner and approvers.
 - Maintain: shows the coral drift banner: "Pricing deck v3 still shows a demo-only flow. This conflicts with DR-042."
Autoplay is NOT allowed; user-driven only (but on first view, animate step 1->4 once). Always show the "Illustrative UI · MVP in development" tag. Include a note under it: "Think privately, choose what becomes shared. Nothing enters project memory unless you push it."

DEMO (cream) — "04 / Demo", H2 "Tenet in action". Left: a dark video-style card labelled "RECORDED WALKTHROUGH" with a coral play button, text "Watch Tenet in action", and a link "OPEN LOOM VIDEO ↗" with href="#" and a clearly marked code comment: // TODO: replace with Loom URL. Caption: "Figma prototype + partially working MVP." Right: a static screenshot-style mock of the decision record (reuse the component).

POSITIONING (cream) — "05 / Why Tenet", H2 "Others organize knowledge. Tenet helps teams work through decisions together." Sub: "The difference is the unit of collaboration: selectively shared reasoning, not just indexed content." Layout: left column with three stacked paper cards ("Where adjacent tools start") and right a large ink card for Tenet (PromptForce-style comparison, but light):
 - Rovo / Glean: Connected work data → answers, agents and automations
 - Notion AI: Documents and meetings → recaps, actions and decisions
 - ChatGPT Projects: Shared chats and files → project context and branching
 - TENET: Think privately — research and explore with your own AI assistant. / Choose what becomes shared — push a prompt, a response, or both into project memory. / Challenge, decide, revisit — capture pushbacks and forecasts; query the project agent later.
 Footnote (required): "Comparison describes core product emphasis, not absence of features. Tenet's workflow is a product vision / MVP in progress."

WHO IT'S FOR (ink) — "06 / Who it's for", H2 "Built for teams that think with AI". Three persona cards (founders, business heads, lead engineers), each with a one-line pain and a one-line outcome. Examples: Founders: "See how every call was made, and by whom." Business heads: "Understand how a junior reached a conclusion, and catch drift early." Lead engineers: "Stop re-litigating architecture decisions. The reasoning is on record." Add a small "What we heard in 10 customer interviews" strip: "Teams lose context when AI findings move from person to person. They want a shared record of reasoning and decisions."

PRICING (cream) — "07 / Pricing", H2 "One simple plan that grows from one team to the whole company". A currency toggle (INR / USD) switching between a single card showing ₹999 /user/mo (India, billed in INR) and $15 /user/mo (US & global). Copy: "Every feature in one plan." "Enterprise controls priced later." Third ink card: "Land and expand: 1 → many teams. Start with one project team, then spread to every team it collaborates with" with a small 1 block → many blocks graphic. Small note: "Indicative pricing for early access. Beta participants get preferential terms." (Do not state any specific discount.)

INVESTORS (ink, id="investors") — big eyebrow "For investors" and H2 "A decision layer for the AI-native team." Sub-nav of small tabs or just stacked sub-sections:
 a) Why now — three shifts: Agents can hold memory (shared project context, surface changes over time); AI use is fragmented (separate tools, reasoning scattered across private chats); Review can't keep up (AI generates more than teams can review and align on).
 b) Traction — "10 customer interviews" and "2 verbal pilot commitments" as big stat counters. Copy: "Kapiva and SalarySe have verbally committed to pilot Tenet. Verbal intent only; working toward signed paid pilots." Who we've spoken to: founders of Series A-funded startups; a business head at a Series B startup; senior engineers at HighLevel and Harvey AI; staff engineers at LinkedIn, Stripe and Rubrik. (Present as text bullets with colored squares, NO logos.)
 c) Market — four stat cards: TAM $21.5B (global team collaboration software, 2025, IMARC Group); SAM·US ~$720M (~100,000 US companies with 100-999 staff × 40 seats × $15/mo × 12); SAM·India ~$50M (est. ~10K firms × 40 seats × ₹999/mo × 12 ≈ ₹480 crore); SOM·2-yr goal ~$120K ARR (20 firms × 40 seats × $12.50/mo). Plus a simple bar chart: Y1 $50K, Y2 $120K ARR target. Footnote: "India-first; $120K goal assumes $12.50 blended ARPU (some global-priced seats). Market sizes estimated."
 d) Moat — "Every decision makes the next one better informed": Compounding decision context; Context that survives handoffs; Continuous alignment (project agents check later work against approved decisions and flag possible drift).
 e) Business model — per-seat SaaS; est. model-cost margin India ~70% · Global 75-80%. Footnote: "Token-cost estimates only; excludes other delivery, support and operating costs."
 f) Go-to-market — three staggered "falling block" cards (steps going up like Tetris stairs): Phase 1 Founder-led sales: turn Kapiva, SalarySe and warm intros into pilots and ~10 paying firms in year 1. Phase 2 Land and expand: expand seats and referrals to reach ~20 paying firms by month 24. Phase 3 US after next round: enter the US after the next financing; no PLG assumption yet.
 g) Team — Yashwant (IIT Roorkee, Co-Founder): Google · ML inference infrastructure; performance & compiler reliability; product, engineering & strategy. Roshan (IIT BHU, Co-Founder): former Software Engineer at Slice; former Co-Founder at Stonks AI; product & go-to-market. Line: "Key hires: founding engineers first; add a small GTM team after paid-pilot conversion." Use initials in colored block avatars (no photos).
 h) The ask — "Raising $500K seed." Donut chart: Engineering 60%, Go-to-market 25%, Operations 15%; Runway 24 months*. "This round unlocks": 1) Convert Kapiva and SalarySe to signed paid pilots; 2) Month 12 target: 10 firms, ~350 seats, ~$50K ARR; 3) Month 24 target: 20 firms, ~800 seats, ~$120K ARR. Footnote: "*Illustrative staged-hiring plan: ~$414K operating spend, ~$86K cash reserve. 60/25/15 allocation applies to planned spend."
 i) Investor CTA row: button "Talk to the founders" (mailto to both founders, subject "Tenet seed round: intro") and "Request the deck" (mailto, subject "Tenet: request pitch deck").
 Use charts built with simple SVG or Recharts, styled in the palette. Animate counters/bars once on scroll-in.

FAQ (cream) — "08 / FAQ", H2 "Questions you might have." Accordion (accessible, keyboard-friendly), 6 items, honest tone:
 1. Is Tenet available today? — "Not yet. We have a Figma prototype and a partially working MVP, and we're onboarding a small group of design partners for a private beta. Join the beta to get early access."
 2. How is this different from ChatGPT Projects, Notion AI or Glean/Rovo? — summarize the positioning section: they organize and answer from content; Tenet's unit is selectively shared reasoning plus an auditable decision record.
 3. Do my teammates see my private AI chats? — "No. You think privately with your own AI assistant and choose what to push into project memory: a prompt, a response, or both."
 4. What does the master agent do? — keeps memory current, answers questions about the project, and flags work that drifts from approved decisions.
 5. Where does it work? — "Inside Docs, Slides and Sheets." (Phrase as "designed to work inside", since the MVP is in progress.)
 6. What will it cost? — "₹999 per user/month in India, $15 per user/month elsewhere, one plan with every feature. Enterprise controls will be priced later."

BETA / CONTACT FORM (ink, id="beta") — "09 / Join the beta", H2 "Be one of the first teams to try Tenet." Left: short copy and the two founder emails shown as plain text links (yashwant.yadav.sde@gmail.com, roshan.jha003@gmail.com). Right: form card (paper on ink) with fields:
 - Full name (required)
 - Work email (required, validated)
 - Company (required)
 - Your role (select: Founder / Business head / Engineering lead / Engineer / Product / Investor / Other)
 - Team size (select: 1-10 / 11-50 / 51-200 / 201-1000 / 1000+)
 - How are you using AI at work today? (multi-select chips: ChatGPT, Claude, Gemini, Copilot, Notion AI, Other)
 - "I'm interested in…" (radio: Joining the beta / Running a paid pilot / Investing / Just exploring)
 - What's the biggest pain in your team's decisions? (textarea, optional)
 - Consent checkbox: "I'm happy for the Tenet founders to email me about this."
 Behavior (strictly static): on submit, validate client-side with inline error messages, then build a mailto: link to BOTH addresses (yashwant.yadav.sde@gmail.com,roshan.jha003@gmail.com), subject "Tenet beta request: {company} ({interest})", and a plain-text body listing each field on its own line, all encoded with encodeURIComponent, then set window.location.href to it. Show a success state: "Opening your email app… If nothing opened, copy your details below and email us." with a "Copy message" button (navigator.clipboard, with fallback) and the visible email addresses. Do not use localStorage, cookies, fetch, or any third-party form service. Add a small honest note: "This opens your email app with a pre-filled message. Nothing is sent until you press send."

FOOTER (ink with <Skyline>): "Tenet." wordmark, tagline "Work converges when decisions are on record.", the two emails, small links (How it works, Pricing, Investors, FAQ), © 2026 Tenet. Include text: "Illustrative UI shown. Product in development."

================================================================
4. TECHNICAL / QUALITY REQUIREMENTS
================================================================
- Fully responsive: desktop (1440), tablet (768), mobile (390). Mobile stacks cards, simplifies falling-block art, keeps CTAs thumb-reachable (sticky bottom "Join the beta" bar on mobile after scrolling past the hero).
- Accessibility: WCAG AA contrast (verify coral on ink and sun on ink), visible focus rings (sun on dark, ink on cream), semantic headings, labels on every form field, aria-expanded on accordion, aria-live for form errors/success, alt text on SVG art (decorative blocks aria-hidden).
- Performance: no external images; all art is SVG/CSS; only Google Fonts (Urbanist, Lato) as external resource; lazy-animate on scroll with IntersectionObserver.
- SEO/meta: title "Tenet: Shared AI memory and decision records for teams"; meta description "Shared AI memory and decision records for teams, so work converges in fewer iterations."; Open Graph tags; favicon = 2x2 colored block mark.
- Code organization: components for Nav, Hero, DecisionRecordCard, Problem, InsightBand, Solution, HowItWorksStepper, Demo, Positioning, Personas, Pricing, Investors (with sub-components), FAQ, BetaForm, Footer, plus BlockPiece, Skyline, FallGuide, Eyebrow, SectionHeader. All copy and numbers in a single content file so I can edit them easily.
- Keep every number exactly as written above. Do not add statistics, awards, customer logos, testimonials, security badges or press mentions.
- Tone of copy: plain, confident, specific; no hype words like "revolutionary", "supercharge", "game-changing". Short sentences.
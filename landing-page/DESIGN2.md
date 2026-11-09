Build a single-page, fully static marketing website for "Tenet", an early-stage startup. The page has two jobs: (1) a pitch microsite that investors will open alongside a pre-read, and (2) a landing page that converts business teams into private-beta signups. There is NO backend, NO API calls, NO auth. Use React + Tailwind, a single page with smooth-scroll anchor navigation.

=== PRODUCT CONTEXT (use only these facts; do not invent features, customers, metrics or logos) ===
Tenet is an AI-native collaboration workspace for shared reasoning. Teammates explore problems privately with AI, selectively share a prompt, an answer, or the full exchange into a shared project space, challenge each other's thinking (agree, push back, flag risks, add forecasts), and build a persistent record of how a project's decisions evolve. A project-level "master agent" retains all shared contributions and can answer later questions about progress, reasoning, objections and what the team considered. Positioning: collaborative articulation, not company-wide search.
Status: Figma prototype and a partially working MVP in development. Opening a private beta for design partners. The product is NOT live yet, so never use "Sign in", "Download" or "Start free trial". Use "Join the private beta".
Planned pricing: Rs 999 per user per month in India, $15 per user per month internationally.
Target customers: cross-functional project teams (business heads, product, marketing/growth, operations, finance) at growing companies, starting in India.
Founders: Yashwant (Co-Founder; product, engineering, strategy; IIT Roorkee; software and ML infrastructure at Google) and Roshan (Co-Founder; product and go-to-market; IIT BHU; former Software Engineer at Slice; former Co-Founder at Stonks AI).
Contact emails: yashwant.yadav.sde@gmail.com, roshan.jha003@gmail.com

=== DESIGN SYSTEM: "INK & PAPER" ===
Mood: calm, premium, editorial, trustworthy; a well-kept decision notebook rather than a neon AI product. Generous whitespace, hairline borders, soft shadows, subtle paper grain (very low opacity SVG noise) on the main background.
Colors (define as CSS variables / Tailwind theme tokens):
- Paper #F6F2EA (page background), Paper-2 #EFE9DD (alternate sections), Card #FFFDF8
- Ink #14161F (primary text and dark sections), Ink-soft #4A4E5A (secondary text), Hairline #DDD6C8
- Indigo #3430C9 (primary accent and CTAs), Indigo-dark #2824A8 (hover), Indigo-tint #E8E7FB
- Ember #F26B3A (used sparingly, ONLY for "push back" moments and tiny highlights)
- Moss #2E7D5B (agree), Sky #1F7AB8 (forecast)
Use exactly one dark section (Ink background, Paper text, faint indigo glow) for the final CTA/form so it lands with contrast. No purple-to-blue gradients, no glassmorphism, no emojis, no stock photos.
Typography (Google Fonts): headlines in "Instrument Serif" (clamp 40px mobile to 84px desktop, line-height 1.02, tight tracking) with ONE italic emphasis phrase per headline colored Indigo; body in "Inter" (17-18px, 1.6 line-height); labels/eyebrows in "JetBrains Mono" (12px, uppercase, wide tracking).
Shape: cards radius 20px, buttons fully rounded pills (min height 48px), 1px hairline borders. Max content width 1200px, section padding 112px desktop / 72px mobile.
Signature motif: PRIVATE vs SHARED. A "Private" chip is an ink-outlined pill with a lock icon. A "Shared" chip is a filled Indigo pill with a users icon. Reuse these everywhere. Second motif: a thin vertical "decision thread" line (ink hairline with small indigo nodes) that runs down the left margin of the How It Works section and draws itself as you scroll.
Logo: wordmark "Tenet" in Instrument Serif next to a small mark: an Indigo rounded square containing a white "T" whose crossbar is a thin line with a dot on each end (two people, one thread). Build it as inline SVG.
Motion: gentle fade-up on scroll (400ms, ease-out), hover lift on cards, the hero mockup plays a looping sequence. Respect prefers-reduced-motion (show static final state). No heavy libraries.

=== PAGE STRUCTURE AND COPY ===
0. Top announcement bar (Ink bg): "Private beta: now onboarding design partners  ->  Join the waitlist" (scrolls to the form).

1. Sticky nav: logo | How it works | Why Tenet | Use cases | Pricing | FAQ | [Join the private beta] pill button. Hamburger drawer on mobile. Nav gets a paper-colored blur background and hairline bottom border after scrolling.

2. HERO
Eyebrow: SHARED REASONING FOR TEAMS
H1: "Think privately with AI. *Decide together.*"
Sub: "Tenet is a collaboration workspace where teammates explore problems with AI in private, share only what's worth sharing, challenge each other's thinking, and keep a lasting record of why every decision was made."
Buttons: primary [Join the private beta], secondary [Watch the walkthrough] (links to [https://www.loom.com/share/87aac049b9ee48528cec39023c15fd9e], opens in new tab).
Micro-line under buttons: "Private by default. You choose what your team sees."
Hero visual (the star of the page): a large two-panel product mockup built in HTML/CSS (no images).
 - Left panel, titled "Aarav's private chat" with a Private chip: a short prompt ("Should we launch a Rs 499 trial pack in Q1? Check the churn numbers in the attached sheet.") and a concise AI answer. A "Share" button reveals a small menu: Prompt / Answer / Both.
 - Right panel, titled "Q1 Trial Pack decision" with a Shared chip: contribution cards appear one by one. Aarav's shared answer; Meera's reply tagged PUSH BACK (Ember): "The 30-day churn assumption looks optimistic for new cohorts."; Kabir's card tagged FORECAST (Sky); Ananya tagged AGREE (Moss). At the bottom an "Ask the project" input shows the master agent answering: "You moved from a Rs 499 pack to a Rs 699 starter bundle after Meera's churn objection."
 - Tiny caption below: "Illustrative concept". Panels overlap slightly with a soft shadow; on mobile stack vertically.
 - All names and numbers here are fictional example content.

1. PROBLEM (Paper-2 bg)
Eyebrow: THE PROBLEM
H2: "The output is shared. *The reasoning isn't.*"
Sub: "AI makes it easy for each person to produce research, proposals and analysis. It doesn't help a team converge on a decision."
Three cards with simple line icons:
 - "Reasoning hides in private chats": "Each teammate's best thinking is locked inside their own AI conversation."
 - "Pushback gets lost": "Objections, forecasts and trade-offs scatter across meetings, threads and document versions."
 - "No one can reconstruct the why": "Weeks later, the team can see the output, but not why alternatives were rejected or assumptions changed."
Then a large pull-quote card (serif, big quote marks): "When my juniors come back with follow-ups to a task, it's hard to understand how they reached a conclusion or what they took from their AI conversation. When the context gets bloated, it's also hard to stop them once they've drifted from the actual problem." Attribution: "Business Head, Kapiva" with small note "Shared with permission".

1. HOW IT WORKS (id="how")
Eyebrow: HOW IT WORKS
H2: "From private exploration to *shared understanding*."
Five numbered steps along the animated decision-thread line. Each step has title, one-line description and a small CSS mockup:
 01 "Open a space": "A project lead creates a collaboration space, invites colleagues and adds context: documents, spreadsheets and other project files."
 02 "Think privately": "Everyone works in their own AI conversation. Nothing is shared by default."
 03 "Share what matters": "Contribute a prompt, an answer, or the complete exchange. You decide the granularity."
 04 "Challenge and converge": "Teammates agree, push back, surface risks and add forecasts, refining the team's collective understanding."
 05 "Ask the project": "A project-level master agent remembers every shared contribution and answers later questions about progress, reasoning, objections and what the team considered."
Visual style for steps: alternating text/mockup rows on desktop, stacked on mobile.

1. WHY TENET (differentiation)
Eyebrow: WHY TENET
H2: "Not search. *Shared thinking.*"
Sub: "Many tools retrieve what your company already knows. Tenet is built around how a team's thinking comes together."
A clean comparison table (horizontally scrollable on mobile) with three columns: "Enterprise search and knowledge assistants", "AI docs and workspaces", "Tenet" (Tenet column highlighted with Indigo-tint background and a subtle border). Use generic category names, not competitor brand names. Rows:
 - Core job: "Find and retrieve existing knowledge" | "Write and organize documents" | "Help a team reason to a decision together"
 - Where AI thinking happens: "Query box over indexed content" | "Inside the document" | "Private conversations per teammate, shared by choice"
 - What gets shared: "Retrieved results" | "The finished document" | "A prompt, an answer or the full exchange, your call"
 - Pushback and forecasts: "Not the focus" | "Comments on text" | "First-class: agree, push back, risk, forecast"
 - Decision history: "Reconstruct from sources" | "Version history" | "A persistent record of how the decision evolved"
Footnote (honest tone, small): "These categories overlap with Tenet in places, and many tools are adding collaboration features. Tenet is designed around collaborative reasoning from the ground up."

1. USE CASES
Eyebrow: BUILT FOR REAL TEAM DECISIONS
H2: "Wherever a team has to *make the call.*"
Tabbed or card grid (tabs on desktop, accordion on mobile) with 5 examples, each with a one-line scenario and "What Tenet keeps": Pricing and packaging changes; Launch and go-to-market plans; Vendor or tool selection; Budget and hiring plans; Post-mortems and retros. Each shows a mini example thread. Label as "Example scenario". Small role chips: Business heads, Product, Growth, Operations, Finance.

1. PRINCIPLES (trust)
H2: "Your thinking stays *yours until you share it.*"
Four short cards: "Private by default" / "Granular sharing" (prompt, answer or both) / "Every contribution attributed" / "Decisions you can revisit". Add line: "Security and data-handling details are shared with beta partners." Do NOT claim any certifications or compliance badges.

1. ROADMAP / WHERE WE ARE (honest status)
H2: "Early, and building in the open."
A horizontal timeline (vertical on mobile) with status chips: "Done: Customer discovery (10 interviews)", "Done: Interactive prototype in Figma", "In progress: Working MVP", "Next: Private beta with design partners", "Next: Paid pilots", "Later: General availability". No dates. Add a line: "We're partnering with a small number of teams to shape the product." (do not name customers or show their logos).

1. PRICING (planned)
H2: "Simple per-seat pricing, *planned.*"
A single centered card with an India / International toggle (default India): "Rs 999 / user / month" or "$15 / user / month". Badge: "Planned pricing". Included: Private AI workspace for every teammate; Selective sharing into shared spaces; Project master agent; Decision history and record. Under it: "Beta partners help shape final pricing." CTA [Join the private beta].

1.  TEAM
H2: "Built by two founders who live this problem."
Two founder cards with large initials avatars (Indigo-tint circles with serif initials "Y" and "R"; leave a clear slot for a future photo), name, role, one-line bio from the context above, and a mailto link to their email. Make it easy to swap in photos later.

1.  FAQ (accordion, conversational)
Title: "Questions you might have."
 - "Is Tenet available today?" -> "Not yet. We have an interactive prototype and a working MVP in development, and we're opening a private beta for design partners."
 - "How is this different from ChatGPT Projects, Notion AI or enterprise search?" -> "Those tools are useful and overlap with Tenet in places. They focus mainly on shared context, documents or retrieval. Tenet focuses on how a team reasons together: private exploration, selective sharing, structured pushback and a lasting decision record."
 - "Can my teammates see my AI chats?" -> "No. Everything starts private. You choose what to share: a prompt, an answer, or the full exchange."
 - "What can the project master agent do?" -> "It retains the shared contributions in a project and can answer later questions about progress, reasoning, objections and what the team considered."
 - "What will it cost?" -> "Planned pricing is Rs 999 per user per month in India and $15 per user per month internationally."
 - "How do I get in the beta?" -> "Fill in the form below. We read every request and reply personally."

1.  FINAL CTA + FORM (id="join", the ONE dark Ink section)
Eyebrow: PRIVATE BETA
H2 (Paper text, italic phrase in a lighter indigo-tint): "Help us shape how teams *decide together.*"
Sub: "Tell us about your team. We'll reach out personally."
Form card (Card bg, radius 24, on the dark section) with fields:
 - "I'm reaching out as" (select, required): "A company interested in the private beta", "A company that wants to talk about a pilot", "An investor", "Something else"
 - Full name (required), Work email (required, validated), Company (required), Your role (required)
 - Team size (select): 1-10, 11-50, 51-200, 200+
 - "What decisions does your team struggle to make together?" (textarea, optional)
 - Submit button: "Send via email"
Behavior (STATIC, no server): on submit, validate required fields client-side with inline error messages, then build a mailto link: to = both founder emails comma-separated, subject = "Tenet private beta: {Company} ({Reaching out as})", body = all fields as readable lines, everything passed through encodeURIComponent, and navigate with window.location.href. Then replace the form with a success state: "Your email app should be opening. If nothing happened, you can [Open in Gmail] (a https://mail.google.com/mail/?view=cm link with the same to/subject/body), [Copy the message] (copies the composed text) or email us directly at the two addresses." Include a "Edit my details" button to go back. No localStorage, no fetch.
Below the form on dark bg: two plain mailto text links for the founders.

1.  FOOTER (Paper bg)
Logo + one-line "Shared reasoning for teams making decisions together." Links: How it works, Why Tenet, Pricing, FAQ, Contact (mailto), Investors (mailto with subject "Investor enquiry"). Bottom line: "(c) 2026 Tenet. Made in India. Tenet is in early development; product visuals are illustrative."

=== GLOBAL REQUIREMENTS ===
- Mobile-first: most Indian visitors will arrive on phones. Design and check 360px, 768px, 1280px+. Touch targets at least 44px. No horizontal page scroll.
- Accessibility: semantic landmarks, visible focus rings in Indigo, WCAG AA contrast, labels linked to inputs, aria-expanded on accordions, keyboard-operable tabs/toggle/menu, alt text or aria-hidden on decorative SVGs.
- Performance: no raster images; all illustration is inline SVG or CSS. Lightweight, no autoplay video.
- SEO/meta: title "Tenet | Shared reasoning for teams making decisions together", a 155-character meta description, Open Graph tags.
- Use real copy from this brief everywhere. No lorem ipsum.
- Do NOT: invent customer logos, testimonials, metrics, funding numbers or certifications; show the fundraising amount or financial targets anywhere; use words like "trusted by", "live", "sign in" or "free trial".
- Smooth scroll for anchors with a sticky-nav offset. Every "Join the private beta" button scrolls to #join.


UPDATE: add the product walkthrough video. Make these changes and leave everything else as is.

1. HERO: change the secondary button from "Watch the walkthrough" (external link) to a button that smooth-scrolls to the new #walkthrough section below. Add a small play-icon inside the button. Remove every reference to [https://www.loom.com/share/87aac049b9ee48528cec39023c15fd9e].

2. NEW SECTION, placed directly after the Hero and before the Problem section (id="walkthrough", Paper background):
Eyebrow: PRODUCT WALKTHROUGH
H2: "See Tenet in *two minutes.*"   (use "a few minutes" if you can't verify the length)
Sub: "A walkthrough of the current prototype, from private exploration to a shared decision record."
Layout: video centered at max-width 960px inside a Card-colored frame (radius 24, 1px Hairline border, soft shadow) with a thin top bar made of three small ink dots, like a browser window. Under the video, a small caption: "Early prototype. The product is in active development." and a quiet text link "Open on Loom" pointing to https://www.loom.com/share/87aac049b9ee48528cec39023c15fd9e (opens in a new tab).

1. EMBED IMPLEMENTATION (important):
- Use a "click to load" facade so the page stays fast: first render a styled poster in a 16:10-ish responsive box (Ink background, faint indigo glow, the product mockup silhouette or the Tenet mark, a large circular Indigo play button, and the label "Watch the walkthrough"). Only after the user clicks, replace the poster with the real iframe and add ?autoplay=1 to its src.
- The iframe must be this exact embed, converted to valid JSX (frameBorder, allowFullScreen, etc.):

<div style="position: relative; padding-bottom: 65.03401360544217%; height: 0;"><iframe src="https://www.loom.com/embed/87aac049b9ee48528cec39023c15fd9e" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe></div>

- Keep the 65.034% padding-bottom responsive wrapper so the video scales on mobile, and make the poster use the same aspect ratio so there is no layout jump when the iframe loads.
- Add title="Tenet product walkthrough" to the iframe, and make the poster a real <button> with an aria-label, keyboard focusable, with a visible Indigo focus ring.
- Add loading="lazy" semantics (the facade already defers loading).
- If the iframe fails to load, the "Open on Loom" link is the fallback.

4. NAV: add a "Walkthrough" link between "How it works" and "Why Tenet" that scrolls to #walkthrough (desktop and mobile drawer).

5. FOOTER: add a "Walkthrough" link to the footer link list.
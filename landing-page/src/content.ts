export const content = {
  nav: ["How it works", "Why Tenet", "Pricing", "Investors", "FAQ"],
  hero: {
    pill: "PRIVATE BETA · SEED ROUND NOV 2026",
    title: "Work converges when decisions are on record.",
    body: "Shared AI memory and decision records for teams, so work converges in fewer iterations.",
    note: "Built for teams that think with AI. Early access, no card needed.",
  },
  problem: {
    title: "Teams iterate in parallel and drift apart",
    cards: [
      [
        "01",
        "Context split across AI chats",
        "Each person works with their own AI, so findings get passed around one by one.",
      ],
      [
        "02",
        "Pushbacks get lost",
        "Challenges, forecasts and trade-offs vanish once the meeting or chat ends.",
      ],
      [
        "03",
        "Loops never close",
        "Teams reopen settled decisions and circle back instead of converging.",
      ],
    ],
    quote:
      "When my juniors come back with follow-ups to a task, it's hard to understand how they reached a conclusion or what they took from their AI conversation. When the context gets bloated, it's also hard to stop them once they've drifted from the actual problem.",
    attribution: "— Business Head, Series B startup (customer interview)",
  },
  insight: {
    title: "Producing work is cheap now. Deciding isn't.",
    body: "AI lets every team produce more docs, decks and analyses than leaders can review. Today's tools store the work, not the decision behind it.",
  },
  solution: {
    title: "One shared memory for the team, with every decision on record",
    cards: [
      [
        "Shared AI memory",
        "Every collaborator's findings, pushbacks and forecasts feed one project memory.",
      ],
      [
        "Decision records",
        "Each decision keeps what was decided, who approved it, and the challenges raised.",
      ],
      [
        "A master agent per project",
        "Keeps memory current, answers questions, flags work that drifts from approved decisions.",
      ],
    ],
  },
  workflow: [
    ["Contribute", "Each person shares what matters from their AI work to the project memory."],
    ["Challenge", "Teammates add pushbacks, risks and forecasts in one place."],
    ["Decide", "The owner records the call, with approvers and reasoning."],
    ["Maintain", "The master agent keeps everyone current and flags drift."],
  ],
  positioning: [
    ["Rovo / Glean", "Connected work data → answers, agents and automations"],
    ["Notion AI", "Documents and meetings → recaps, actions and decisions"],
    ["ChatGPT Projects", "Shared chats and files → project context and branching"],
  ],
  tenetDifference: [
    ["Think privately", "Research and explore with your own AI assistant."],
    ["Choose what becomes shared", "Push a prompt, a response, or both into project memory."],
    [
      "Challenge, decide, revisit",
      "Capture pushbacks and forecasts; query the project agent later.",
    ],
  ],
  personas: [
    [
      "Founders",
      "Decisions disappear into calls and scattered chats.",
      "See how every call was made, and by whom.",
    ],
    [
      "Business heads",
      "AI-assisted work arrives without its reasoning.",
      "Understand how a junior reached a conclusion, and catch drift early.",
    ],
    [
      "Lead engineers",
      "Settled architecture choices keep reopening.",
      "Stop re-litigating architecture decisions. The reasoning is on record.",
    ],
  ],
  investor: {
    whyNow: [
      ["Agents can hold memory", "Shared project context can surface changes over time."],
      ["AI use is fragmented", "Separate tools leave reasoning scattered across private chats."],
      ["Review can't keep up", "AI generates more than teams can review and align on."],
    ],
    spokenTo: [
      "Founders of Series A-funded startups",
      "A business head at a Series B startup",
      "Senior engineers at HighLevel and Harvey AI",
      "Staff engineers at LinkedIn, Stripe and Rubrik",
    ],
    market: [
      ["TAM", "$21.5B", "Global team collaboration software, 2025, IMARC Group"],
      ["SAM · US", "~$720M", "~100,000 US companies with 100-999 staff × 40 seats × $15/mo × 12"],
      ["SAM · India", "~$50M", "Est. ~10K firms × 40 seats × ₹999/mo × 12 ≈ ₹480 crore"],
      ["SOM · 2-yr goal", "~$120K ARR", "20 firms × 40 seats × $12.50/mo"],
    ],
    moat: [
      ["Compounding decision context", "Each recorded call adds useful context for the next one."],
      [
        "Context that survives handoffs",
        "Reasoning remains available when people or projects change.",
      ],
      [
        "Continuous alignment",
        "Project agents check later work against approved decisions and flag possible drift.",
      ],
    ],
    gtm: [
      [
        "Phase 1 · Founder-led sales",
        "Turn Kapiva, SalarySe and warm intros into pilots and ~10 paying firms in year 1.",
      ],
      [
        "Phase 2 · Land and expand",
        "Expand seats and referrals to reach ~20 paying firms by month 24.",
      ],
      [
        "Phase 3 · US after next round",
        "Enter the US after the next financing; no PLG assumption yet.",
      ],
    ],
    team: [
      [
        "YY",
        "Yashwant",
        "IIT Roorkee, Co-Founder",
        "Google · ML inference infrastructure; performance & compiler reliability; product, engineering & strategy.",
      ],
      [
        "RJ",
        "Roshan",
        "IIT BHU, Co-Founder",
        "Former Software Engineer at Slice; former Co-Founder at Stonks AI; product & go-to-market.",
      ],
    ],
  },
  faq: [
    [
      "Is Tenet available today?",
      "Not yet. We have a Figma prototype and a partially working MVP, and we're onboarding a small group of design partners for a private beta. Join the beta to get early access.",
    ],
    [
      "How is this different from ChatGPT Projects, Notion AI or Glean/Rovo?",
      "They organize and answer from content. Tenet's unit is selectively shared reasoning plus an auditable decision record.",
    ],
    [
      "Do my teammates see my private AI chats?",
      "No. You think privately with your own AI assistant and choose what to push into project memory: a prompt, a response, or both.",
    ],
    [
      "What does the master agent do?",
      "It keeps memory current, answers questions about the project, and flags work that drifts from approved decisions.",
    ],
    [
      "Where does it work?",
      "Tenet is designed to work inside Docs, Slides and Sheets. The MVP is in progress.",
    ],
    [
      "What will it cost?",
      "₹999 per user/month in India, $15 per user/month elsewhere, one plan with every feature. Enterprise controls will be priced later.",
    ],
  ],
  emails: ["yashwant.yadav.sde@gmail.com", "roshan.jha003@gmail.com"],
} as const;

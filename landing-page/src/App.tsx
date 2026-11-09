import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";

const founderEmails = "yashwant.yadav.sde@gmail.com,roshan.jha003@gmail.com";

function Icon({
  name,
  size = 18,
  className = "",
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  const paths: Record<string, ReactNode> = {
    lock: (
      <>
        <rect x="5" y="10" width="14" height="10" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </>
    ),
    users: (
      <>
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </>
    ),
    arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
    menu: (
      <>
        <path d="M4 7h16M4 12h16M4 17h16" />
      </>
    ),
    close: (
      <>
        <path d="M6 6l12 12M18 6 6 18" />
      </>
    ),
    external: (
      <>
        <path d="M15 4h5v5M10 14 20 4" />
        <path d="M20 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h6" />
      </>
    ),
    brain: (
      <>
        <path d="M9.5 4.5A3 3 0 0 0 4 6v.5A3.5 3.5 0 0 0 3 13a3 3 0 0 0 3 4.5A3.5 3.5 0 0 0 9.5 21Z" />
        <path d="M14.5 4.5A3 3 0 0 1 20 6v.5a3.5 3.5 0 0 1 1 6.5 3 3 0 0 1-3 4.5 3.5 3.5 0 0 1-3.5 3.5ZM9.5 8h-2M14.5 8h2M9.5 15H7M14.5 15h2M9.5 4.5v16M14.5 4.5v16" />
      </>
    ),
    message: (
      <>
        <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z" />
        <path d="M8 9h8M8 13h5" />
      </>
    ),
    history: (
      <>
        <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
        <path d="M3 3v5h5M12 7v5l3 2" />
      </>
    ),
    file: (
      <>
        <path d="M6 2h8l4 4v16H6Z" />
        <path d="M14 2v5h5M9 13h6M9 17h6" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    copy: (
      <>
        <rect x="8" y="8" width="12" height="12" rx="2" />
        <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
      </>
    ),
    mail: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m3 7 9 6 9-6" />
      </>
    ),
    chevron: <path d="m6 9 6 6 6-6" />,
  };
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function Logo({ light = false }: { light?: boolean }) {
  return (
    <a className={`logo ${light ? "logo-light" : ""}`} href="#top" aria-label="Tenet home">
      <svg viewBox="0 0 38 38" aria-hidden="true">
        <rect width="38" height="38" rx="10" fill="#3430C9" />
        <path d="M11 12h16M19 12v16" stroke="white" strokeWidth="2.25" strokeLinecap="round" />
        <circle cx="11" cy="12" r="2" fill="white" />
        <circle cx="27" cy="12" r="2" fill="white" />
      </svg>
      <span>Tenet</span>
    </a>
  );
}

function PrivacyChip({ shared = false }: { shared?: boolean }) {
  return (
    <span className={`privacy-chip ${shared ? "shared" : ""}`}>
      <Icon name={shared ? "users" : "lock"} size={13} />
      {shared ? "Shared" : "Private"}
    </span>
  );
}

function Eyebrow({ children, light = false }: { children: ReactNode; light?: boolean }) {
  return <p className={`eyebrow ${light ? "eyebrow-light" : ""}`}>{children}</p>;
}

function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      ([entry]) => entry.isIntersecting && node.classList.add("is-visible"),
      { threshold: 0.12 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={ref} className={`reveal ${className}`}>
      {children}
    </div>
  );
}

function HeroMockup() {
  const [menu, setMenu] = useState(false);
  return (
    <div className="product-shell" aria-label="Illustrative Tenet product concept">
      <div className="mock-private">
        <div className="mock-toolbar">
          <div>
            <span className="mock-kicker">PRIVATE WORKSPACE</span>
            <strong>Aarav's private chat</strong>
          </div>
          <PrivacyChip />
        </div>
        <div className="chat-stack">
          <div className="prompt-bubble">
            <span>You</span>
            Should we launch a Rs 499 trial pack in Q1? Check the churn numbers in the attached
            sheet.
            <div className="attachment">
              <Icon name="file" size={14} /> cohort-analysis.xlsx
            </div>
          </div>
          <div className="ai-answer">
            <div className="agent-mark">T</div>
            <div>
              <span>Tenet AI</span>
              <p>
                The Rs 499 trial could improve conversion, but current 30-day churn makes margin
                recovery uncertain. Consider testing a Rs 699 starter bundle with stronger retention
                value.
              </p>
            </div>
          </div>
        </div>
        <div className="share-wrap">
          <button className="share-button" onClick={() => setMenu(!menu)} aria-expanded={menu}>
            Share to project <Icon name="chevron" size={15} />
          </button>
          {menu && (
            <div className="share-menu">
              <button onClick={() => setMenu(false)}>Prompt</button>
              <button onClick={() => setMenu(false)}>Answer</button>
              <button onClick={() => setMenu(false)}>Both</button>
            </div>
          )}
        </div>
      </div>
      <div className="mock-shared">
        <div className="mock-toolbar">
          <div>
            <span className="mock-kicker">PROJECT SPACE</span>
            <strong>Q1 Trial Pack decision</strong>
          </div>
          <PrivacyChip shared />
        </div>
        <div className="contributions">
          <Contribution initials="AA" name="Aarav" tag="SHARED ANSWER">
            The Rs 499 trial could improve conversion, but margin recovery is uncertain.
          </Contribution>
          <Contribution initials="MS" name="Meera" tag="PUSH BACK" tone="ember">
            The 30-day churn assumption looks optimistic for new cohorts.
          </Contribution>
          <Contribution initials="KR" name="Kabir" tag="FORECAST" tone="sky">
            A Rs 699 starter bundle could retain 12–15% more customers.
          </Contribution>
          <Contribution initials="AN" name="Ananya" tag="AGREE" tone="moss">
            Agree. The bundle gives Growth a clearer value story to test.
          </Contribution>
        </div>
        <div className="project-answer">
          <div className="ask-line">
            <span>Ask the project</span>
            <Icon name="arrow" size={15} />
          </div>
          <p>
            You moved from a Rs 499 pack to a Rs 699 starter bundle after Meera's churn objection.
          </p>
        </div>
      </div>
    </div>
  );
}

function Contribution({
  initials,
  name,
  tag,
  tone = "indigo",
  children,
}: {
  initials: string;
  name: string;
  tag: string;
  tone?: string;
  children: ReactNode;
}) {
  return (
    <div className="contribution">
      <div className="mini-avatar">{initials}</div>
      <div>
        <div className="contribution-meta">
          <strong>{name}</strong>
          <span className={`tag tag-${tone}`}>{tag}</span>
        </div>
        <p>{children}</p>
      </div>
    </div>
  );
}

const problemCards = [
  {
    icon: "brain",
    title: "Reasoning hides in private chats",
    copy: "Each teammate's best thinking is locked inside their own AI conversation.",
  },
  {
    icon: "message",
    title: "Pushback gets lost",
    copy: "Objections, forecasts and trade-offs scatter across meetings, threads and document versions.",
  },
  {
    icon: "history",
    title: "No one can reconstruct the why",
    copy: "Weeks later, the team can see the output, but not why alternatives were rejected or assumptions changed.",
  },
];

const steps = [
  {
    title: "Open a space",
    copy: "A project lead creates a collaboration space, invites colleagues and adds context: documents, spreadsheets and other project files.",
    visual: "space",
  },
  {
    title: "Think privately",
    copy: "Everyone works in their own AI conversation. Nothing is shared by default.",
    visual: "private",
  },
  {
    title: "Share what matters",
    copy: "Contribute a prompt, an answer, or the complete exchange. You decide the granularity.",
    visual: "share",
  },
  {
    title: "Challenge and converge",
    copy: "Teammates agree, push back, surface risks and add forecasts, refining the team's collective understanding.",
    visual: "challenge",
  },
  {
    title: "Ask the project",
    copy: "A project-level master agent remembers every shared contribution and answers later questions about progress, reasoning, objections and what the team considered.",
    visual: "ask",
  },
];

function StepVisual({ type }: { type: string }) {
  if (type === "space")
    return (
      <div className="step-mock">
        <div className="step-title">
          <span className="step-icon">
            <Icon name="users" size={16} />
          </span>{" "}
          Q1 Packaging
        </div>
        <div className="file-row">
          <Icon name="file" size={15} /> Churn analysis.xlsx <span>2.4 MB</span>
        </div>
        <div className="file-row">
          <Icon name="file" size={15} /> Customer notes.pdf <span>1.1 MB</span>
        </div>
        <div className="avatar-row">
          <span>AA</span>
          <span>MS</span>
          <span>KR</span>
          <i>+2</i>
        </div>
      </div>
    );
  if (type === "private")
    return (
      <div className="step-mock">
        <div className="mock-toolbar compact">
          <strong>My exploration</strong>
          <PrivacyChip />
        </div>
        <div className="mini-chat right">What assumptions should we test first?</div>
        <div className="mini-chat">Start with churn sensitivity and contribution margin.</div>
      </div>
    );
  if (type === "share")
    return (
      <div className="step-mock share-choices">
        <p>Choose what your team sees</p>
        <button>
          <span>Prompt</span>
          <Icon name="arrow" size={15} />
        </button>
        <button>
          <span>Answer</span>
          <Icon name="arrow" size={15} />
        </button>
        <button className="selected">
          <span>Prompt + answer</span>
          <Icon name="check" size={15} />
        </button>
      </div>
    );
  if (type === "challenge")
    return (
      <div className="step-mock reaction-mock">
        <div>
          <span className="tag tag-moss">AGREE</span>
          <p>Stronger value story for customers.</p>
        </div>
        <div>
          <span className="tag tag-ember">PUSH BACK</span>
          <p>Churn assumption needs another look.</p>
        </div>
        <div>
          <span className="tag tag-sky">FORECAST</span>
          <p>Retention could improve by 12–15%.</p>
        </div>
      </div>
    );
  return (
    <div className="step-mock ask-mock">
      <p className="ask-prompt">Why did we move away from Rs 499?</p>
      <div className="answer-line">
        <div className="agent-mark">T</div>
        <p>
          Churn risk changed the team's view. The shared record shows the objection and the
          alternative considered.
        </p>
      </div>
    </div>
  );
}

const comparisonRows = [
  [
    "Core job",
    "Find and retrieve existing knowledge",
    "Write and organize documents",
    "Help a team reason to a decision together",
  ],
  [
    "Where AI thinking happens",
    "Query box over indexed content",
    "Inside the document",
    "Private conversations per teammate, shared by choice",
  ],
  [
    "What gets shared",
    "Retrieved results",
    "The finished document",
    "A prompt, an answer or the full exchange, your call",
  ],
  [
    "Pushback and forecasts",
    "Not the focus",
    "Comments on text",
    "First-class: agree, push back, risk, forecast",
  ],
  [
    "Decision history",
    "Reconstruct from sources",
    "Version history",
    "A persistent record of how the decision evolved",
  ],
];

const cases = [
  {
    title: "Pricing and packaging changes",
    scenario: "Should the team launch a lower-priced trial or a higher-value starter bundle?",
    keeps: "Assumptions, churn objections, margin trade-offs and the final packaging rationale.",
    role: "Business heads",
    tag: "PUSH BACK",
    tone: "ember",
  },
  {
    title: "Launch and go-to-market plans",
    scenario: "Which audience, message and channel should lead a new product launch?",
    keeps: "Research, positioning alternatives, channel forecasts and why the team chose its plan.",
    role: "Growth",
    tag: "FORECAST",
    tone: "sky",
  },
  {
    title: "Vendor or tool selection",
    scenario: "Which vendor best balances capability, cost, migration effort and risk?",
    keeps: "Evaluation criteria, objections, hidden constraints and the decision trail.",
    role: "Operations",
    tag: "RISK",
    tone: "ember",
  },
  {
    title: "Budget and hiring plans",
    scenario: "Where should limited budget and headcount go next quarter?",
    keeps: "Competing priorities, business cases, forecasts and allocation reasoning.",
    role: "Finance",
    tag: "FORECAST",
    tone: "sky",
  },
  {
    title: "Post-mortems and retros",
    scenario: "What happened, which assumptions failed and what should change next time?",
    keeps: "Individual perspectives, evidence, disagreements and agreed follow-through.",
    role: "Product",
    tag: "AGREE",
    tone: "moss",
  },
];

function UseCases() {
  const [active, setActive] = useState(0);
  return (
    <div className="use-case-layout">
      <div className="case-tabs" role="tablist" aria-label="Use case examples">
        {cases.map((item, index) => (
          <button
            key={item.title}
            role="tab"
            aria-selected={active === index}
            aria-controls={`case-panel-${index}`}
            id={`case-tab-${index}`}
            className={active === index ? "active" : ""}
            onClick={() => setActive(index)}
          >
            <span>0{index + 1}</span>
            {item.title}
            <Icon name="arrow" />
          </button>
        ))}
      </div>
      <div
        className="case-detail"
        role="tabpanel"
        id={`case-panel-${active}`}
        aria-labelledby={`case-tab-${active}`}
      >
        <div className="case-labels">
          <span className="example-label">EXAMPLE SCENARIO</span>
          <span className="role-chip">{cases[active].role}</span>
        </div>
        <h3>{cases[active].title}</h3>
        <p className="case-scenario">{cases[active].scenario}</p>
        <div className="example-thread">
          <div className="thread-person">A</div>
          <div>
            <span className={`tag tag-${cases[active].tone}`}>{cases[active].tag}</span>
            <p>{cases[active].scenario}</p>
          </div>
        </div>
        <div className="keeps">
          <span>WHAT TENET KEEPS</span>
          <p>{cases[active].keeps}</p>
        </div>
      </div>
    </div>
  );
}

const faqs = [
  [
    "Is Tenet available today?",
    "Not yet. We have an interactive prototype and a working MVP in development, and we’re opening a private beta for design partners.",
  ],
  [
    "How is this different from ChatGPT Projects, Notion AI or enterprise search?",
    "Those tools are useful and overlap with Tenet in places. They focus mainly on shared context, documents or retrieval. Tenet focuses on how a team reasons together: private exploration, selective sharing, structured pushback and a lasting decision record.",
  ],
  [
    "Can my teammates see my AI chats?",
    "No. Everything starts private. You choose what to share: a prompt, an answer, or the full exchange.",
  ],
  [
    "What can the project master agent do?",
    "It retains the shared contributions in a project and can answer later questions about progress, reasoning, objections and what the team considered.",
  ],
  [
    "What will it cost?",
    "Planned pricing is Rs 999 per user per month in India and $15 per user per month internationally.",
  ],
  [
    "How do I get in the beta?",
    "Fill in the form below. We read every request and reply personally.",
  ],
];

function FAQ() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="faq-list">
      {faqs.map(([question, answer], index) => (
        <div className={`faq-item ${open === index ? "open" : ""}`} key={question}>
          <button
            onClick={() => setOpen(open === index ? null : index)}
            aria-expanded={open === index}
            aria-controls={`faq-answer-${index}`}
          >
            <span>{question}</span>
            <span className="faq-plus" aria-hidden="true">
              +
            </span>
          </button>
          <div id={`faq-answer-${index}`} className="faq-answer" hidden={open !== index}>
            <p>{answer}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

type FormData = {
  intent: string;
  name: string;
  email: string;
  company: string;
  role: string;
  size: string;
  decisions: string;
};

const initialForm: FormData = {
  intent: "",
  name: "",
  email: "",
  company: "",
  role: "",
  size: "1-10",
  decisions: "",
};

function BetaForm() {
  const [data, setData] = useState<FormData>(initialForm);
  const [errors, setErrors] = useState<Partial<FormData>>({});
  const [sent, setSent] = useState(false);
  const [copied, setCopied] = useState(false);

  const subject = `Tenet private beta: ${data.company} (${data.intent})`;
  const message = [
    "Tenet private beta enquiry",
    "",
    `Reaching out as: ${data.intent}`,
    `Full name: ${data.name}`,
    `Work email: ${data.email}`,
    `Company: ${data.company}`,
    `Role: ${data.role}`,
    `Team size: ${data.size}`,
    "",
    "Decisions the team struggles to make together:",
    data.decisions || "Not provided",
  ].join("\n");
  const mailto = `mailto:${founderEmails}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(message)}`;
  const gmail = `https://mail.google.com/mail/?view=cm&to=${encodeURIComponent(founderEmails)}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(message)}`;

  function update(field: keyof FormData, value: string) {
    setData((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors: Partial<FormData> = {};
    if (!data.intent) nextErrors.intent = "Please choose an option.";
    if (!data.name.trim()) nextErrors.name = "Please enter your full name.";
    if (!data.email.trim()) nextErrors.email = "Please enter your work email.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email))
      nextErrors.email = "Please enter a valid email address.";
    if (!data.company.trim()) nextErrors.company = "Please enter your company.";
    if (!data.role.trim()) nextErrors.role = "Please enter your role.";
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      requestAnimationFrame(() =>
        document.querySelector<HTMLElement>('[data-error="true"]')?.focus(),
      );
      return;
    }
    setSent(true);
    window.location.href = mailto;
  }

  async function copyMessage() {
    await navigator.clipboard.writeText(`To: ${founderEmails}\nSubject: ${subject}\n\n${message}`);
    setCopied(true);
  }

  if (sent)
    return (
      <div className="form-card success-card" aria-live="polite">
        <div className="success-icon">
          <Icon name="mail" size={27} />
        </div>
        <Eyebrow>MESSAGE READY</Eyebrow>
        <h3>Your email app should be opening.</h3>
        <p>If nothing happened, choose another way to send your note:</p>
        <div className="success-actions">
          <a href={gmail} target="_blank" rel="noreferrer" className="button button-primary">
            Open in Gmail <Icon name="external" size={16} />
          </a>
          <button className="button button-secondary" onClick={copyMessage}>
            <Icon name={copied ? "check" : "copy"} size={16} />{" "}
            {copied ? "Message copied" : "Copy the message"}
          </button>
        </div>
        <p className="direct-email">
          Or email us directly at{" "}
          <a href="mailto:yashwant.yadav.sde@gmail.com">yashwant.yadav.sde@gmail.com</a> and{" "}
          <a href="mailto:roshan.jha003@gmail.com">roshan.jha003@gmail.com</a>.
        </p>
        <button className="edit-button" onClick={() => setSent(false)}>
          Edit my details
        </button>
      </div>
    );

  return (
    <form className="form-card" onSubmit={submit} noValidate>
      <div className="field field-full">
        <label htmlFor="intent">
          I'm reaching out as <span aria-hidden="true">*</span>
        </label>
        <select
          id="intent"
          value={data.intent}
          onChange={(e) => update("intent", e.target.value)}
          aria-invalid={!!errors.intent}
          data-error={errors.intent ? "true" : undefined}
        >
          <option value="">Choose one</option>
          <option>A company interested in the private beta</option>
          <option>A company that wants to talk about a pilot</option>
          <option>An investor</option>
          <option>Something else</option>
        </select>
        {errors.intent && <span className="field-error">{errors.intent}</span>}
      </div>
      <div className="form-grid">
        <div className="field">
          <label htmlFor="full-name">
            Full name <span aria-hidden="true">*</span>
          </label>
          <input
            id="full-name"
            value={data.name}
            onChange={(e) => update("name", e.target.value)}
            autoComplete="name"
            aria-invalid={!!errors.name}
            data-error={errors.name ? "true" : undefined}
          />
          {errors.name && <span className="field-error">{errors.name}</span>}
        </div>
        <div className="field">
          <label htmlFor="work-email">
            Work email <span aria-hidden="true">*</span>
          </label>
          <input
            id="work-email"
            type="email"
            value={data.email}
            onChange={(e) => update("email", e.target.value)}
            autoComplete="email"
            aria-invalid={!!errors.email}
            data-error={errors.email ? "true" : undefined}
          />
          {errors.email && <span className="field-error">{errors.email}</span>}
        </div>
        <div className="field">
          <label htmlFor="company">
            Company <span aria-hidden="true">*</span>
          </label>
          <input
            id="company"
            value={data.company}
            onChange={(e) => update("company", e.target.value)}
            autoComplete="organization"
            aria-invalid={!!errors.company}
            data-error={errors.company ? "true" : undefined}
          />
          {errors.company && <span className="field-error">{errors.company}</span>}
        </div>
        <div className="field">
          <label htmlFor="role">
            Your role <span aria-hidden="true">*</span>
          </label>
          <input
            id="role"
            value={data.role}
            onChange={(e) => update("role", e.target.value)}
            autoComplete="organization-title"
            aria-invalid={!!errors.role}
            data-error={errors.role ? "true" : undefined}
          />
          {errors.role && <span className="field-error">{errors.role}</span>}
        </div>
        <div className="field field-full">
          <label htmlFor="size">Team size</label>
          <select id="size" value={data.size} onChange={(e) => update("size", e.target.value)}>
            <option>1-10</option>
            <option>11-50</option>
            <option>51-200</option>
            <option>200+</option>
          </select>
        </div>
        <div className="field field-full">
          <label htmlFor="decisions">
            What decisions does your team struggle to make together?{" "}
            <span className="optional">Optional</span>
          </label>
          <textarea
            id="decisions"
            rows={4}
            value={data.decisions}
            onChange={(e) => update("decisions", e.target.value)}
          />
        </div>
      </div>
      <button className="button button-primary form-submit" type="submit">
        Send via email <Icon name="arrow" size={17} />
      </button>
      <p className="form-note">Your details are only used to respond to this enquiry.</p>
    </form>
  );
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [international, setInternational] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  const closeMenu = () => setMenuOpen(false);

  return (
    <div id="top">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <div className="announcement">
        <a href="#join">
          Private beta: now onboarding design partners <Icon name="arrow" size={15} />{" "}
          <span>Join the waitlist</span>
        </a>
      </div>
      <header className={`site-header ${scrolled ? "scrolled" : ""}`}>
        <nav className="nav-wrap" aria-label="Main navigation">
          <Logo />
          <div className="desktop-nav">
            <a href="#how">How it works</a>
            <a href="#why">Why Tenet</a>
            <a href="#use-cases">Use cases</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
          </div>
          <a className="button button-primary nav-cta" href="#join">
            Join the private beta
          </a>
          <button
            className="mobile-menu-button"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
          >
            <Icon name={menuOpen ? "close" : "menu"} size={23} />
          </button>
        </nav>
        <div className={`mobile-menu ${menuOpen ? "open" : ""}`} id="mobile-menu">
          <a href="#how" onClick={closeMenu}>
            How it works
          </a>
          <a href="#why" onClick={closeMenu}>
            Why Tenet
          </a>
          <a href="#use-cases" onClick={closeMenu}>
            Use cases
          </a>
          <a href="#pricing" onClick={closeMenu}>
            Pricing
          </a>
          <a href="#faq" onClick={closeMenu}>
            FAQ
          </a>
          <a className="button button-primary" href="#join" onClick={closeMenu}>
            Join the private beta
          </a>
        </div>
      </header>

      <main id="main">
        <section className="hero section">
          <div className="container">
            <Reveal className="hero-copy">
              <Eyebrow>SHARED REASONING FOR TEAMS</Eyebrow>
              <h1>
                Think privately with AI. <em>Decide together.</em>
              </h1>
              <p className="hero-sub">
                Tenet is a collaboration workspace where teammates explore problems with AI in
                private, share only what's worth sharing, challenge each other's thinking, and keep
                a lasting record of why every decision was made.
              </p>
              <div className="hero-actions">
                <a className="button button-primary" href="#join">
                  Join the private beta <Icon name="arrow" size={17} />
                </a>
                <a
                  className="button button-secondary"
                  href="https://www.loom.com/share/87aac049b9ee48528cec39023c15fd9e"
                  target="_blank"
                  rel="noreferrer"
                >
                  Watch the walkthrough <Icon name="external" size={16} />
                </a>
              </div>
              <div className="micro-line">
                <Icon name="lock" size={14} /> Private by default. You choose what your team sees.
              </div>
            </Reveal>
            <Reveal className="hero-visual">
              <HeroMockup />
              <p className="visual-caption">
                Illustrative concept{" "}
                <span>All names and numbers are fictional example content.</span>
              </p>
            </Reveal>
          </div>
        </section>

        <section className="section problem-section">
          <div className="container">
            <Reveal className="section-heading">
              <Eyebrow>THE PROBLEM</Eyebrow>
              <h2>
                The output is shared. <em>The reasoning isn't.</em>
              </h2>
              <p>
                AI makes it easy for each person to produce research, proposals and analysis. It
                doesn't help a team converge on a decision.
              </p>
            </Reveal>
            <div className="problem-grid">
              {problemCards.map((card, index) => (
                <Reveal className="problem-card" key={card.title}>
                  <span className="card-number">0{index + 1}</span>
                  <div className="line-icon">
                    <Icon name={card.icon} size={25} />
                  </div>
                  <h3>{card.title}</h3>
                  <p>{card.copy}</p>
                </Reveal>
              ))}
            </div>
            <Reveal className="quote-card">
              <span className="quote-mark">“</span>
              <blockquote>
                When my juniors come back with follow-ups to a task, it's hard to understand how
                they reached a conclusion or what they took from their AI conversation. When the
                context gets bloated, it's also hard to stop them once they've drifted from the
                actual problem.
              </blockquote>
              <div className="quote-attribution">
                <span>BH</span>
                <p>
                  <strong>Business Head, Kapiva</strong>
                  <small>Shared with permission</small>
                </p>
              </div>
            </Reveal>
          </div>
        </section>

        <section className="section how-section" id="how">
          <div className="container">
            <Reveal className="section-heading">
              <Eyebrow>HOW IT WORKS</Eyebrow>
              <h2>
                From private exploration to <em>shared understanding.</em>
              </h2>
            </Reveal>
            <div className="steps">
              <div className="decision-line" aria-hidden="true" />
              {steps.map((step, index) => (
                <Reveal className={`step ${index % 2 ? "reverse" : ""}`} key={step.title}>
                  <span className="step-node" aria-hidden="true" />
                  <div className="step-copy">
                    <span className="step-number">0{index + 1}</span>
                    <h3>{step.title}</h3>
                    <p>{step.copy}</p>
                    {index === 1 && <PrivacyChip />}
                    {index === 2 && (
                      <div className="chip-pair">
                        <PrivacyChip />
                        <Icon name="arrow" size={16} />
                        <PrivacyChip shared />
                      </div>
                    )}
                  </div>
                  <StepVisual type={step.visual} />
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="section why-section" id="why">
          <div className="container">
            <Reveal className="section-heading">
              <Eyebrow>WHY TENET</Eyebrow>
              <h2>
                Not search. <em>Shared thinking.</em>
              </h2>
              <p>
                Many tools retrieve what your company already knows. Tenet is built around how a
                team's thinking comes together.
              </p>
            </Reveal>
            <Reveal className="comparison-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">COMPARISON</th>
                    <th scope="col">Enterprise search and knowledge assistants</th>
                    <th scope="col">AI docs and workspaces</th>
                    <th scope="col">
                      <span className="tenet-table-mark">T</span> Tenet
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {comparisonRows.map((row) => (
                    <tr key={row[0]}>
                      {row.map((cell, index) =>
                        index === 0 ? (
                          <th scope="row" key={cell}>
                            {cell}
                          </th>
                        ) : (
                          <td key={cell}>
                            {index === 3 && <Icon name="check" size={15} />}
                            {cell}
                          </td>
                        ),
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Reveal>
            <p className="table-note">
              These categories overlap with Tenet in places, and many tools are adding collaboration
              features. Tenet is designed around collaborative reasoning from the ground up.
            </p>
          </div>
        </section>

        <section className="section use-cases-section" id="use-cases">
          <div className="container">
            <Reveal className="section-heading">
              <Eyebrow>BUILT FOR REAL TEAM DECISIONS</Eyebrow>
              <h2>
                Wherever a team has to <em>make the call.</em>
              </h2>
              <div className="role-list">
                <span>Business heads</span>
                <span>Product</span>
                <span>Growth</span>
                <span>Operations</span>
                <span>Finance</span>
              </div>
            </Reveal>
            <Reveal>
              <UseCases />
            </Reveal>
          </div>
        </section>

        <section className="section principles-section">
          <div className="container">
            <Reveal className="section-heading centered">
              <Eyebrow>BUILT ON CLEAR PRINCIPLES</Eyebrow>
              <h2>
                Your thinking stays <em>yours until you share it.</em>
              </h2>
            </Reveal>
            <div className="principles-grid">
              {[
                [
                  "lock",
                  "Private by default",
                  "Your personal AI conversations stay visible only to you.",
                ],
                [
                  "arrow",
                  "Granular sharing",
                  "Share a prompt, an answer or both—the choice is yours.",
                ],
                [
                  "users",
                  "Every contribution attributed",
                  "Ideas and challenges keep the name of the person who shared them.",
                ],
                [
                  "history",
                  "Decisions you can revisit",
                  "Return to the reasoning, objections and alternatives behind the call.",
                ],
              ].map(([icon, title, copy]) => (
                <Reveal className="principle-card" key={title}>
                  <div className="line-icon">
                    <Icon name={icon} size={23} />
                  </div>
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </Reveal>
              ))}
            </div>
            <p className="security-note">
              <Icon name="lock" size={15} /> Security and data-handling details are shared with beta
              partners.
            </p>
          </div>
        </section>

        <section className="section roadmap-section">
          <div className="container">
            <Reveal className="roadmap-heading">
              <div>
                <Eyebrow>WHERE WE ARE</Eyebrow>
                <h2>Early, and building in the open.</h2>
              </div>
              <p>We're partnering with a small number of teams to shape the product.</p>
            </Reveal>
            <Reveal className="timeline">
              {[
                ["Done", "Customer discovery", "10 interviews"],
                ["Done", "Interactive prototype", "in Figma"],
                ["In progress", "Working MVP", ""],
                ["Next", "Private beta", "with design partners"],
                ["Next", "Paid pilots", ""],
                ["Later", "General availability", ""],
              ].map(([status, title, note], index) => (
                <div
                  className={`timeline-item status-${status.toLowerCase().replace(" ", "-")}`}
                  key={title}
                >
                  <span className="timeline-dot">{index + 1}</span>
                  <span className="status-chip">{status}</span>
                  <strong>{title}</strong>
                  {note && <small>{note}</small>}
                </div>
              ))}
            </Reveal>
          </div>
        </section>

        <section className="section pricing-section" id="pricing">
          <div className="container">
            <Reveal className="section-heading centered">
              <Eyebrow>PRICING</Eyebrow>
              <h2>
                Simple per-seat pricing, <em>planned.</em>
              </h2>
            </Reveal>
            <Reveal className="pricing-card">
              <span className="planned-badge">PLANNED PRICING</span>
              <div className="price-toggle" role="group" aria-label="Pricing region">
                <button
                  className={!international ? "active" : ""}
                  aria-pressed={!international}
                  onClick={() => setInternational(false)}
                >
                  India
                </button>
                <button
                  className={international ? "active" : ""}
                  aria-pressed={international}
                  onClick={() => setInternational(true)}
                >
                  International
                </button>
              </div>
              <div className="price">
                <span>{international ? "$15" : "Rs 999"}</span>
                <small>/ user / month</small>
              </div>
              <div className="price-divider" />
              <ul>
                {[
                  "Private AI workspace for every teammate",
                  "Selective sharing into shared spaces",
                  "Project master agent",
                  "Decision history and record",
                ].map((item) => (
                  <li key={item}>
                    <span>
                      <Icon name="check" size={14} />
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
              <p>Beta partners help shape final pricing.</p>
              <a className="button button-primary" href="#join">
                Join the private beta <Icon name="arrow" size={17} />
              </a>
            </Reveal>
          </div>
        </section>

        <section className="section team-section">
          <div className="container">
            <Reveal className="section-heading">
              <Eyebrow>THE FOUNDERS</Eyebrow>
              <h2>Built by two founders who live this problem.</h2>
            </Reveal>
            <div className="team-grid">
              <Reveal className="founder-card">
                <div className="founder-avatar" data-photo-slot="true">
                  Y
                </div>
                <div>
                  <span className="founder-role">CO-FOUNDER</span>
                  <h3>Yashwant</h3>
                  <p>
                    Product, engineering and strategy. IIT Roorkee; software and ML infrastructure
                    at Google.
                  </p>
                  <a href="mailto:yashwant.yadav.sde@gmail.com">
                    <Icon name="mail" size={16} /> yashwant.yadav.sde@gmail.com
                  </a>
                </div>
              </Reveal>
              <Reveal className="founder-card">
                <div className="founder-avatar" data-photo-slot="true">
                  R
                </div>
                <div>
                  <span className="founder-role">CO-FOUNDER</span>
                  <h3>Roshan</h3>
                  <p>
                    Product and go-to-market. IIT BHU; former Software Engineer at Slice; former
                    Co-Founder at Stonks AI.
                  </p>
                  <a href="mailto:roshan.jha003@gmail.com">
                    <Icon name="mail" size={16} /> roshan.jha003@gmail.com
                  </a>
                </div>
              </Reveal>
            </div>
          </div>
        </section>

        <section className="section faq-section" id="faq">
          <div className="container faq-layout">
            <Reveal>
              <Eyebrow>FAQ</Eyebrow>
              <h2>Questions you might have.</h2>
              <p className="faq-intro">
                A straightforward look at what Tenet is, where we are, and how the private beta
                works.
              </p>
            </Reveal>
            <Reveal>
              <FAQ />
            </Reveal>
          </div>
        </section>

        <section className="section join-section" id="join">
          <div className="join-glow" aria-hidden="true" />
          <div className="container join-layout">
            <Reveal className="join-copy">
              <Eyebrow light>PRIVATE BETA</Eyebrow>
              <h2>
                Help us shape how teams <em>decide together.</em>
              </h2>
              <p>Tell us about your team. We'll reach out personally.</p>
              <div className="join-points">
                <span>
                  <Icon name="check" size={15} /> A direct conversation with the founders
                </span>
                <span>
                  <Icon name="check" size={15} /> Help shape the product and final pricing
                </span>
              </div>
            </Reveal>
            <Reveal>
              <BetaForm />
            </Reveal>
          </div>
          <div className="container founder-links">
            <span>Prefer email?</span>
            <a href="mailto:yashwant.yadav.sde@gmail.com">yashwant.yadav.sde@gmail.com</a>
            <a href="mailto:roshan.jha003@gmail.com">roshan.jha003@gmail.com</a>
          </div>
        </section>
      </main>

      <footer>
        <div className="container footer-top">
          <div>
            <Logo />
            <p>Shared reasoning for teams making decisions together.</p>
          </div>
          <nav aria-label="Footer navigation">
            <a href="#how">How it works</a>
            <a href="#why">Why Tenet</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
            <a href={`mailto:${founderEmails}`}>Contact</a>
            <a href={`mailto:${founderEmails}?subject=${encodeURIComponent("Investor enquiry")}`}>
              Investors
            </a>
          </nav>
        </div>
        <div className="container footer-bottom">
          <span>© 2026 Tenet. Made in India.</span>
          <span>Tenet is in early development; product visuals are illustrative.</span>
        </div>
      </footer>
    </div>
  );
}

export default App;

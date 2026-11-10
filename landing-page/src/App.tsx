import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { content } from "./content";

const colors = ["coral", "sun", "teal", "plum", "ember"] as const;
type Color = (typeof colors)[number];

function useVisible<T extends HTMLElement>(threshold = 0.18) {
  const ref = useRef<T>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold },
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [threshold]);
  return { ref, visible };
}

function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const { ref, visible } = useVisible<HTMLDivElement>();
  return (
    <div ref={ref} className={`reveal ${visible ? "is-visible" : ""} ${className}`}>
      {children}
    </div>
  );
}

export function BlockPiece({
  color = "coral",
  size = "m",
  shape = 0,
  className = "",
}: {
  color?: Color;
  size?: "s" | "m" | "l";
  shape?: number;
  className?: string;
}) {
  const cells = [
    [
      [0, 0],
      [1, 0],
      [1, 1],
      [2, 1],
    ],
    [
      [0, 0],
      [0, 1],
      [1, 1],
      [2, 1],
    ],
    [
      [0, 0],
      [1, 0],
      [0, 1],
      [1, 1],
    ],
    [
      [1, 0],
      [0, 1],
      [1, 1],
      [2, 1],
    ],
    [
      [0, 0],
      [0, 1],
      [0, 2],
      [1, 2],
    ],
  ][shape % 5];
  return (
    <span className={`block-piece block-${size} ${className}`} aria-hidden="true">
      {cells.map(([x, y], i) => (
        <i key={i} className={`bg-${color}`} style={{ gridColumn: x + 1, gridRow: y + 1 }} />
      ))}
    </span>
  );
}

export function FallGuide({ color = "sun" }: { color?: Color }) {
  return (
    <div className="fall-guide" aria-hidden="true">
      <span />
      <BlockPiece color={color} size="s" shape={3} />
    </div>
  );
}

export function Skyline({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`skyline ${compact ? "compact" : ""}`} aria-hidden="true">
      {Array.from({ length: compact ? 8 : 14 }, (_, i) => (
        <BlockPiece
          key={i}
          color={colors[i % colors.length]}
          shape={i % 5}
          size={i % 4 === 0 ? "l" : "m"}
          className="fall-in"
        />
      ))}
    </div>
  );
}

export function Eyebrow({ children, dark = false }: { children: ReactNode; dark?: boolean }) {
  return (
    <div className={`eyebrow ${dark ? "on-dark" : ""}`}>
      <i />
      {children}
    </div>
  );
}

export function SectionHeader({
  chapter,
  title,
  dark = false,
  body,
}: {
  chapter: string;
  title: string;
  dark?: boolean;
  body?: string;
}) {
  return (
    <header className="section-header">
      <Eyebrow dark={dark}>{chapter}</Eyebrow>
      <h2>{title}</h2>
      {body && <p>{body}</p>}
      <div className="corner-blocks" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
    </header>
  );
}

function Logo() {
  return (
    <a href="#top" className="logo" aria-label="Tenet, home">
      <span className="logo-mark" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </span>
      Tenet
    </a>
  );
}

export function Nav() {
  const [open, setOpen] = useState(false);
  const links = [
    ["How it works", "how-it-works"],
    ["Why Tenet", "why-tenet"],
    ["Pricing", "pricing"],
    ["Investors", "investors"],
    ["FAQ", "faq"],
  ];
  return (
    <nav className="nav" aria-label="Main navigation">
      <div className="container nav-inner">
        <Logo />
        <div className="nav-links">
          {links.map(([label, id]) => (
            <a key={id} href={`#${id}`}>
              {label}
            </a>
          ))}
        </div>
        <a href="#beta" className="button primary nav-cta">
          Join the beta
        </a>
        <button
          className="menu-button"
          onClick={() => setOpen(!open)}
          aria-label="Open menu"
          aria-expanded={open}
        >
          <span />
          <span />
        </button>
      </div>
      {open && (
        <div className="mobile-menu">
          {links.map(([label, id]) => (
            <a key={id} href={`#${id}`} onClick={() => setOpen(false)}>
              {label}
            </a>
          ))}
          <a href="#beta" className="button primary" onClick={() => setOpen(false)}>
            Join the beta
          </a>
        </div>
      )}
    </nav>
  );
}

export function DecisionRecordCard({
  compact = false,
  stage = 4,
}: {
  compact?: boolean;
  stage?: number;
}) {
  return (
    <div className={`decision-card ${compact ? "compact-card" : ""}`}>
      <div className="record-top">
        <span>DR-042</span>
        {stage >= 3 && <b className="chip teal">Decided</b>}
      </div>
      <h3>Move onboarding to a self-serve trial</h3>
      {stage === 1 && (
        <div className="memory-item">
          <b>Shared to project memory</b>
          <p>Push a prompt, a response, or both</p>
          <div className="toggle-row">
            <span className="active">Prompt</span>
            <span>Response</span>
            <span>Both</span>
          </div>
        </div>
      )}
      {stage >= 2 && (
        <div className="challenges">
          <div>
            <b>Meera · Pushback</b>
            <p>Trial users may overload support in week one.</p>
            {stage >= 3 && <em>Add in-app guide; review tickets after 14 days.</em>}
          </div>
          <div>
            <b>Arjun · Forecast</b>
            <p>Sales-led deals drop 20%.</p>
            {stage >= 3 && <em>Keep sales-assist for 50+ seat accounts.</em>}
          </div>
        </div>
      )}
      {stage >= 3 && (
        <div className="people">
          <span>
            <small>Owner</small>Priya, Head of Growth
          </span>
          <span>
            <small>Approvers</small>Arjun (CEO), Meera (Eng Lead)
          </span>
        </div>
      )}
      {stage >= 4 && (
        <div className="drift">
          <b>Drift flagged by master agent</b>
          <span>Pricing deck v3 still shows a demo-only flow. This conflicts with DR-042.</span>
        </div>
      )}
    </div>
  );
}

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => document.body.classList.toggle("hero-passed", !e.isIntersecting),
      { threshold: 0 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return (
    <section id="top" ref={ref} className="hero dark-section">
      <div className="container hero-grid">
        <div className="hero-copy">
          <div className="pill">
            <i />
            {content.hero.pill}
          </div>
          <h1>{content.hero.title}</h1>
          <p className="hero-sub">{content.hero.body}</p>
          <div className="hero-actions">
            <a href="#beta" className="button primary">
              Join the beta
            </a>
            <a href="#demo" className="button outline">
              Watch the walkthrough
            </a>
          </div>
          <p className="fineprint">{content.hero.note}</p>
        </div>
        <div className="hero-visual">
          <div className="ui-label">Illustrative UI · MVP in development</div>
          <DecisionRecordCard />
          <div className="fall one">
            <FallGuide color="sun" />
          </div>
          <div className="fall two">
            <FallGuide color="plum" />
          </div>
        </div>
      </div>
      <Skyline />
    </section>
  );
}

function PaperCard({
  children,
  color = "coral",
  dark = false,
  className = "",
}: {
  children: ReactNode;
  color?: Color;
  dark?: boolean;
  className?: string;
}) {
  return (
    <article className={`paper-card top-${color} ${dark ? "card-dark" : ""} ${className}`}>
      {children}
    </article>
  );
}

export function Problem() {
  return (
    <section className="section cream">
      <div className="container">
        <SectionHeader chapter="01 / The problem" title={content.problem.title} />
        <div className="three-grid">
          {content.problem.cards.map((card, i) => (
            <Reveal key={card[0]}>
              <PaperCard color={colors[i + 1]}>
                <span className="card-number">{card[0]}</span>
                <h3>{card[1]}</h3>
                <p>{card[2]}</p>
              </PaperCard>
            </Reveal>
          ))}
        </div>
        <Reveal>
          <blockquote>
            <p>“{content.problem.quote}”</p>
            <cite>{content.problem.attribution}</cite>
          </blockquote>
        </Reveal>
      </div>
    </section>
  );
}

export function InsightBand() {
  return (
    <section className="insight">
      <BlockPiece color="sun" size="l" shape={1} />
      <div className="container">
        <h2>{content.insight.title}</h2>
        <p>{content.insight.body}</p>
      </div>
      <BlockPiece color="plum" size="l" shape={4} />
    </section>
  );
}

export function Solution() {
  return (
    <section className="section cream">
      <div className="container">
        <SectionHeader chapter="02 / The solution" title={content.solution.title} />
        <div className="three-grid">
          {content.solution.cards.map((card, i) => (
            <Reveal key={card[0]}>
              <PaperCard color={i === 2 ? "sun" : colors[i]} dark={i === 2}>
                <span className="icon-square">{i + 1}</span>
                <h3>{card[0]}</h3>
                <p>{card[1]}</p>
              </PaperCard>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

export function HowItWorksStepper() {
  const [step, setStep] = useState(1);
  const { ref, visible } = useVisible<HTMLElement>(0.3);
  const played = useRef(false);
  useEffect(() => {
    if (!visible || played.current) return;
    played.current = true;
    let n = 1;
    const timer = window.setInterval(() => {
      n += 1;
      setStep(n);
      if (n === 4) window.clearInterval(timer);
    }, 650);
    return () => window.clearInterval(timer);
  }, [visible]);
  return (
    <section id="how-it-works" ref={ref} className="section dark-section">
      <div className="container">
        <SectionHeader dark chapter="03 / How it works" title="Inside Docs, Slides and Sheets" />
        <div className="stepper-layout">
          <div className="steps" role="tablist" aria-label="How Tenet works">
            {content.workflow.map((item, i) => (
              <button
                key={item[0]}
                onMouseEnter={() => setStep(i + 1)}
                onClick={() => setStep(i + 1)}
                className={step === i + 1 ? "active" : ""}
                role="tab"
                aria-selected={step === i + 1}
              >
                <span className={`step-block bg-${colors[i]}`}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span>
                  <b>{item[0]}</b>
                  <small>{item[1]}</small>
                </span>
              </button>
            ))}
          </div>
          <div className="step-panel">
            <div className="ui-label">Illustrative UI · MVP in development</div>
            <DecisionRecordCard stage={step} />
            <p className="panel-note">
              Think privately, choose what becomes shared. Nothing enters project memory unless you
              push it.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

export function Demo() {
  return (
    <section id="demo" className="section cream">
      <div className="container">
        <SectionHeader chapter="04 / Demo" title="Tenet in action" />
        <div className="demo-grid">
          <Reveal>
            <div className="video-card">
              <Eyebrow dark>Recorded walkthrough</Eyebrow>
              <button className="play" aria-label="Play Tenet walkthrough">
                <span>▶</span>
              </button>
              <h3>Watch Tenet in action</h3>
              <a target="_blank" href="https://www.loom.com/share/87aac049b9ee48528cec39023c15fd9e">Open Loom video ↗</a>
              <p>Figma prototype + partially working MVP.</p>
            </div>
          </Reveal>
          <Reveal>
            <div>
              <div className="ui-label dark-label">Illustrative UI · MVP in development</div>
              <DecisionRecordCard compact />
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

export function Positioning() {
  return (
    <section id="why-tenet" className="section cream positioning">
      <div className="container">
        <SectionHeader
          chapter="05 / Why Tenet"
          title="Others organize knowledge. Tenet helps teams work through decisions together."
          body="The difference is the unit of collaboration: selectively shared reasoning, not just indexed content."
        />
        <div className="compare-grid">
          <div className="vertical-scroll">
            <h3 className="column-title">Where adjacent tools start</h3>
            {content.positioning.map((x, i) => (
              <PaperCard key={x[0]} color={colors[i + 1]}>
                <h3>{x[0]}</h3>
                <p>{x[1]}</p>
              </PaperCard>
            ))}
          </div>
          <div className="tenet-card">
            <span className="tenet-label">Tenet</span>
            {content.tenetDifference.map((x, i) => (
              <div key={x[0]}>
                <span>{`0${i + 1}`}</span>
                <h3>{x[0]}</h3>
                <p>{x[1]}</p>
              </div>
            ))}
          </div>
        </div>
        <p className="footnote">
          Comparison describes core product emphasis, not absence of features. Tenet's workflow is a
          product vision / MVP in progress.
        </p>
      </div>
    </section>
  );
}

export function Personas() {
  return (
    <section className="section dark-section">
      <div className="container">
        <SectionHeader
          dark
          chapter="06 / Who it's for"
          title="Built for teams that think with AI"
        />
        <div className="three-grid">
          {content.personas.map((p, i) => (
            <Reveal key={p[0]}>
              <PaperCard dark color={colors[i]}>
                <h3>{p[0]}</h3>
                <small>The friction</small>
                <p>{p[1]}</p>
                <small>The outcome</small>
                <p className="outcome">{p[2]}</p>
              </PaperCard>
            </Reveal>
          ))}
        </div>
        <div className="heard-strip">
          <b>What we heard in 10 customer interviews</b>
          <span>
            Teams lose context when AI findings move from person to person. They want a shared
            record of reasoning and decisions.
          </span>
        </div>
      </div>
    </section>
  );
}

export function Pricing() {
  const [currency, setCurrency] = useState<"INR" | "USD">("INR");
  return (
    <section id="pricing" className="section cream">
      <div className="container">
        <SectionHeader
          chapter="07 / Pricing"
          title="One simple plan that grows from one team to the whole company"
        />
        <div className="currency-toggle" role="group" aria-label="Currency">
          {(["INR", "USD"] as const).map((c) => (
            <button
              key={c}
              onClick={() => setCurrency(c)}
              className={currency === c ? "active" : ""}
            >
              {c}
            </button>
          ))}
        </div>
        <div className="pricing-grid">
          <PaperCard color="coral" className="price-card">
            <span>One plan</span>
            <div className="price">
              {currency === "INR" ? "₹999" : "$15"}
              <small>/user/mo</small>
            </div>
            <p>{currency === "INR" ? "India, billed in INR" : "US & global"}</p>
            <ul>
              <li>Every feature in one plan.</li>
              <li>Enterprise controls priced later.</li>
            </ul>
            <a href="#beta" className="button primary">
              Join the beta
            </a>
          </PaperCard>
          <PaperCard dark color="sun" className="expand-card">
            <h3>Land and expand: 1 → many teams</h3>
            <p>Start with one project team, then spread to every team it collaborates with.</p>
            <div className="expand-graphic">
              <i />
              <span>→</span>
              <i />
              <i />
              <i />
              <i />
            </div>
          </PaperCard>
        </div>
        <p className="footnote">
          Indicative pricing for early access. Beta participants get preferential terms.
        </p>
      </div>
    </section>
  );
}

function StatCounter({ value, label }: { value: string; label: string }) {
  return (
    <div className="big-stat">
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}

function BarChart() {
  return (
    <div
      className="bar-chart"
      role="img"
      aria-label="ARR target: year one 50 thousand dollars, year two 120 thousand dollars"
    >
      <div>
        <span style={{ height: "42%" }} />
        <b>Y1</b>
        <small>$50K</small>
      </div>
      <div>
        <span style={{ height: "100%" }} />
        <b>Y2</b>
        <small>$120K</small>
      </div>
    </div>
  );
}

function Donut() {
  return (
    <div className="donut-wrap">
      <div
        className="donut"
        role="img"
        aria-label="Use of funds: Engineering 60%, Go-to-market 25%, Operations 15%"
      >
        <b>$500K</b>
        <span>seed</span>
      </div>
      <ul>
        <li>
          <i className="bg-coral" />
          Engineering 60%
        </li>
        <li>
          <i className="bg-sun" />
          Go-to-market 25%
        </li>
        <li>
          <i className="bg-teal" />
          Operations 15%
        </li>
      </ul>
    </div>
  );
}

export function Investors() {
  return (
    <section id="investors" className="section dark-section investors">
      <div className="container">
        <SectionHeader
          dark
          chapter="For investors"
          title="A decision layer for the AI-native team."
        />
        <InvestorBlock title="Why now">
          <div className="three-grid">
            {content.investor.whyNow.map((x, i) => (
              <PaperCard dark color={colors[i]} key={x[0]}>
                <h3>{x[0]}</h3>
                <p>{x[1]}</p>
              </PaperCard>
            ))}
          </div>
        </InvestorBlock>
        <InvestorBlock title="Traction">
          <div className="traction">
            <div className="stats">
              <StatCounter value="10" label="customer interviews" />
              <StatCounter value="2" label="verbal pilot commitments" />
            </div>
            <div>
              <p>
                Kapiva and SalarySe have verbally committed to pilot Tenet. Verbal intent only;
                working toward signed paid pilots.
              </p>
              <h4>Who we've spoken to</h4>
              <ul className="square-list">
                {content.investor.spokenTo.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
          </div>
        </InvestorBlock>
        <InvestorBlock title="Market">
          <div className="market-layout">
            <div className="market-grid">
              {content.investor.market.map((x, i) => (
                <div className={`market-card top-${colors[i]}`} key={x[0]}>
                  <span>{x[0]}</span>
                  <b>{x[1]}</b>
                  <p>{x[2]}</p>
                </div>
              ))}
            </div>
            <BarChart />
          </div>
          <p className="footnote">
            India-first; $120K goal assumes $12.50 blended ARPU (some global-priced seats). Market
            sizes estimated.
          </p>
        </InvestorBlock>
        <InvestorBlock title="Moat" intro="Every decision makes the next one better informed">
          <div className="three-grid">
            {content.investor.moat.map((x, i) => (
              <PaperCard dark color={colors[i + 1]} key={x[0]}>
                <h3>{x[0]}</h3>
                <p>{x[1]}</p>
              </PaperCard>
            ))}
          </div>
        </InvestorBlock>
        <InvestorBlock title="Business model">
          <div className="model-row">
            <div>
              <b>Per-seat SaaS</b>
              <span>Simple plan, priced per user.</span>
            </div>
            <div>
              <b>~70%</b>
              <span>Est. model-cost margin · India</span>
            </div>
            <div>
              <b>75-80%</b>
              <span>Est. model-cost margin · Global</span>
            </div>
          </div>
          <p className="footnote">
            Token-cost estimates only; excludes other delivery, support and operating costs.
          </p>
        </InvestorBlock>
        <InvestorBlock title="Go-to-market">
          <div className="gtm-grid">
            {content.investor.gtm.map((x, i) => (
              <PaperCard dark color={colors[i]} key={x[0]} className={`stair stair-${i}`}>
                <h3>{x[0]}</h3>
                <p>{x[1]}</p>
              </PaperCard>
            ))}
          </div>
        </InvestorBlock>
        <InvestorBlock title="Team">
          <div className="team-grid">
            {content.investor.team.map((x, i) => (
              <div className="team-member" key={x[1]}>
                <span className={`avatar bg-${colors[i]}`}>{x[0]}</span>
                <div>
                  <h3>{x[1]}</h3>
                  <b>{x[2]}</b>
                  <p>{x[3]}</p>
                </div>
              </div>
            ))}
          </div>
          <p className="key-hires">
            Key hires: founding engineers first; add a small GTM team after paid-pilot conversion.
          </p>
        </InvestorBlock>
        <InvestorBlock title="The ask" intro="Raising $500K seed.">
          <div className="ask-grid">
            <Donut />
            <div>
              <h3>This round unlocks</h3>
              <ol>
                <li>Convert Kapiva and SalarySe to signed paid pilots</li>
                <li>Month 12 target: 10 firms, ~350 seats, ~$50K ARR</li>
                <li>Month 24 target: 20 firms, ~800 seats, ~$120K ARR</li>
              </ol>
              <b className="runway">Runway 24 months*</b>
            </div>
          </div>
          <p className="footnote">
            *Illustrative staged-hiring plan: ~$414K operating spend, ~$86K cash reserve. 60/25/15
            allocation applies to planned spend.
          </p>
        </InvestorBlock>
        <div className="investor-cta">
          <div>
            <h3>Want to go deeper?</h3>
            <p>Speak with the founders or ask for the full deck.</p>
          </div>
          <div>
            <a
              className="button primary"
              href={`mailto:${content.emails.join(",")}?subject=${encodeURIComponent("Tenet seed round: intro")}`}
            >
              Talk to the founders
            </a>
            <a
              className="button outline"
              href={`mailto:${content.emails.join(",")}?subject=${encodeURIComponent("Tenet: request pitch deck")}`}
            >
              Request the deck
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

function InvestorBlock({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: string;
  children: ReactNode;
}) {
  return (
    <Reveal className="investor-block">
      <div className="investor-title">
        <span />
        <h3>{title}</h3>
        {intro && <p>{intro}</p>}
      </div>
      {children}
    </Reveal>
  );
}

export function FAQ() {
  const [open, setOpen] = useState(0);
  return (
    <section id="faq" className="section cream">
      <div className="container narrow">
        <SectionHeader chapter="08 / FAQ" title="Questions you might have." />
        <div className="accordion">
          {content.faq.map((x, i) => (
            <div className="faq-item" key={x[0]}>
              <h3>
                <button
                  onClick={() => setOpen(open === i ? -1 : i)}
                  aria-expanded={open === i}
                  aria-controls={`faq-${i}`}
                >
                  <span>{x[0]}</span>
                  <i>{open === i ? "−" : "+"}</i>
                </button>
              </h3>
              <div id={`faq-${i}`} className={open === i ? "answer open" : "answer"}>
                <p>{x[1]}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

type FormData = {
  name: string;
  email: string;
  company: string;
  role: string;
  size: string;
  ai: string[];
  interest: string;
  pain: string;
  consent: boolean;
};
const initialForm: FormData = {
  name: "",
  email: "",
  company: "",
  role: "",
  size: "",
  ai: [],
  interest: "Joining the beta",
  pain: "",
  consent: false,
};

export function BetaForm() {
  const [form, setForm] = useState(initialForm),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [message, setMessage] = useState(""),
    [copied, setCopied] = useState(false);
  const update = (key: keyof FormData, value: string | boolean | string[]) =>
    setForm({ ...form, [key]: value });
  const buildMessage = () =>
    [
      `Full name: ${form.name}`,
      `Work email: ${form.email}`,
      `Company: ${form.company}`,
      `Role: ${form.role}`,
      `Team size: ${form.size}`,
      `AI tools: ${form.ai.join(", ") || "None selected"}`,
      `Interest: ${form.interest}`,
      `Decision pain: ${form.pain || "Not provided"}`,
      `Consent to email: ${form.consent ? "Yes" : "No"}`,
    ].join("\n");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!form.name.trim()) next.name = "Please enter your full name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) next.email = "Enter a valid work email.";
    if (!form.company.trim()) next.company = "Please enter your company.";
    if (!form.role) next.role = "Choose your role.";
    if (!form.size) next.size = "Choose a team size.";
    if (!form.consent) next.consent = "Please confirm we can email you.";
    setErrors(next);
    if (Object.keys(next).length) return;
    const body = buildMessage();
    setMessage(body);
    const subject = `Tenet beta request: ${form.company} (${form.interest})`;
    window.location.href = `mailto:${content.emails.join(",")}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message);
    } catch {
      const t = document.createElement("textarea");
      t.value = message;
      document.body.appendChild(t);
      t.select();
      document.execCommand("copy");
      t.remove();
    }
    setCopied(true);
  };
  return (
    <section id="beta" className="section dark-section beta">
      <div className="container">
        <SectionHeader
          dark
          chapter="09 / Join the beta"
          title="Be one of the first teams to try Tenet."
        />
        <div className="beta-grid">
          <div className="beta-copy">
            <p>
              We're onboarding a small group of design partners. Tell us how your team works with AI
              today.
            </p>
            {content.emails.map((x) => (
              <a href={`mailto:${x}`} key={x}>
                {x}
              </a>
            ))}
            <BlockPiece color="sun" size="l" shape={0} />
          </div>
          <form onSubmit={submit} noValidate className="beta-form">
            {message ? (
              <div className="success" aria-live="polite">
                <span>Message ready</span>
                <h3>Opening your email app…</h3>
                <p>If nothing opened, copy your details below and email us.</p>
                <pre>{message}</pre>
                <button type="button" className="button primary" onClick={copy}>
                  {copied ? "Copied" : "Copy message"}
                </button>
                {content.emails.map((x) => (
                  <a href={`mailto:${x}`} key={x}>
                    {x}
                  </a>
                ))}
              </div>
            ) : (
              <>
                <div className="form-row">
                  <Field label="Full name" error={errors.name}>
                    <input
                      value={form.name}
                      onChange={(e) => update("name", e.target.value)}
                      required
                      autoComplete="name"
                    />
                  </Field>
                  <Field label="Work email" error={errors.email}>
                    <input
                      type="email"
                      value={form.email}
                      onChange={(e) => update("email", e.target.value)}
                      required
                      autoComplete="email"
                    />
                  </Field>
                </div>
                <Field label="Company" error={errors.company}>
                  <input
                    value={form.company}
                    onChange={(e) => update("company", e.target.value)}
                    required
                    autoComplete="organization"
                  />
                </Field>
                <div className="form-row">
                  <Field label="Your role" error={errors.role}>
                    <select value={form.role} onChange={(e) => update("role", e.target.value)}>
                      <option value="">Select</option>
                      {[
                        "Founder",
                        "Business head",
                        "Engineering lead",
                        "Engineer",
                        "Product",
                        "Investor",
                        "Other",
                      ].map((x) => (
                        <option key={x}>{x}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Team size" error={errors.size}>
                    <select value={form.size} onChange={(e) => update("size", e.target.value)}>
                      <option value="">Select</option>
                      {["1-10", "11-50", "51-200", "201-1000", "1000+"].map((x) => (
                        <option key={x}>{x}</option>
                      ))}
                    </select>
                  </Field>
                </div>
                <fieldset>
                  <legend>How are you using AI at work today?</legend>
                  <div className="chips">
                    {["ChatGPT", "Claude", "Gemini", "Copilot", "Notion AI", "Other"].map((x) => (
                      <label key={x}>
                        <input
                          type="checkbox"
                          checked={form.ai.includes(x)}
                          onChange={() =>
                            update(
                              "ai",
                              form.ai.includes(x)
                                ? form.ai.filter((a) => a !== x)
                                : [...form.ai, x],
                            )
                          }
                        />
                        <span>{x}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <fieldset>
                  <legend>I'm interested in…</legend>
                  <div className="radio-grid">
                    {[
                      "Joining the beta",
                      "Running a paid pilot",
                      "Investing",
                      "Just exploring",
                    ].map((x) => (
                      <label key={x}>
                        <input
                          type="radio"
                          name="interest"
                          checked={form.interest === x}
                          onChange={() => update("interest", x)}
                        />
                        <span>{x}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <Field label="What's the biggest pain in your team's decisions? (optional)">
                  <textarea
                    rows={4}
                    value={form.pain}
                    onChange={(e) => update("pain", e.target.value)}
                  />
                </Field>
                <label className="consent">
                  <input
                    type="checkbox"
                    checked={form.consent}
                    onChange={(e) => update("consent", e.target.checked)}
                  />
                  <span>I'm happy for the Tenet founders to email me about this.</span>
                </label>
                {errors.consent && <span className="error">{errors.consent}</span>}
                <button className="button primary submit" type="submit">
                  Open email request
                </button>
                <p className="form-note" aria-live="polite">
                  This opens your email app with a pre-filled message. Nothing is sent until you
                  press send.
                </p>
              </>
            )}
          </form>
        </div>
      </div>
    </section>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {error && <em className="error">{error}</em>}
    </label>
  );
}

export function Footer() {
  return (
    <footer className="footer dark-section">
      <div className="container footer-grid">
        <div>
          <Logo />
          <p>Work converges when decisions are on record.</p>
          <small>Illustrative UI shown. Product in development.</small>
        </div>
        <div>
          {content.emails.map((x) => (
            <a href={`mailto:${x}`} key={x}>
              {x}
            </a>
          ))}
        </div>
        <div>
          {[
            ["How it works", "how-it-works"],
            ["Pricing", "pricing"],
            ["Investors", "investors"],
            ["FAQ", "faq"],
          ].map((x) => (
            <a href={`#${x[1]}`} key={x[1]}>
              {x[0]}
            </a>
          ))}
        </div>
        <span className="copyright">© 2026 Tenet.</span>
      </div>
      <Skyline compact />
    </footer>
  );
}

export default function App() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <Problem />
        <InsightBand />
        <Solution />
        <HowItWorksStepper />
        <Demo />
        <Positioning />
        <Personas />
        <Pricing />
        <Investors />
        <FAQ />
        <BetaForm />
      </main>
      <Footer />
      <a href="#beta" className="mobile-sticky">
        Join the beta
      </a>
    </>
  );
}

"use client";

import Link from "next/link";
import { ArrowUp, Search, Sparkles } from "lucide-react";
import { useState } from "react";

import { Markdown } from "@/components/Markdown";
import { api } from "@/lib/api";
import { KIND_LABEL } from "@/lib/format";
import type { Answer, Source } from "@/lib/types";

function sourceHref(handle: string, s: Source): string | undefined {
  if (s.kind === "decision") return `/spaces/${handle}/decisions/${s.id}`;
  if (s.kind === "finding") return `/spaces/${handle}/findings/${s.id}`;
  if (s.kind === "pr") return `/spaces/${handle}/prs/${s.id.split("#")[1]}`;
  return s.url;
}

/** Ask any agent: the space's, a decision's or a PR's. Answers come with their sources. */
export function AskBox({ handle, agent, placeholder, suggestions = [] }: {
  handle: string;
  agent?: string;
  placeholder?: string;
  suggestions?: string[];
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask(q: string) {
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await api<Answer>(`/spaces/${handle}/ask`, { method: "POST", json: { question: q, agent } }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      {answer ? (
        <section className="panel">
          <div className="panel-head">
            <div className="row"><Sparkles size={18} color="var(--accent)" /><span className="medium">{answer.question}</span></div>
            <span className="pill accent">{answer.agent} · v{answer.version}</span>
          </div>
          <Markdown text={answer.answer} />
          {answer.sources.length ? (
            <div className="row wrap">
              {answer.sources.map((s, i) => {
                const href = sourceHref(handle, s);
                const label = `${KIND_LABEL[s.kind] ?? s.kind} · ${s.kind === "decision" ? s.id : s.title ?? s.id}`;
                if (!href) return <span key={i} className="chip">{label}</span>;
                return href.startsWith("/")
                  ? <Link key={i} className="chip" href={href}>{label}</Link>
                  : <a key={i} className="chip" href={href} target="_blank" rel="noreferrer">{label}</a>;
              })}
            </div>
          ) : null}
        </section>
      ) : null}
      {error ? <div className="error">{error}</div> : null}
      <form className="composer" onSubmit={(e) => { e.preventDefault(); void ask(question); }}>
        <Search size={18} color="var(--muted)" style={{ marginBottom: 10 }} />
        <textarea
          aria-label="Ask"
          rows={1}
          value={question}
          placeholder={placeholder ?? `Ask ${agent ?? `@${handle}`}…`}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(question); } }}
        />
        <button className="icon-btn" type="submit" disabled={busy} aria-label="Ask">
          <ArrowUp size={18} className={busy ? "spin" : ""} />
        </button>
      </form>
      {suggestions.length && !answer ? (
        <div className="row wrap">
          {suggestions.map((s) => (
            <button key={s} className="chip" type="button" onClick={() => { setQuestion(s); void ask(s); }}>{s}</button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

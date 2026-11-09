"use client";

import Link from "next/link";
import { useState } from "react";

import { EvidenceChips, Person, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, when } from "@/lib/format";
import type { Finding } from "@/lib/types";

const STANCES = [
  { key: "agree", label: "Agree" },
  { key: "concern", label: "Concern" },
  { key: "question", label: "Question" },
];

/** A finding: shared on purpose, visible to everyone, not agreed. Reply, or promote it. */
export function FindingCard({ finding, handle, canPromote, onChange, expanded = false }: {
  finding: Finding;
  handle: string;
  canPromote: boolean;
  onChange: (f: Finding) => void;
  expanded?: boolean;
}) {
  const [stance, setStance] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);

  async function send() {
    if (!stance) return;
    setBusy(true);
    setError(null);
    try {
      onChange(await api<Finding>(`/findings/${finding.id}/replies`, { method: "POST", json: { stance, text } }));
      setStance(null);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function promote() {
    setBusy(true);
    setError(null);
    try {
      const result = await api<Finding & { notes: string[] }>(`/findings/${finding.id}/promote`, { method: "POST" });
      setNotes(result.notes ?? []);
      onChange(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <Person user={finding.author} sub={`${when(finding.created_at)} · shared finding`} />
        <div className="row">
          <span className="pill">Not agreed</span>
          {finding.status === "promoted" ? <StatusPill status="promoted" label="Promoted to proposal" /> : null}
        </div>
      </div>
      {expanded ? <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{finding.text}</p> : (
        <Link href={`/spaces/${handle}/findings/${finding.id}`} style={{ whiteSpace: "pre-wrap" }}>{finding.text}</Link>
      )}
      <EvidenceChips evidence={finding.evidence} />
      {finding.mentions.length ? (
        <div className="row wrap small muted">
          About: {finding.mentions.map((m) => (
            <Link key={m} className="chip" href={m.startsWith("pr-") ? `/spaces/${handle}/prs/${m.slice(3)}` : `/spaces/${handle}/decisions/${m}`}>
              {m.startsWith("pr-") ? `PR #${m.slice(3)}` : m}
            </Link>
          ))}
        </div>
      ) : null}
      <div className="row small muted">
        {finding.counts.agree} agree · {finding.counts.concern} concern · {finding.counts.question} question
      </div>
      {finding.replies.length ? (
        <div className="stack">
          {finding.replies.map((r) => (
            <div key={r.id} className="row top">
              <StatusPill status={r.stance} />
              <span><strong>{r.author?.name}</strong>{r.text ? ` — ${r.text}` : ""} <span className="small muted">{ago(r.created_at)}</span></span>
            </div>
          ))}
        </div>
      ) : null}
      <div className="divider" />
      <div className="row wrap">
        {STANCES.map((s) => (
          <button key={s.key} type="button" className={`chip ${stance === s.key ? "selected" : ""}`} onClick={() => setStance(stance === s.key ? null : s.key)}>{s.label}</button>
        ))}
        {finding.status === "open" && canPromote ? (
          <button className="btn small" style={{ marginLeft: "auto" }} disabled={busy} onClick={promote}>Promote to proposal</button>
        ) : finding.proposal_id ? (
          <Link className="link" style={{ marginLeft: "auto" }} href={`/spaces/${handle}/proposals/${finding.proposal_id}`}>View proposal →</Link>
        ) : null}
      </div>
      {stance ? (
        <div className="row top">
          <input className="input" value={text} onChange={(e) => setText(e.target.value)}
            placeholder={stance === "agree" ? "Optional note" : `Your ${stance}, in a line`} />
          <button className="btn primary" disabled={busy || (stance !== "agree" && !text.trim())} onClick={send}>Reply</button>
        </div>
      ) : null}
      {notes.map((n) => <span key={n} className="small muted">({n})</span>)}
      {error ? <div className="error">{error}</div> : null}
    </section>
  );
}

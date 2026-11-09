"use client";

import { useParams } from "next/navigation";
import { GitMerge } from "lucide-react";
import { useState } from "react";

import { useShell } from "@/components/Shell";
import { useSpace } from "@/components/SpaceFrame";
import { EvidenceChips, ErrorNote, Loading, Panel, Person, StatusPill } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { when } from "@/lib/format";
import type { Proposal, StateVersion } from "@/lib/types";

/** 04 · Review a proposal in order. The agreed state doesn't change until every stage approves. */
export default function ProposalPage() {
  const { id } = useParams<{ id: string }>();
  const { space, reload: reloadSpace } = useSpace();
  const { me, refresh } = useShell();
  const { data: p, error, setData } = useApi<Proposal>(`/proposals/${id}`);
  const { data: base } = useApi<StateVersion>(p ? `/spaces/${space.handle}/state?version=${p.base_version}` : null);
  const [note, setNote] = useState("");
  const [pushback, setPushback] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!p) return <><ErrorNote error={error} /><Loading /></>;

  const waiting = p.stages.find((s) => s.state === "waiting");
  const myTurn = Boolean(waiting && me && waiting.owner?.id === me.id);
  const openPushbacks = p.pushbacks.filter((b) => !b.outcome);
  const decision = p.decision_key ? base?.snapshot.decisions[p.decision_key] : undefined;
  const parents = (p.content.parents ?? []).map((k) => base?.snapshot.decisions[k]).filter(Boolean);

  async function act(path: string, json: unknown) {
    setBusy(true);
    setActionError(null);
    try {
      setData(await api<Proposal>(`/proposals/${p!.id}/${path}`, { method: "POST", json }));
      setNote("");
      setPushback("");
      await Promise.all([refresh(), reloadSpace()]);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const statusLabel = p.status === "pending" ? (myTurn ? "Awaiting your review" : `Waiting on ${waiting?.owner?.name}`) : undefined;

  return (
    <>
      <div className="heading">
        <span className="eyebrow">{p.decision_key ?? p.type} · {p.status === "pending" ? "in review" : p.status}</span>
        <div className="title-row">
          <h1 className="h1">{p.title}</h1>
          <StatusPill status={p.status === "pending" ? (myTurn ? "pending" : "waiting") : p.status} label={statusLabel} />
        </div>
        <p className="lede">Proposed by {p.proposer?.name} · {when(p.created_at)} · Shared with @{space.handle}</p>
      </div>

      <div className="cols">
        <div className="col-main">
          <Panel title="What the team is deciding" meta={p.status === "approved" ? `Agreed in v${p.committed_version}` : "Not yet agreed"}>
            <p className="big">{p.content.statement ?? p.content.text}</p>
            {p.content.constraints?.length ? (
              <div className="stack" style={{ gap: 6 }}>
                <span className="tiny-label">Constraints</span>
                {p.content.constraints.map((c) => <div key={c} className="row top"><span className="muted">•</span><span>{c}</span></div>)}
              </div>
            ) : null}
            <div className="compare">
              <div>
                <span className="tiny-label">Current · version {p.base_version}</span>
                <span>{decision ? `${decision.key} rev ${decision.revision}: ${decision.statement}` : parents.length
                  ? parents.map((d) => `${d!.key}: ${d!.statement}`).join(" ")
                  : "Nothing agreed on this yet."}</span>
              </div>
              <div className="proposed">
                <span className="tiny-label">Proposed change</span>
                <span>{p.content.statement ?? p.content.text}</span>
              </div>
            </div>
            {p.content.parents?.length ? <span className="small muted">Builds on {p.content.parents.join(", ")}</span> : null}
          </Panel>

          {p.content.conflicts?.length ? (
            <Panel title="Conflicts with agreed decisions" className="accent">
              {p.content.conflicts.map((c, i) => (
                <div key={i} className="note danger"><span><strong>{c.decision}</strong> · {c.constraint}<br />{c.explanation}</span></div>
              ))}
            </Panel>
          ) : null}

          <Panel title="Source evidence" meta={`${p.evidence.length} attached`}>
            {p.content.tagged_text ? (
              <div className="stack" style={{ gap: 6 }}>
                <span className="tiny-label">Shared from a private session</span>
                <div className="quote">{p.content.tagged_text}</div>
              </div>
            ) : null}
            {p.evidence.length ? <EvidenceChips evidence={p.evidence} handle={space.handle} /> : <p className="muted small">No sources attached.</p>}
          </Panel>

          {p.pushbacks.length ? (
            <Panel title="Pushback" meta={`${openPushbacks.length} open`}>
              {p.pushbacks.map((b) => (
                <div key={b.id} className="stack" style={{ gap: 4 }}>
                  <div className="row between">
                    <Person user={b.raised_by} sub={when(b.created_at)} />
                    <StatusPill status={b.outcome ?? "open"} label={b.outcome ?? "open"} />
                  </div>
                  <div className="quote">{b.reason}</div>
                  {b.note ? <span className="small muted">{b.resolved_by?.name}: {b.note}</span> : null}
                </div>
              ))}
            </Panel>
          ) : null}

          <div className="note">
            <GitMerge size={18} />
            <span>The agreed state stays version {p.base_version} until every reviewer approves. Approving a decision never merges a pull request.</span>
          </div>
        </div>

        <div className="col-side">
          <Panel title="Review in order" meta={waiting ? `Stage ${waiting.number} of ${p.stages.length}` : ""}>
            {p.stages.map((s, i) => (
              <div key={s.number} className="stack">
                {i > 0 ? <div className="divider" /> : null}
                <div className="row between">
                  <span className="tiny-label" style={{ color: s.state === "waiting" ? "var(--accent)" : undefined }}>
                    {String(s.number).padStart(2, "0")} · {s.name}
                  </span>
                  <StatusPill status={s.state === "not_started" ? "" : s.state}
                    label={s.state === "waiting" ? (s.owner?.id === me?.id ? "Your turn" : "Waiting") : s.state === "not_started" ? "Not started" : undefined} />
                </div>
                <Person user={s.owner} sub={s.at ? `${s.state === "rejected" ? "Requested changes" : "Approved"} ${when(s.at)}` : undefined} />
                {s.note ? <span className="small muted">“{s.note}”</span> : null}
              </div>
            ))}
          </Panel>

          {p.status === "pending" && myTurn ? (
            <Panel title="Your review">
              <textarea className="textarea" value={note} onChange={(e) => setNote(e.target.value)}
                placeholder={openPushbacks.length ? "One line on why you're approving over the open pushback" : "Optional note for the record"} />
              <ErrorNote error={actionError} />
              <button className="btn primary block" disabled={busy} onClick={() => act("approve", { note })}>
                {waiting?.number === p.stages.length ? `Approve & update to v${space.head_version + 1}` : "Approve this stage"}
              </button>
              <button className="btn block" disabled={busy || !note.trim()} onClick={() => act("reject", { reason: note })}>
                Request changes
              </button>
              <span className="hint">Approve: {waiting?.number === p.stages.length ? "publish the new version and notify everyone" : "pass it to the next stage"}. Request changes: return it to {p.proposer?.name}; the state stays v{space.head_version}.</span>
            </Panel>
          ) : null}

          {p.status === "pending" ? (
            <Panel title="Push back">
              <textarea className="textarea" value={pushback} onChange={(e) => setPushback(e.target.value)} placeholder="What should the reviewers weigh before approving?" />
              <button className="btn block" disabled={busy || !pushback.trim()} onClick={() => act("pushbacks", { reason: pushback })}>Raise pushback</button>
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}

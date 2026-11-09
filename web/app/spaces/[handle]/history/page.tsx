"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, GitBranch, History, Info } from "lucide-react";
import { Suspense, useEffect, useMemo, useState } from "react";

import { useSpace } from "@/components/SpaceFrame";
import { ErrorNote, Loading, Person, StatusPill } from "@/components/ui";
import { useApi } from "@/lib/api";
import { day, when } from "@/lib/format";
import type { DecisionEntry, EventView, Rewind, RewindStep } from "@/lib/types";

type Entry =
  | { kind: "version"; at: string; step: RewindStep; agreed: Record<string, DecisionEntry> }
  | { kind: "event"; at: string; event: EventView; agreedVersion: number; agreed: Record<string, DecisionEntry> };

const EVENT_TITLE: Record<string, (e: EventView) => string> = {
  "space.created": () => "Space created",
  "item.linked": (e) => `Linked ${String(e.payload.title ?? "a source")}`,
  "item.synced": (e) => `Synced ${String(e.payload.title ?? "a Doc")}`,
  "member.added": (e) => `${String(e.payload.name)} joined`,
  "session.tagged": (e) => `${e.actor?.name ?? "Someone"} shared from a private session`,
  "finding.shared": (e) => `${e.actor?.name ?? "Someone"} shared a finding`,
  "finding.replied": (e) => `${e.actor?.name ?? "Someone"} replied: ${String(e.payload.stance)}`,
  "finding.promoted": () => "Finding promoted to a proposal",
  "proposal.created": (e) => `Proposed ${String(e.payload.decision ?? e.payload.title ?? "")}`.trim(),
  "proposal.approved": (e) => `${String(e.payload.stage_name ?? "Stage")} approved`,
  "proposal.rejected": () => "Changes requested",
  "proposal.blocked": (e) => `Held: conflicts with ${(e.payload.conflicts_with as string[] | undefined)?.join(", ")}`,
  "pushback.raised": (e) => `${e.actor?.name ?? "Someone"} pushed back`,
  "pushback.resolved": (e) => `Pushback ${String(e.payload.outcome)}`,
  "pr.linked": (e) => `${e.target.id} linked to ${String(e.payload.decision)}`,
  "pr.checked": (e) => `${e.target.id} checked: ${String(e.payload.result)}`,
};

function eventText(e: EventView): string {
  const p = e.payload;
  return String(p.text ?? p.note ?? p.reason ?? p.title ?? p.summary ?? "");
}

function HistoryView() {
  const { space } = useSpace();
  const params = useSearchParams();
  const decision = params.get("decision") ?? "";
  const [filter, setFilter] = useState(decision);
  const { data, error } = useApi<Rewind>(`/spaces/${space.handle}/rewind?from=1${filter ? `&decision=${filter}` : ""}`);

  const entries = useMemo<Entry[]>(() => {
    if (!data) return [];
    const out: Entry[] = [];
    let before: Record<string, DecisionEntry> = {};
    let beforeVersion = 0;
    for (const step of data.steps) {
      for (const event of step.events) {
        out.push({ kind: "event", at: event.at, event, agreedVersion: beforeVersion, agreed: before });
      }
      if (!filter || step.changes.length) out.push({ kind: "version", at: step.at, step, agreed: step.agreed });
      before = step.agreed;
      beforeVersion = step.version;
    }
    if (!filter) return out;
    // A decision's story includes its proposals' events (reviews, pushbacks), which name the
    // proposal rather than the decision, and any finding or PR that mentions it.
    const proposals = new Set(
      out.flatMap((e) => (e.kind === "event" && e.event.type === "proposal.created" && e.event.payload.decision === filter ? [e.event.target.id] : [])),
    );
    return out.filter((e) => e.kind === "version"
      || (e.event.target.kind === "proposal" && proposals.has(e.event.target.id))
      || JSON.stringify(e.event.payload).includes(filter));
  }, [data, filter]);

  const [index, setIndex] = useState(0);
  useEffect(() => {
    setIndex(Math.max(entries.length - 1, 0));
  }, [entries.length]);

  if (!data) return <><ErrorNote error={error} /><Loading /></>;
  const selected = entries[index];
  const decisions = Object.keys(data.steps.at(-1)?.agreed ?? {});

  return (
    <>
      <div className="heading">
        <span className="eyebrow">Read-only history</span>
        <div className="title-row">
          <h1 className="h1">Decision history</h1>
          <Link className="btn" href={`/spaces/${space.handle}`}>Back to current state</Link>
        </div>
        <p className="lede">See what was agreed at any moment, and why it changed. Today&apos;s agreement stays v{data.head_version}.</p>
      </div>

      <div className="panel tight" style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <div className="row">
          <GitBranch size={18} color="var(--accent)" />
          <select className="select" style={{ width: 320 }} value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">Everything in @{space.handle}</option>
            {decisions.map((k) => <option key={k} value={k}>{k} · {data.steps.at(-1)!.agreed[k].title}</option>)}
          </select>
        </div>
        <div className="row small muted">
          {entries.length ? `${day(entries[0].at)}–${day(entries.at(-1)!.at)} · ${entries.length} events` : ""}
          <StatusPill status="active" label={`Latest agreement · v${data.head_version}`} />
        </div>
      </div>

      <div className="cols">
        <div className="timeline" style={{ width: 556, flexShrink: 0 }}>
          {entries.map((entry, i) => {
            const isVersion = entry.kind === "version";
            const title = isVersion ? entry.step.summary : (EVENT_TITLE[entry.event.type]?.(entry.event) ?? entry.event.type);
            const sub = isVersion
              ? entry.step.changes.map((c) => `${c.key} · ${c.decision?.statement ?? c.status?.text ?? c.change}`).join(" ")
              : eventText(entry.event);
            return (
              <div key={i} className="step">
                <div className="track">
                  <div className={`dot ${i === index ? "on" : isVersion && entry.step.version === data.head_version ? "final" : ""}`} />
                  {i < entries.length - 1 ? <div className="line" /> : null}
                </div>
                <button className={`event ${i === index ? "selected" : ""}`} onClick={() => setIndex(i)}>
                  <div className="row between">
                    <span className="small muted">{when(entry.at)}</span>
                    {isVersion ? <StatusPill status="active" label={`Agreed · v${entry.step.version}`} />
                      : entry.event.type.startsWith("proposal.created") ? <StatusPill status="pending" label="Proposal" />
                        : entry.event.type.startsWith("finding") ? <span className="pill">Finding</span> : null}
                  </div>
                  <span style={{ fontWeight: 500, fontSize: 14 }}>{title}</span>
                  {sub ? <span className="small muted">{sub.length > 160 ? `${sub.slice(0, 160)}…` : sub}</span> : null}
                </button>
              </div>
            );
          })}
        </div>

        {selected ? (
          <div className="col-main">
            <section className="panel">
              <div className="row between">
                <span className="row" style={{ color: "var(--accent)", fontSize: 11, fontWeight: 600 }}>
                  <History size={16} />READ-ONLY REWIND · STEP {index + 1} OF {entries.length}
                </span>
                <div className="row">
                  <button className="icon-btn" aria-label="Earlier" disabled={index === 0} onClick={() => setIndex(index - 1)}><ChevronLeft size={16} /></button>
                  <button className="icon-btn" aria-label="Later" disabled={index === entries.length - 1} onClick={() => setIndex(index + 1)}><ChevronRight size={16} /></button>
                </div>
              </div>
              <div className="row small muted">
                <span className="pill">Selected moment</span>
                {when(selected.at)} · shared agreement v{selected.kind === "version" ? selected.step.version : selected.agreedVersion}
              </div>
              {selected.kind === "version" ? (
                <>
                  <p className="big" style={{ fontSize: 22 }}>{selected.step.summary}</p>
                  {selected.step.committed_by ? <Person user={selected.step.committed_by} sub="Committed this version" /> : null}
                </>
              ) : (
                <>
                  <p className="big" style={{ fontSize: 22 }}>{EVENT_TITLE[selected.event.type]?.(selected.event) ?? selected.event.type}</p>
                  {eventText(selected.event) ? <div className="quote">{eventText(selected.event)}</div> : null}
                  <span className="small muted">The agreement had not changed at this point.</span>
                  {selected.event.actor ? <Person user={selected.event.actor} sub={selected.event.type.replace(".", " ")} /> : null}
                </>
              )}
              <div className="divider" />
              <div className="stack" style={{ background: "var(--bg)", borderRadius: 6, padding: 16 }}>
                <div className="row between">
                  <span className="tiny-label">Agreed at this moment</span>
                  <span className="pill">Version {selected.kind === "version" ? selected.step.version : selected.agreedVersion}</span>
                </div>
                {Object.values(selected.agreed).length === 0 ? <span className="muted">Nothing agreed yet.</span> :
                  Object.values(selected.agreed).map((d) => (
                    <div key={d.key} className="stack" style={{ gap: 2 }}>
                      <span style={{ fontWeight: 500 }}>{d.key} · {d.title}</span>
                      <span className="small muted">{d.constraints.join(" · ")}</span>
                    </div>
                  ))}
              </div>
            </section>
            <div className="note"><Info size={16} /><span>Rewind is a read-only view. The team&apos;s current agreement remains version {data.head_version}.</span></div>
          </div>
        ) : null}
      </div>
    </>
  );
}

export default function HistoryPage() {
  return <Suspense fallback={<Loading />}><HistoryView /></Suspense>;
}

"use client";

import Link from "next/link";

import { useSpace } from "@/components/SpaceFrame";
import { Panel, Person, StatusPill } from "@/components/ui";
import { useApi } from "@/lib/api";
import { when } from "@/lib/format";
import type { Proposal } from "@/lib/types";

export default function Reviews() {
  const { space } = useSpace();
  const { data } = useApi<Proposal[]>(`/spaces/${space.handle}/proposals`);
  const open = data?.filter((p) => p.status === "pending" || p.status === "blocked") ?? [];
  const closed = data?.filter((p) => !open.includes(p)) ?? [];

  const row = (p: Proposal) => {
    const waiting = p.stages.find((s) => s.state === "waiting");
    return (
      <Link key={p.id} className="list-row" href={`/spaces/${space.handle}/proposals/${p.id}`}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="person-name">{p.decision_key ? `${p.decision_key} · ` : ""}{p.title}</div>
          <div className="person-sub">
            {p.type} · proposed by {p.proposer?.name} · {when(p.created_at)}
            {waiting ? ` · waiting on ${waiting.owner?.name} (${waiting.name})` : ""}
          </div>
        </div>
        <StatusPill status={p.status} />
      </Link>
    );
  };

  return (
    <div className="cols">
      <div className="col-main">
        <Panel title="Open reviews" meta={`${open.length} open`}>
          {open.length ? <div>{open.map(row)}</div> : <p className="muted">Nothing waiting on review.</p>}
        </Panel>
        <Panel title="Decided" meta={`${closed.length}`}>
          {closed.length ? <div>{closed.map(row)}</div> : <p className="muted">No reviewed proposals yet.</p>}
        </Panel>
      </div>
      <div className="col-side">
        <Panel title="Review in order">
          {space.stages.map((s) => {
            const area = space.areas.find((a) => a.key === s.area);
            return <Person key={s.number} user={area?.owner} sub={`Stage ${s.number} · ${s.name}`} />;
          })}
          <p className="muted small" style={{ margin: 0 }}>The agreed state changes only after every stage approves.</p>
        </Panel>
      </div>
    </div>
  );
}

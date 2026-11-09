"use client";

import Link from "next/link";

import { Shell } from "@/components/Shell";
import { ErrorNote, Loading, Panel, StatusPill } from "@/components/ui";
import { useApi } from "@/lib/api";
import { when } from "@/lib/format";
import type { Proposal } from "@/lib/types";

export default function Approvals() {
  const { data, error } = useApi<Proposal[]>("/approvals");
  return (
    <Shell crumbs={[{ label: "Approvals" }]}>
      <div className="heading">
        <h1 className="h1">Waiting on you</h1>
        <p className="lede">Proposals whose current review stage is yours.</p>
      </div>
      <ErrorNote error={error} />
      {!data ? <Loading /> : (
        <Panel title="Your turn" meta={`${data.length}`}>
          {data.length === 0 ? <p className="muted">Nothing is waiting on you.</p> : (
            <div>
              {data.map((p) => {
                const stage = p.stages.find((s) => s.state === "waiting");
                return (
                  <Link key={p.id} className="list-row" href={`/spaces/${p.space?.handle}/proposals/${p.id}`}>
                    <div style={{ flex: 1 }}>
                      <div className="person-name">{p.decision_key ? `${p.decision_key} · ` : ""}{p.title}</div>
                      <div className="person-sub">@{p.space?.handle} · proposed by {p.proposer?.name} · {when(p.created_at)}</div>
                    </div>
                    <StatusPill status="waiting" label={`Stage ${stage?.number} · ${stage?.name}`} />
                  </Link>
                );
              })}
            </div>
          )}
        </Panel>
      )}
    </Shell>
  );
}

"use client";

import Link from "next/link";
import { Bot } from "lucide-react";
import { useState } from "react";

import { AskBox } from "@/components/AskBox";
import { useSpace } from "@/components/SpaceFrame";
import { ErrorNote, Loading, Panel, StatusPill } from "@/components/ui";
import { useApi } from "@/lib/api";
import type { Agents } from "@/lib/types";

/** Every agent you can ask: the space's, one per decision (covering its PRs), one per PR. */
export default function AgentsPage() {
  const { space } = useSpace();
  const { data, error } = useApi<Agents>(`/spaces/${space.handle}/agents`);
  const [agent, setAgent] = useState<string | undefined>(undefined);

  if (!data) return <><ErrorNote error={error} /><Loading /></>;
  const selected = agent ?? data.space.agent;

  const pick = (a: string) => (
    <button className={`chip ${selected === a ? "selected" : ""}`} onClick={() => setAgent(a)}><Bot size={13} />{a}</button>
  );

  return (
    <div className="cols">
      <div className="col-main">
        <Panel title={<span className="row"><Bot size={18} color="var(--accent)" />Ask {selected}</span>}>
          <p className="muted" style={{ margin: 0 }}>
            {selected === data.space.agent ? "The space's agent answers from the agreed state, its sources and shared findings."
              : selected.includes("/pr-") ? "A PR's agent answers from that PR's record: the decisions it implements, its checks, and how those decisions came about."
                : "A decision's agent answers from every revision of the decision and every PR that implements it."}
          </p>
          <AskBox key={selected} handle={space.handle} agent={selected === data.space.agent ? undefined : selected}
            suggestions={selected.includes("/pr-") ? ["Why was this PR made?", "What did the check find?", "What changed since it was opened?"]
              : ["Where are we?", "Why was this decided?", "What changed?"]} />
        </Panel>
      </div>
      <div className="col-side">
        <Panel title="Space">{pick(data.space.agent)}</Panel>
        <Panel title="Decisions" meta={`${data.decisions.length}`}>
          {data.decisions.length === 0 ? <p className="muted">None yet.</p> : data.decisions.map((d) => (
            <div key={d.key} className="stack" style={{ gap: 6 }}>
              <div className="row between">{pick(d.agent)}<StatusPill status={d.status} /></div>
              <span className="small muted">{d.title}{d.prs.length ? ` · PRs ${d.prs.map((n) => `#${n}`).join(", ")}` : ""}</span>
            </div>
          ))}
        </Panel>
        <Panel title="Pull requests" meta={`${data.prs.length}`}>
          {data.prs.length === 0 ? <p className="muted">No PRs checked yet.</p> : data.prs.map((p) => (
            <div key={p.number} className="stack" style={{ gap: 6 }}>
              <div className="row between">{pick(p.agent)}<StatusPill status={p.result} /></div>
              <Link className="small muted" href={`/spaces/${space.handle}/prs/${p.number}`}>
                {p.title || `PR #${p.number}`}{p.implements.length ? ` · implements ${p.implements.join(", ")}` : ""}
              </Link>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

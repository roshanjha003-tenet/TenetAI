"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AskBox } from "@/components/AskBox";
import { useSpace } from "@/components/SpaceFrame";
import { EvidenceChips, ErrorNote, Loading, Panel, Person, StatusPill } from "@/components/ui";
import { useApi } from "@/lib/api";
import { when } from "@/lib/format";
import type { DecisionDetail, Finding } from "@/lib/types";

export default function DecisionPage() {
  const { key } = useParams<{ key: string }>();
  const { space } = useSpace();
  const { data: d, error } = useApi<DecisionDetail>(`/spaces/${space.handle}/decisions/${key}`);
  const { data: findings } = useApi<Finding[]>(`/spaces/${space.handle}/findings?mention=${key}`);
  if (!d) return <><ErrorNote error={error} /><Loading /></>;
  const current = d.revisions[d.revisions.length - 1];
  const agent = `@${space.handle}/${d.key}`;

  return (
    <>
      <div className="heading">
        <span className="eyebrow">{d.key} · revision {d.current_revision} · {d.area.name}</span>
        <div className="title-row"><h1 className="h1">{d.title}</h1><StatusPill status={d.status} /></div>
        <p className="lede">Owned by {d.area.owner.name} · agent <code>{agent}</code></p>
      </div>
      <div className="cols">
        <div className="col-main">
          <Panel title="Agreed" meta={`Revision ${current.revision} · v${current.state_version}`}>
            <p className="big">{current.statement}</p>
            <div className="stack" style={{ gap: 6 }}>
              <span className="tiny-label">Constraints</span>
              {current.constraints.map((c) => <div key={c} className="row top"><span className="muted">•</span><span>{c}</span></div>)}
            </div>
            {current.parents.length ? (
              <span className="small muted">Builds on {current.parents.map((p, i) => (
                <span key={p}>{i > 0 ? ", " : ""}<Link className="link" href={`/spaces/${space.handle}/decisions/${p}`}>{p}</Link></span>
              ))}</span>
            ) : null}
            <EvidenceChips evidence={current.evidence} />
          </Panel>
          <Panel title={`Ask ${agent}`}>
            <AskBox handle={space.handle} agent={agent} suggestions={["Why was this decided?", "Which PRs follow it, and which don't?", "What changed between revisions?"]} />
          </Panel>
          {d.revisions.length > 1 ? (
            <Panel title="Earlier revisions">
              {d.revisions.slice(0, -1).reverse().map((r) => (
                <div key={r.revision} className="stack" style={{ gap: 4 }}>
                  <span className="tiny-label">Revision {r.revision} · v{r.state_version} · {when(r.created_at)}</span>
                  <span>{r.statement}</span>
                  <span className="small muted">{r.constraints.join(" · ")}</span>
                </div>
              ))}
            </Panel>
          ) : null}
        </div>
        <div className="col-side">
          <Panel title="Decision provenance">
            <Person user={current.proposer} sub={`Proposed · ${when(current.created_at)}`} />
            {current.approvals.map((a) => (
              <Person key={a.user_id + a.stage} user={{ id: a.user_id, name: a.name, email: "", title: null, github_login: null }} sub={`${a.stage} · approved ${when(a.at)}`} />
            ))}
            <Link className="link" href={`/spaces/${space.handle}/history?decision=${d.key}`}>See how we got here →</Link>
          </Panel>
          <Panel title="Pull requests" meta={`${d.prs.length}`}>
            {d.prs.length === 0 ? <p className="muted">No PRs implement this yet.</p> : d.prs.map((p) => (
              <Link key={`${p.repo}#${p.number}`} className="source" href={`/spaces/${space.handle}/prs/${p.number}`}>
                <div className="source-mark">PR</div>
                <div className="source-body">
                  <div className="source-title">#{p.number} · {p.repo}</div>
                  <div className="source-sub">Linked revision {p.pinned_revision}{p.pinned_revision < d.current_revision ? " · decision changed since" : ""}</div>
                </div>
              </Link>
            ))}
          </Panel>
          {findings?.length ? (
            <Panel title="Findings about it" meta={`${findings.length}`}>
              {findings.slice(0, 4).map((f) => (
                <Link key={f.id} href={`/spaces/${space.handle}/findings/${f.id}`} className="small">
                  <strong>{f.author?.name}:</strong> {f.text.slice(0, 120)}{f.text.length > 120 ? "…" : ""}
                </Link>
              ))}
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}

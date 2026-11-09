"use client";

import Link from "next/link";
import { CircleCheck, GitMerge, LockKeyhole, Sparkles } from "lucide-react";

import { AskBox } from "@/components/AskBox";
import { useSpace } from "@/components/SpaceFrame";
import { Panel, Person, SourceRow, StatusPill } from "@/components/ui";
import { useApi } from "@/lib/api";
import { ago, KIND_LABEL, plural, when } from "@/lib/format";
import type { Finding, PRCheck, Proposal, Rewind, StateVersion } from "@/lib/types";

/** Overview: the one agreed view, what's waiting, what changed, and ask the space. */
export default function Overview() {
  const { space } = useSpace();
  const h = space.handle;
  const { data: state } = useApi<StateVersion>(`/spaces/${h}/state`);
  const { data: pending } = useApi<Proposal[]>(`/spaces/${h}/proposals?status=pending`);
  const { data: prs } = useApi<PRCheck[]>(`/spaces/${h}/prs`);
  const { data: findings } = useApi<Finding[]>(`/spaces/${h}/findings`);
  const head = space.head_version;
  const { data: rewind } = useApi<Rewind>(head > 1 ? `/spaces/${h}/rewind?from=${head}&to=${head}` : null);

  const decisions = Object.values(state?.snapshot.decisions ?? {}).sort((a, b) => b.key.localeCompare(a.key));
  const latest = rewind?.steps[0];
  const recent = latest && Date.now() - new Date(latest.at).getTime() < 3 * 86400_000;
  const approvers = latest?.changes.flatMap((c) => c.decision?.approved_by.map((a) => a.name) ?? []) ?? [];

  return (
    <>
      <div className="heading">
        <div className="title-row">
          <h1 className="h1">{space.name}</h1>
          <Link className="btn" href="/sessions"><Sparkles size={16} color="var(--accent)" />Open private AI workspace</Link>
        </div>
        <p className="lede">{space.goal || "One agreed view of the work."}</p>
      </div>

      {recent && latest ? (
        <div className="note success">
          <CircleCheck size={18} />
          <span>
            <strong>{latest.summary}</strong>
            {approvers.length ? ` — approved by ${approvers.join(" and ")}` : ""}. Shared state updated to version {latest.version}.
          </span>
          <span className="small" style={{ marginLeft: "auto" }}>{ago(latest.at)}</span>
        </div>
      ) : null}

      <div className="cols">
        <div className="col-main">
          <Panel
            title={<span className="row" style={{ color: "var(--accent)", fontSize: 12 }}><GitMerge size={18} />CURRENT AGREED STATE</span>}
            actions={<StatusPill status="active" label={`Version ${head}`} />}
          >
            {decisions.length === 0 ? <p className="muted">Nothing agreed yet. Share a proposal from your private workspace.</p> : (
              <div className="stack">
                {decisions.map((d) => (
                  <Link key={d.key} href={`/spaces/${h}/decisions/${d.key}`} className="stack" style={{ gap: 4 }}>
                    <div className="row between">
                      <span className="tiny-label">{d.key} · revision {d.revision} · {d.area.replace(/-/g, " ")}</span>
                      <StatusPill status={d.status} />
                    </div>
                    <span className="medium">{d.title}</span>
                    <span className="muted">{d.statement}</span>
                  </Link>
                ))}
              </div>
            )}
            {state?.snapshot.status ? (
              <div className="note"><span><strong>Status · {state.snapshot.status.by}:</strong> {state.snapshot.status.text}</span></div>
            ) : null}
            <div className="divider" />
            <div className="row between small muted">
              <span>{state ? `v${state.version} · ${state.summary} · ${when(state.created_at)}` : ""}</span>
              <span style={{ color: "var(--accent)" }}>Shared with all {space.members.length} members</span>
            </div>
          </Panel>

          {latest && latest.changes.length ? (
            <Panel title="What changed" meta={`Version ${latest.parent_version} → Version ${latest.version}`}>
              {latest.changes.map((c) => (
                <div key={c.key} className="stack" style={{ gap: 8 }}>
                  {c.previous ? <div className="row top muted"><span>−</span><span>{c.previous.statement}</span></div> : null}
                  <div className="note success"><span>+</span><span><strong>{c.key}</strong> · {c.decision?.statement ?? c.status?.text}</span></div>
                </div>
              ))}
              <Link className="link" href={`/spaces/${h}/history`}>See how we got here →</Link>
            </Panel>
          ) : null}

          <Panel title="Work in flight" meta={prs ? plural(prs.length, "pull request") : ""}>
            {!prs?.length ? <p className="muted">No pull requests checked yet. PRs that say <code>Implements: D-…</code> show up here.</p> : (
              <div>
                {prs.map((p) => (
                  <Link key={p.id} className="list-row" href={`/spaces/${h}/prs/${p.pr_number}`}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="person-name">{p.pr_title || `PR #${p.pr_number}`} · #{p.pr_number}</div>
                      <div className="person-sub">{p.pr_author} · {p.title}</div>
                    </div>
                    <StatusPill status={p.result} />
                  </Link>
                ))}
              </div>
            )}
          </Panel>

          <AskBox handle={h} placeholder="Ask about this space…" suggestions={["Where are we?", "Why did we decide this?", "What changed recently?"]} />
        </div>

        <div className="col-side">
          {pending && pending.length ? pending.map((p) => {
            const stage = p.stages.find((s) => s.state === "waiting");
            return (
              <Panel key={p.id} title={`Waiting on ${stage?.owner?.name.split(" ")[0] ?? "review"}`} meta={plural(pending.length, "review")}>
                <StatusPill status="pending" label={p.type === "status" ? "Pending status" : "Pending decision"} />
                <p className="medium">{p.decision_key ? `${p.decision_key} · ` : ""}{p.title}</p>
                <p className="muted" style={{ margin: 0 }}>
                  {p.stages.filter((s) => s.state === "approved").map((s) => `${s.owner?.name} approved the ${s.name}.`).join(" ")}{" "}
                  {stage ? `${stage.owner?.name}'s ${stage.name} review is next.` : ""}
                </p>
                {stage ? <Person user={stage.owner} sub={`Stage ${stage.number} of ${p.stages.length} · ${stage.name}`} /> : null}
                <Link className="btn primary" href={`/spaces/${h}/proposals/${p.id}`}>View pending proposal →</Link>
              </Panel>
            );
          }) : (
            <Panel title="Up next" meta="No pending approvals">
              <p className="muted" style={{ margin: 0 }}>Nothing is waiting on review. Share a finding or a proposal from your private workspace.</p>
            </Panel>
          )}

          <Panel title="Recent findings" meta={findings ? plural(findings.length, "finding") : ""}>
            {!findings?.length ? <p className="muted">Nobody has shared a finding yet.</p> : findings.slice(0, 3).map((f) => (
              <Link key={f.id} href={`/spaces/${h}/findings/${f.id}`} className="stack" style={{ gap: 4 }}>
                <span className="small muted">{f.author?.name} · {ago(f.created_at)} · {f.counts.agree} agree · {f.counts.concern} concern</span>
                <span>{f.text.length > 140 ? `${f.text.slice(0, 140)}…` : f.text}</span>
              </Link>
            ))}
            <Link className="link" href={`/spaces/${h}/findings`}>All findings →</Link>
          </Panel>

          <Panel title="Linked sources" meta={`${space.items.length} connected`}>
            {space.items.slice(0, 5).map((i) => (
              <SourceRow key={i.id} kind={i.kind} title={i.title} sub={`${KIND_LABEL[i.kind] ?? i.kind}${i.excerpt ? ` · ${i.excerpt.slice(0, 40)}…` : ""}`} href={i.url} />
            ))}
            <Link className="link" href={`/spaces/${h}/sources`}>Manage sources →</Link>
          </Panel>

          <div className="note">
            <LockKeyhole size={18} />
            <span>Your private thinking stays private. Tag <strong>@{h}</strong> in a private session to share a paragraph, and only that paragraph, with this space.</span>
          </div>
        </div>
      </div>
    </>
  );
}

"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ExternalLink } from "lucide-react";

import { AskBox } from "@/components/AskBox";
import { Markdown } from "@/components/Markdown";
import { useSpace } from "@/components/SpaceFrame";
import { ErrorNote, Loading, Panel, StatusPill } from "@/components/ui";
import { useApi } from "@/lib/api";
import { when } from "@/lib/format";
import type { PRDetail } from "@/lib/types";

const CONCLUSION: Record<string, string> = { success: "Passed", failure: "Failed", neutral: "Neutral" };

/** One PR: the decisions it implements, every check result, and its own agent. */
export default function PRPage() {
  const { number } = useParams<{ number: string }>();
  const { space } = useSpace();
  const { data, error } = useApi<PRDetail>(`/spaces/${space.handle}/prs/${number}`);
  if (!data) return <><ErrorNote error={error} /><Loading /></>;
  const { latest } = data;
  const agent = `@${space.handle}/pr-${number}`;

  return (
    <>
      <div className="heading">
        <span className="eyebrow">{latest.repo} · pull request · agent {agent}</span>
        <div className="title-row">
          <h1 className="h1">{latest.pr_title || `PR #${number}`} <span className="muted">#{number}</span></h1>
          {latest.pr_url ? <a className="btn" href={latest.pr_url} target="_blank" rel="noreferrer"><ExternalLink size={14} />Open on GitHub</a> : null}
        </div>
        <p className="lede">{latest.pr_author} · head {latest.head_sha.slice(0, 7)} · checked {when(latest.created_at)}</p>
      </div>

      <div className="cols">
        <div className="col-main">
          <Panel
            title={<span style={{ color: latest.conclusion === "failure" ? "var(--danger)" : undefined }}>{latest.title}</span>}
            actions={<StatusPill status={latest.result} label={`${CONCLUSION[latest.conclusion] ?? latest.conclusion} · ${latest.result.replace(/_/g, " ")}`} />}
          >
            <Markdown text={latest.summary} />
          </Panel>

          {latest.findings.length ? (
            <Panel title="Where it drifts">
              {latest.findings.map((f, i) => (
                <div key={i} className="stack" style={{ gap: 6 }}>
                  <div className="row between">
                    <Link className="link" href={`/spaces/${space.handle}/decisions/${f.decision}`}>{f.decision} rev {f.revision} · {f.decision_title}</Link>
                    <code>{f.file}:{f.start_line}{f.end_line !== f.start_line ? `-${f.end_line}` : ""}</code>
                  </div>
                  <div className="note danger"><span><strong>{f.constraint}</strong><br />{f.explanation}</span></div>
                  <span className="small muted">Approved by {f.approvers.map((a) => `${a.name} (${a.stage})`).join(" and ")}</span>
                </div>
              ))}
            </Panel>
          ) : null}

          <Panel title={`Ask ${agent}`}>
            <AskBox handle={space.handle} agent={agent}
              suggestions={["Where are we?", "Why did this check fail or pass?", "What changed since this PR started?"]} />
          </Panel>
        </div>

        <div className="col-side">
          <Panel title="Implements" meta={`${data.links.length}`}>
            {data.links.length === 0 ? <p className="muted">No linked decisions. Add <code>Implements: D-…</code> to the PR description.</p> : data.links.map((l) => (
              <div key={l.decision} className="stack" style={{ gap: 4 }}>
                <div className="row between">
                  <Link className="link" href={`/spaces/${space.handle}/decisions/${l.decision}`}>{l.decision}</Link>
                  <StatusPill status={l.pinned_revision < l.current_revision ? "stale" : l.status}
                    label={l.pinned_revision < l.current_revision ? `rev ${l.pinned_revision} → ${l.current_revision}` : `rev ${l.pinned_revision}`} />
                </div>
                <span className="small muted">{l.title}</span>
                <span className="small muted">Decision agent: <code>@{space.handle}/{l.decision}</code></span>
              </div>
            ))}
          </Panel>
          <Panel title="Check history" meta={`${data.history.length}`}>
            {data.history.map((c) => (
              <div key={c.id} className="row between">
                <span className="small">{when(c.created_at)} · {c.head_sha.slice(0, 7)}</span>
                <StatusPill status={c.result} />
              </div>
            ))}
          </Panel>
        </div>
      </div>
    </>
  );
}

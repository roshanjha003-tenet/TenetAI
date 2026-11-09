"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LockKeyhole } from "lucide-react";
import { useState } from "react";

import { Shell, useShell } from "@/components/Shell";
import { ErrorNote, Loading, Panel } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { when } from "@/lib/format";
import type { Session, SessionSummary } from "@/lib/types";

function NewSession() {
  const { me } = useShell();
  const router = useRouter();
  const [space, setSpace] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const target = space || me?.spaces[0]?.handle || "";

  async function start() {
    try {
      const s = await api<Session>(`/spaces/${target}/sessions`, { method: "POST", json: { title: title || "New session" } });
      router.push(`/sessions/${s.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <Panel title="Start a private session">
      <div className="field">
        <label className="label" htmlFor="space">Space</label>
        <select id="space" className="select" value={target} onChange={(e) => setSpace(e.target.value)}>
          {me?.spaces.map((s) => <option key={s.id} value={s.handle}>@{s.handle}</option>)}
        </select>
        <span className="hint">Your AI works from this space&apos;s agreed state. Nothing you write is shared unless you tag the space.</span>
      </div>
      <div className="field">
        <label className="label" htmlFor="title">What are you working on?</label>
        <input id="title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Retry strategy" />
      </div>
      <ErrorNote error={error} />
      <button className="btn primary block" disabled={!target} onClick={start}>Start session</button>
    </Panel>
  );
}

export default function Sessions() {
  const { data, error } = useApi<SessionSummary[]>("/sessions");
  return (
    <Shell crumbs={[{ label: "Your private workspace" }]} context={<><LockKeyhole size={15} /><span>Only you</span></>}>
      <div className="heading">
        <h1 className="h1">Think privately. Share intentionally.</h1>
        <p className="lede">Sessions are visible only to you; the database enforces it.</p>
      </div>
      <div className="cols">
        <div className="col-main">
          <ErrorNote error={error} />
          <Panel title="Your sessions" meta={data ? `${data.length}` : ""}>
            {!data ? <Loading /> : data.length === 0 ? <p className="muted">No sessions yet.</p> : (
              <div>
                {data.map((s) => (
                  <Link key={s.id} className="list-row" href={`/sessions/${s.id}`}>
                    <div style={{ flex: 1 }}>
                      <div className="person-name">{s.title}</div>
                      <div className="person-sub">@{s.space} · {when(s.created_at)}</div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Panel>
        </div>
        <div className="col-side"><NewSession /></div>
      </div>
    </Shell>
  );
}

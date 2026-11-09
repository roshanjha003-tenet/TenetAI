"use client";

import { useState } from "react";

import { FindingCard } from "@/components/FindingCard";
import { useShell } from "@/components/Shell";
import { useSpace } from "@/components/SpaceFrame";
import { ErrorNote, Loading, Panel } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import type { Finding } from "@/lib/types";

/** Findings: what people found, shared without waiting on approval, open for everyone's response. */
export default function Findings() {
  const { space } = useSpace();
  const { me } = useShell();
  const { data, error, setData } = useApi<Finding[]>(`/spaces/${space.handle}/findings`);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const ownsArea = Boolean(me && space.areas.some((a) => a.owner.id === me.id));

  async function share() {
    setBusy(true);
    setShareError(null);
    try {
      const created = await api<Finding>(`/spaces/${space.handle}/findings`, { method: "POST", json: { text } });
      setData([created, ...(data ?? [])]);
      setText("");
    } catch (e) {
      setShareError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const replace = (f: Finding) => setData((data ?? []).map((x) => (x.id === f.id ? f : x)));

  return (
    <div className="cols">
      <div className="col-main">
        <ErrorNote error={error} />
        {!data ? <Loading /> : data.length === 0 ? <p className="muted">No findings yet.</p> : data.map((f) => (
          <FindingCard key={f.id} finding={f} handle={space.handle} onChange={replace}
            canPromote={Boolean(me && (f.author?.id === me.id || ownsArea))} />
        ))}
      </div>
      <div className="col-side">
        <Panel title="Share a finding">
          <textarea className="textarea" value={text} onChange={(e) => setText(e.target.value)}
            placeholder="What did you find? Mention a decision (D-…) or a PR agent so the right people see it." />
          <ErrorNote error={shareError} />
          <button className="btn primary block" disabled={busy || !text.trim()} onClick={share}>Share with @{space.handle}</button>
          <span className="hint">Everyone in the space sees it now. It never changes the agreed state unless it's promoted and approved. To share from your own AI's work, tag @{space.handle} in a private session.</span>
        </Panel>
      </div>
    </div>
  );
}

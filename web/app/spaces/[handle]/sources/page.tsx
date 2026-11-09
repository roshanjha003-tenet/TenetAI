"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { useSpace } from "@/components/SpaceFrame";
import { ErrorNote, Panel, SourceRow } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { KIND_LABEL } from "@/lib/format";
import type { GoogleStatus } from "@/lib/types";

/** Sources: the context the space's agents draw evidence from. Google Docs stay in sync. */
export default function Sources() {
  const { space, reload } = useSpace();
  const { data: google } = useApi<GoogleStatus>("/connect/google");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [synced, setSynced] = useState<string | null>(null);

  const isDoc = /docs\.google\.com\/document|drive\.google\.com/.test(url);
  const docs = space.items.filter((i) => i.kind === "gdoc");

  async function add() {
    setBusy(true);
    setError(null);
    try {
      if (isDoc) await api(`/spaces/${space.handle}/docs`, { method: "POST", json: { url, title } });
      else await api(`/spaces/${space.handle}/items`, { method: "POST", json: { url, title, excerpt } });
      setUrl("");
      setTitle("");
      setExcerpt("");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function syncAll() {
    setBusy(true);
    try {
      const results = await api<{ status: string }[]>(`/spaces/${space.handle}/sync`, { method: "POST" });
      const updated = results.filter((r) => r.status === "updated").length;
      setSynced(`${updated} updated · ${results.length - updated} unchanged or unavailable`);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cols">
      <div className="col-main">
        <Panel title="Linked sources" meta={`${space.items.length} connected`}
          actions={docs.length && google?.configured ? (
            <button className="btn small" disabled={busy} onClick={syncAll}><RefreshCw size={14} />Sync Google Docs</button>
          ) : null}>
          {synced ? <span className="small muted">{synced}</span> : null}
          {space.items.length === 0 ? <p className="muted">No sources yet.</p> : space.items.map((i) => (
            <div key={i.id} className="stack" style={{ gap: 6 }}>
              <SourceRow kind={i.kind} title={i.title} sub={KIND_LABEL[i.kind] ?? i.kind} href={i.url} />
              {i.excerpt ? <div className="quote small">{i.excerpt.length > 280 ? `${i.excerpt.slice(0, 280)}…` : i.excerpt}</div> : null}
            </div>
          ))}
        </Panel>
      </div>
      <div className="col-side">
        <Panel title="Add a source">
          <div className="field">
            <label className="label" htmlFor="url">Link</label>
            <input id="url" className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Jira, GitHub, Notion, Slack or Google Doc" />
          </div>
          <div className="field">
            <label className="label" htmlFor="title">Title</label>
            <input id="title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={isDoc ? "Defaults to the Doc's title" : "What is it?"} />
          </div>
          {isDoc ? (
            google?.connected ? <span className="hint">Tenet reads this Doc with your Google permissions and keeps it in sync.</span>
              : <span className="hint">Connect Google Drive first, in <Link className="link" href="/settings/connections">Connections</Link>.</span>
          ) : (
            <div className="field">
              <label className="label" htmlFor="excerpt">Excerpt</label>
              <textarea id="excerpt" className="textarea" value={excerpt} onChange={(e) => setExcerpt(e.target.value)} placeholder="The part the team should work from" />
              <span className="hint">Fetching Jira, Notion and Slack content is coming; paste what matters for now.</span>
            </div>
          )}
          <ErrorNote error={error} />
          <button className="btn primary block" disabled={busy || !url.trim() || (isDoc && !google?.connected)} onClick={add}>Add source</button>
        </Panel>
      </div>
    </div>
  );
}

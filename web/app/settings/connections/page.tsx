"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Shell } from "@/components/Shell";
import { ErrorNote, Loading, Panel, SourceRow } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import type { GoogleStatus } from "@/lib/types";

function Connections() {
  const params = useSearchParams();
  const { data, error, reload } = useApi<GoogleStatus>("/connect/google");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const result = params.get("google");

  async function connect() {
    setBusy(true);
    try {
      const { url } = await api<{ url: string }>("/connect/google/start", { method: "POST" });
      window.location.href = url;
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    await api("/connect/google", { method: "DELETE" }).catch(() => {});
    await reload();
    setBusy(false);
  }

  return (
    <>
      <div className="heading">
        <h1 className="h1">Connections</h1>
        <p className="lede">Tenet reads connected tools with your own permissions, and only when you ask it to.</p>
      </div>
      {result === "connected" ? <div className="note success">Google Drive is connected.</div> : null}
      {result === "error" ? <div className="note danger">Google didn&apos;t connect: {params.get("reason") || "try again"}.</div> : null}
      <ErrorNote error={error ?? actionError} />
      {!data ? <Loading /> : (
        <Panel title="Google Drive" meta={data.connected ? `Connected as ${data.email}` : "Not connected"}>
          <SourceRow kind="gdoc" title="Google Docs" sub="Attach Docs to private sessions; share them by tagging a space; shared Docs stay in sync." />
          {!data.configured ? (
            <p className="muted" style={{ margin: 0 }}>This server has no Google OAuth client yet. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the backend&apos;s .env.</p>
          ) : data.connected ? (
            <button className="btn" disabled={busy} onClick={disconnect}>Disconnect</button>
          ) : (
            <button className="btn primary" disabled={busy} onClick={connect}>Connect Google Drive</button>
          )}
          <span className="hint">Read-only access. Docs you attach stay private until you share them.</span>
        </Panel>
      )}
    </>
  );
}

export default function ConnectionsPage() {
  return (
    <Shell crumbs={[{ label: "Connections" }]}>
      <Suspense fallback={<Loading />}><Connections /></Suspense>
    </Shell>
  );
}

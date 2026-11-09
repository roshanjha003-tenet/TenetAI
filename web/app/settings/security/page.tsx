"use client";

import { useRouter } from "next/navigation";

import { Shell } from "@/components/Shell";
import { ErrorNote, Loading, Panel, Pill } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { ago, when } from "@/lib/format";
import type { AuthSessionRow } from "@/lib/types";

function device(userAgent: string): string {
  const browser = /Edg\//.test(userAgent) ? "Edge" : /Chrome\//.test(userAgent) ? "Chrome"
    : /Firefox\//.test(userAgent) ? "Firefox" : /Safari\//.test(userAgent) ? "Safari" : "Browser";
  const os = /Windows/.test(userAgent) ? "Windows" : /Mac OS/.test(userAgent) ? "macOS"
    : /Android/.test(userAgent) ? "Android" : /iPhone|iPad/.test(userAgent) ? "iOS"
    : /Linux/.test(userAgent) ? "Linux" : "";
  return os ? `${browser} on ${os}` : browser;
}

export default function SecurityPage() {
  const router = useRouter();
  const { data, error, reload } = useApi<AuthSessionRow[]>("/auth/sessions");

  async function revoke(id: string) {
    await api(`/auth/sessions/${id}`, { method: "DELETE" }).catch(() => {});
    await reload();
  }

  async function signOutEverywhere() {
    await api("/auth/logout-all", { method: "POST" }).catch(() => {});
    router.push("/login");
  }

  return (
    <Shell crumbs={[{ label: "Sign-in & sessions" }]}>
      <div className="heading">
        <h1 className="h1">Sign-in &amp; sessions</h1>
        <p className="lede">Where you&apos;re signed in. A session ends after 12 hours unused, or 7 days at most.</p>
      </div>
      <ErrorNote error={error} />
      {!data ? <Loading /> : (
        <Panel
          title="Active sessions"
          meta={`${data.length} signed in`}
          actions={<button className="btn small danger" onClick={signOutEverywhere}>Sign out everywhere</button>}
        >
          <div className="stack">
            {data.map((s) => (
              <div key={s.id} className="row between">
                <div>
                  <div className="row">
                    <strong>{device(s.user_agent)}</strong>
                    {s.current ? <Pill tone="success">This browser</Pill> : null}
                    <Pill>{s.provider}</Pill>
                  </div>
                  <div className="hint">
                    Signed in {when(s.created_at)} · last active {ago(s.last_seen_at)}{s.ip ? ` · ${s.ip}` : ""}
                  </div>
                </div>
                {!s.current ? <button className="btn small" onClick={() => revoke(s.id)}>Sign out</button> : null}
              </div>
            ))}
          </div>
        </Panel>
      )}
    </Shell>
  );
}

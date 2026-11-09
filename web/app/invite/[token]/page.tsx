"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorNote, Loading } from "@/components/ui";
import { api, signInUrl, useApi } from "@/lib/api";
import type { AuthConfig, InviteInfo } from "@/lib/types";

/** An invite link: who invited you, to what, and how to accept (sign in as the invited email). */
export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { data: invite, error } = useApi<InviteInfo>(`/invites/${token}`);
  const { data: config } = useApi<AuthConfig>("/auth/config");
  const [acceptError, setAcceptError] = useState<string | null>(null);

  async function acceptSignedIn() {
    try {
      await api(`/invites/${token}/accept`, { method: "POST" });
      router.push("/");
    } catch (e) {
      setAcceptError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="center">
      <div className="panel" style={{ width: 420 }}>
        <div className="logo" style={{ marginBottom: 0 }}>
          <div className="logo-mark">T</div>
          <div className="logo-name">Tenet AI</div>
        </div>
        <ErrorNote error={error ?? acceptError} />
        {!invite ? (error ? null : <Loading />) : (
          <div className="stack">
            <p className="lede" style={{ margin: 0 }}>
              {invite.invited_by} invited <strong>{invite.email}</strong> to {invite.org}
              {invite.space ? <> and {invite.space} as a {invite.role}</> : null}.
            </p>
            {invite.accepted ? <div className="note">This invite was already used. Sign in instead.</div> : null}
            {invite.expired ? <div className="note warn">This invite has expired. Ask {invite.invited_by} for a new one.</div> : null}
            {!invite.accepted && !invite.expired ? (
              <>
                {config?.providers.map((p) => (
                  <a key={p.id} className="btn primary block" href={signInUrl(p.id, "/", token)}>
                    Accept with {p.label}
                  </a>
                ))}
                <span className="hint">Sign in as {invite.email}. Tenet checks the address with your identity provider.</span>
                <button className="btn block" onClick={acceptSignedIn}>I&apos;m already signed in as {invite.email}</button>
              </>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

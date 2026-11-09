"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Loading } from "@/components/ui";
import { api, signInUrl, useApi } from "@/lib/api";
import type { AuthConfig, Me } from "@/lib/types";

function safeNext(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const { data: config, error: configError } = useApi<AuthConfig>("/auth/config");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(params.get("error"));

  async function devSignIn(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/dev", { method: "POST", json: { token: token.trim() } });
      const me = await api<Me>("/me");
      router.push(next !== "/" ? next : me.spaces.length ? `/spaces/${me.spaces[0].handle}` : "/spaces/new");
    } catch {
      setError("That token didn't work.");
    }
  }

  return (
    <div className="panel" style={{ width: 400 }}>
      <div className="logo" style={{ marginBottom: 0 }}>
        <div className="logo-mark">T</div>
        <div className="logo-name">Tenet AI</div>
      </div>
      <p className="lede">Shared context. Private thinking.</p>
      {error ? <div className="note danger">{error}</div> : null}
      {configError ? <div className="note danger">Can&apos;t reach Tenet: {configError}</div> : null}
      {!config ? <Loading /> : (
        <div className="stack">
          {config.providers.map((p) => (
            <a key={p.id} className="btn primary block" href={signInUrl(p.id, next)}>
              Continue with {p.label}
            </a>
          ))}
          {config.providers.length === 0 && !config.dev ? (
            <p className="muted">Sign-in isn&apos;t set up on this server yet.</p>
          ) : null}
          {config.providers.length > 0 ? (
            <span className="hint">Use your work account. Your company&apos;s sign-in rules (like MFA) apply.</span>
          ) : null}
          {config.dev ? (
            <form className="stack" onSubmit={devSignIn}>
              <div className="field">
                <label className="label" htmlFor="token">Development token</label>
                <input id="token" className="input" value={token} onChange={(e) => setToken(e.target.value)} />
                <span className="hint">Local development only: seeded users sign in with dev-yashwant, dev-maya, …</span>
              </div>
              <button className="btn block" type="submit" disabled={!token.trim()}>Sign in with token</button>
            </form>
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function Login() {
  return (
    <div className="center">
      <Suspense fallback={<Loading />}><LoginForm /></Suspense>
    </div>
  );
}

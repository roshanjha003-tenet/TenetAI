"use client";

import { useState } from "react";

import { Shell, useShell } from "@/components/Shell";
import { ErrorNote, Loading, Panel, Person as PersonRow, Pill } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { when } from "@/lib/format";
import type { AuditRow, DomainRow, InviteRow, Person, Usage } from "@/lib/types";

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function People() {
  const { me } = useShell();
  const { data, error, reload } = useApi<Person[]>("/admin/people");
  const [actionError, setActionError] = useState<string | null>(null);

  async function update(id: string, change: Partial<Pick<Person, "active" | "is_org_admin">>) {
    try {
      await api(`/admin/people/${id}`, { method: "PATCH", json: change });
      await reload();
    } catch (e) {
      setActionError(errorText(e));
    }
  }

  return (
    <Panel title="People" meta={data ? `${data.length} in your org` : undefined}>
      <ErrorNote error={error ?? actionError} />
      {!data ? <Loading /> : (
        <div className="stack">
          {data.map((p) => (
            <div key={p.id} className="row between">
              <PersonRow
                user={p}
                sub={
                  <span className="row" style={{ gap: 6 }}>
                    {p.email}
                    {p.is_org_admin ? <Pill tone="accent">Admin</Pill> : null}
                    {p.external ? <Pill tone="warn">External</Pill> : null}
                    {!p.active ? <Pill tone="danger">Turned off</Pill> : null}
                  </span>
                }
              />
              {p.id !== me?.id ? (
                <div className="row">
                  {!p.external ? (
                    <button className="btn small" onClick={() => update(p.id, { is_org_admin: !p.is_org_admin })}>
                      {p.is_org_admin ? "Remove admin" : "Make admin"}
                    </button>
                  ) : null}
                  <button className={`btn small ${p.active ? "danger" : ""}`} onClick={() => update(p.id, { active: !p.active })}>
                    {p.active ? "Turn off" : "Turn on"}
                  </button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function Invites() {
  const { me } = useShell();
  const { data, error, reload } = useApi<InviteRow[]>("/admin/invites");
  const [email, setEmail] = useState("");
  const [space, setSpace] = useState("");
  const [role, setRole] = useState("member");
  const [link, setLink] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setActionError(null);
    try {
      const created = await api<InviteRow>("/admin/invites", {
        method: "POST",
        json: { email: email.trim(), space: space || null, role },
      });
      setLink(created.link ?? null);
      setEmail("");
      await reload();
    } catch (err) {
      setActionError(errorText(err));
    }
  }

  return (
    <Panel title="Invites" meta="Email isn't sent yet: copy the link and send it yourself">
      <form className="row wrap" onSubmit={invite}>
        <input className="input" style={{ flex: "2 1 220px" }} placeholder="name@company.com" value={email}
          onChange={(e) => setEmail(e.target.value)} />
        <select className="select" style={{ flex: "1 1 160px" }} value={space} onChange={(e) => setSpace(e.target.value)}>
          <option value="">Org only (no space)</option>
          {me?.spaces.map((s) => <option key={s.id} value={`@${s.handle}`}>@{s.handle}</option>)}
        </select>
        <select className="select" style={{ flex: "1 1 120px" }} value={role} onChange={(e) => setRole(e.target.value)}>
          {["member", "viewer", "guest", "owner", "admin"].map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <button className="btn primary" type="submit" disabled={!email.includes("@")}>Invite</button>
      </form>
      <span className="hint">People outside your verified domains join as external guests: they see only the spaces they&apos;re invited to.</span>
      {link ? (
        <div className="note success" style={{ wordBreak: "break-all" }}>
          Invite link (valid 7 days): {link}
          <button className="btn small" onClick={() => navigator.clipboard?.writeText(link)}>Copy</button>
        </div>
      ) : null}
      <ErrorNote error={error ?? actionError} />
      {data?.length ? (
        <div className="stack">
          {data.map((i) => (
            <div key={i.id} className="row between">
              <span>{i.email}{i.space ? ` → ${i.space} (${i.role})` : ""}</span>
              <span className="row">
                <Pill tone={i.status === "accepted" ? "success" : i.status === "expired" ? "danger" : undefined}>{i.status}</Pill>
                <span className="hint">{when(i.created_at)}</span>
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}

function Domains() {
  const { data, error, reload } = useApi<DomainRow[]>("/admin/domains");
  const [domain, setDomain] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setActionError(null);
    try {
      await api("/admin/domains", { method: "POST", json: { domain: domain.trim() } });
      setDomain("");
      await reload();
    } catch (err) {
      setActionError(errorText(err));
    }
  }

  async function verify(name: string) {
    setActionError(null);
    try {
      await api(`/admin/domains/${name}/verify`, { method: "POST" });
      await reload();
    } catch (err) {
      setActionError(errorText(err));
    }
  }

  return (
    <Panel title="Verified domains" meta="Anyone with a verified email domain can sign in and join your org">
      <form className="row" onSubmit={add}>
        <input className="input" placeholder="company.com" value={domain} onChange={(e) => setDomain(e.target.value)} />
        <button className="btn" type="submit" disabled={!domain.includes(".")}>Add domain</button>
      </form>
      <ErrorNote error={error ?? actionError} />
      {data?.map((d) => (
        <div key={d.domain} className="stack" style={{ gap: 4 }}>
          <div className="row between">
            <strong>{d.domain}</strong>
            {d.verified ? <Pill tone="success">Verified</Pill> : (
              <button className="btn small primary" onClick={() => verify(d.domain)}>Check DNS</button>
            )}
          </div>
          {!d.verified ? (
            <span className="hint">Add a DNS TXT record on {d.domain}: <code>{d.txt_record}</code></span>
          ) : null}
        </div>
      ))}
    </Panel>
  );
}

function UsagePanel() {
  const { data, error, reload } = useApi<Usage>("/admin/usage");
  const [cap, setCap] = useState("");

  async function saveCap(e: React.FormEvent) {
    e.preventDefault();
    await api("/admin/usage/cap", { method: "PUT", json: { cap_usd: cap.trim() === "" ? null : Number(cap) } });
    setCap("");
    await reload();
  }

  return (
    <Panel
      title="Model usage this month"
      meta={data ? `$${data.spent_usd.toFixed(2)} of ${data.cap_usd === null ? "no cap" : `$${data.cap_usd.toFixed(2)} cap`}` : undefined}
    >
      <ErrorNote error={error} />
      {!data ? <Loading /> : (
        <>
          {data.by_task.length === 0 ? <p className="muted" style={{ margin: 0 }}>No model calls yet this month.</p> : (
            <table className="table">
              <thead><tr><th>Task</th><th>Model</th><th>Calls</th><th>Tokens in / out</th><th>Cost</th></tr></thead>
              <tbody>
                {data.by_task.map((t) => (
                  <tr key={`${t.task}-${t.model}`}>
                    <td>{t.task}</td><td>{t.model}</td><td>{t.calls}</td>
                    <td>{t.input_tokens.toLocaleString()} / {t.output_tokens.toLocaleString()}</td>
                    <td>${t.cost_usd.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <form className="row" onSubmit={saveCap}>
            <input className="input" style={{ maxWidth: 160 }} inputMode="decimal" placeholder="Cap in USD" value={cap}
              onChange={(e) => setCap(e.target.value)} />
            <button className="btn" type="submit">Set monthly cap</button>
          </form>
          <span className="hint">At the cap, model features pause: PR checks report neutral and Ask says it can&apos;t answer. Leave empty for no cap.</span>
        </>
      )}
    </Panel>
  );
}

function Audit() {
  const { data, error } = useApi<AuditRow[]>("/admin/audit?limit=100");
  return (
    <Panel title="Audit log" meta="Sign-ins, sessions, invites, roles, domains, connections">
      <ErrorNote error={error} />
      {!data ? <Loading /> : (
        <table className="table">
          <thead><tr><th>When</th><th>What</th><th>Who</th><th>Subject</th><th>Result</th></tr></thead>
          <tbody>
            {data.map((r, i) => (
              <tr key={i}>
                <td>{when(r.at)}</td>
                <td>{r.action}</td>
                <td>{r.actor ?? "—"}</td>
                <td>{r.subject}</td>
                <td>{r.outcome === "success" ? <Pill tone="success">ok</Pill> : <Pill tone="danger">{r.reason || "failed"}</Pill>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

export default function AdminPage() {
  return (
    <Shell crumbs={[{ label: "Admin" }]}>
      <div className="heading">
        <h1 className="h1">Admin</h1>
        <p className="lede">Who can sign in to your org, and what they&apos;ve done.</p>
      </div>
      <div className="stack" style={{ gap: 20 }}>
        <People />
        <Invites />
        <Domains />
        <UsagePanel />
        <Audit />
      </div>
    </Shell>
  );
}

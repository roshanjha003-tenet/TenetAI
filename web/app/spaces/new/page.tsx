"use client";

import { useRouter } from "next/navigation";
import { Layers, LockKeyhole, Users } from "lucide-react";
import { useMemo, useState } from "react";

import { Shell } from "@/components/Shell";
import { Avatar, Panel, SourceRow } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { plural } from "@/lib/format";
import type { SpaceDetail, UserRef } from "@/lib/types";

const STAGE_AREAS = [
  { key: "product-scope", name: "Product scope", hint: "Reviews first: is this the right thing to do?" },
  { key: "technical-safety", name: "Technical safety", hint: "Reviews second: is it safe to build this way?" },
];

function kindOf(url: string): string {
  const host = (() => { try { return new URL(url).host; } catch { return ""; } })();
  if (host.endsWith("atlassian.net")) return "jira";
  if (host.endsWith("notion.so")) return "notion";
  if (host.endsWith("slack.com")) return "slack";
  if (host.endsWith("github.com")) return "github";
  if (host === "docs.google.com") return "gdoc";
  return "doc";
}

function slug(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
}

/** 01 · Create a shared space: identify the work, pull in context, add the right people. */
export default function NewSpace() {
  const router = useRouter();
  const { data: users } = useApi<UserRef[]>("/users");
  const [name, setName] = useState("");
  const [handle, setHandle] = useState("");
  const [goal, setGoal] = useState("");
  const [link, setLink] = useState("");
  const [links, setLinks] = useState<string[]>([]);
  const [owners, setOwners] = useState<Record<string, string>>({});
  const [invitees, setInvitees] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const id = handle || slug(name);
  const people = useMemo(() => users ?? [], [users]);
  const ownerEmails = Object.values(owners).filter(Boolean);
  const everyone = Array.from(new Set([...ownerEmails, ...invitees]));

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const space = await api<SpaceDetail>("/spaces", {
        method: "POST",
        json: {
          handle: id, name, goal,
          areas: STAGE_AREAS.filter((a) => owners[a.key]).map((a) => ({ key: a.key, name: a.name, owner_email: owners[a.key] })),
        },
      });
      for (const url of links) {
        await api(`/spaces/${space.handle}/items`, { method: "POST", json: { url } });
      }
      const already = new Set(space.members.map((m) => m.email));
      for (const email of invitees.filter((e) => !already.has(e))) {
        await api(`/spaces/${space.handle}/members`, { method: "POST", json: { email, role: "member" } });
      }
      router.push(`/spaces/${space.handle}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <Shell crumbs={[{ label: "New space" }]} context={<><Users size={15} /><span>{plural(everyone.length, "invitation")} ready</span></>}>
      <div className="heading">
        <span className="eyebrow">Create shared space</span>
        <div className="title-row"><h1 className="h1">Bring the work together</h1><span className="pill">Setup draft</span></div>
        <p className="lede">Link the context. Add the people. Give the work one place to agree.</p>
      </div>
      <div className="cols">
        <div className="col-main">
          <Panel title="Space details" meta="01 / Identify the work">
            <div className="row top" style={{ gap: 18 }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="label" htmlFor="name">Space name</label>
                <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Checkout redesign" />
              </div>
              <div className="field" style={{ width: 240 }}>
                <label className="label" htmlFor="handle">Project ID</label>
                <input id="handle" className="input" value={`@${id}`} onChange={(e) => setHandle(slug(e.target.value))} />
              </div>
            </div>
            <div className="field">
              <label className="label" htmlFor="goal">Purpose</label>
              <input id="goal" className="input" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="What should this work achieve?" />
              <span className="hint">Use this @id to intentionally share work from your private AI space.</span>
            </div>
          </Panel>

          <Panel title="Link source material" meta="02 / Pull in context">
            <form className="row" onSubmit={(e) => { e.preventDefault(); if (link.trim()) { setLinks([...links, link.trim()]); setLink(""); } }}>
              <input className="input" value={link} onChange={(e) => setLink(e.target.value)} placeholder="Paste a Jira, GitHub, Notion, Docs or Slack link" />
              <button className="btn" type="submit">Add link</button>
            </form>
            {links.length === 0 ? <p className="muted small">No sources yet. You can add more later.</p> : links.map((l) => (
              <SourceRow key={l} kind={kindOf(l)} title={l.replace(/^https?:\/\//, "")} href={l} />
            ))}
          </Panel>

          <Panel title="Review owners" meta="03 / Who approves">
            {STAGE_AREAS.map((a) => (
              <div key={a.key} className="field">
                <label className="label" htmlFor={a.key}>{a.name}</label>
                <select id={a.key} className="select" value={owners[a.key] ?? ""} onChange={(e) => setOwners({ ...owners, [a.key]: e.target.value })}>
                  <option value="">You</option>
                  {people.map((u) => <option key={u.id} value={u.email}>{u.name}</option>)}
                </select>
                <span className="hint">{a.hint}</span>
              </div>
            ))}
          </Panel>

          <Panel title="Invite collaborators" meta="04 / Add the right people">
            <div className="row wrap">
              {people.map((u) => {
                const on = invitees.includes(u.email) || ownerEmails.includes(u.email);
                return (
                  <button key={u.id} type="button" className={`chip ${on ? "selected" : ""}`}
                    onClick={() => setInvitees(on ? invitees.filter((e) => e !== u.email) : [...invitees, u.email])}>
                    <Avatar name={u.name} /> {u.name}{u.title ? ` · ${u.title}` : ""}
                  </button>
                );
              })}
            </div>
            <span className="hint">You are the admin. Review owners are added automatically.</span>
          </Panel>
        </div>

        <div className="col-side">
          <Panel>
            <span className="tiny-label">Your shared space</span>
            <div className="stack" style={{ gap: 10 }}>
              <div style={{ width: 42, height: 42, borderRadius: 10, background: "var(--accent-soft)", display: "grid", placeItems: "center" }}>
                <Layers size={20} color="var(--accent)" />
              </div>
              <span style={{ fontSize: 22, fontWeight: 600 }}>{name || "Untitled space"}</span>
              <span className="chip" style={{ alignSelf: "flex-start" }}>@{id || "space-id"}</span>
            </div>
            <div className="divider" />
            <p className="muted" style={{ margin: 0 }}>{plural(links.length, "linked source")} · {plural(everyone.length, "invitee")} · 0 agreed decisions yet.</p>
            {error ? <div className="error">{error}</div> : null}
            <button className="btn primary block" disabled={!name.trim() || !id || busy} onClick={create}>
              {busy ? "Creating…" : "Create shared space"}
            </button>
          </Panel>
          <div className="note" style={{ background: "transparent" }}>
            <LockKeyhole size={18} />
            <span><strong style={{ color: "var(--text)" }}>Shared context. Private thinking.</strong><br />
              Only linked context is shared; your private AI conversations stay private.</span>
          </div>
        </div>
      </div>
    </Shell>
  );
}

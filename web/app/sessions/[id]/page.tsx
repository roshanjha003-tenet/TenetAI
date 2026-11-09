"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowUp, ArrowUpRight, Check, FileText, GitPullRequest, LockKeyhole, Plus, Search, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Shell } from "@/components/Shell";
import { ErrorNote, Loading, Panel } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { plural, when } from "@/lib/format";
import type { Attachment, GoogleDoc, GoogleStatus, Message, Session, Shared, SpaceDetail } from "@/lib/types";

const ACTIONS = [
  { key: "finding", label: "Share a finding", hint: "Everyone sees it now and can respond. No approval." },
  { key: "decision", label: "Propose a decision", hint: "Drafted into a decision and sent through the review." },
  { key: "status", label: "Update status", hint: "Progress, a blocker or a change, for the owners to confirm." },
  { key: "question", label: "Ask the space", hint: "Answered from the agreed record. Name an agent (@space/pr-12) to ask it." },
];

type Reply = { message: Message; reply: Message; shared: Shared | null };

/** 02 · A private session: your own AI, your attached Docs, and an explicit share step. */
export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session, error, setData } = useApi<Session>(`/sessions/${id}`);
  const { data: space } = useApi<SpaceDetail>(session ? `/spaces/${session.space}` : null);
  const { data: google, reload: reloadGoogle } = useApi<GoogleStatus>("/connect/google");
  const [draft, setDraft] = useState("");
  const [share, setShare] = useState("");
  const [action, setAction] = useState("finding");
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [lastShare, setLastShare] = useState<Shared | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Newer browsers return a Promise from scrollIntoView; an effect must return nothing.
    void bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages.length]);

  const handle = session?.space ?? "";
  const tagsSpace = useMemo(() => new RegExp(`(^|[^\\w@])@${handle}\\b`, "i").test(draft), [draft, handle]);

  if (!session) return <Shell crumbs={[{ label: "Private session" }]}><ErrorNote error={error} /><Loading /></Shell>;

  async function send(text: string, extra: { action?: string; attachment_ids?: string[] } = {}) {
    setBusy(true);
    setSendError(null);
    try {
      const result = await api<Reply>(`/sessions/${id}/messages`, { method: "POST", json: { text, ...extra } });
      setData((s) => (s ? { ...s, messages: [...s.messages, result.message, result.reply] } : s));
      if (result.shared) {
        setLastShare(result.shared);
        const fresh = await api<Session>(`/sessions/${id}`);
        setData(fresh);
      }
      return true;
    } catch (e) {
      setSendError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function sendPrivate() {
    if (!draft.trim()) return;
    if (await send(draft)) setDraft("");
  }

  async function sendShare() {
    if (!share.trim()) return;
    const text = `@${handle} ${share.trim()}`;
    if (await send(text, { action, attachment_ids: chosen })) {
      setShare("");
      setChosen([]);
    }
  }

  const stages = space?.stages.map((s) => space.areas.find((a) => a.key === s.area)?.owner.name).filter(Boolean) ?? [];

  return (
    <Shell crumbs={[{ label: "Your private workspace", href: "/sessions" }, { label: session.title }]}
      context={<><span>@{handle}</span><span className="sep" /><LockKeyhole size={15} /><span>Only you</span></>}>
      <div className="heading">
        <span className="eyebrow">Private draft · before sharing</span>
        <div className="title-row"><h1 className="h1">{session.title}</h1><span className="pill">Only you</span></div>
        <p className="lede">Working from @{handle} · agreed v{space?.head_version ?? "…"}</p>
      </div>

      <div className="cols">
        <div className="col-main">
          <div className="note"><LockKeyhole size={18} /><span>This conversation is private. Nothing here is sent to the shared space unless you share it on the right.</span></div>

          <div className="chat">
            {session.messages.length === 0 ? <p className="muted">Ask your AI anything about the work. It knows the space&apos;s agreed state and your attached Docs.</p> : null}
            {session.messages.map((m) => m.role === "user" ? (
              <div key={m.id} className="bubble">
                <div className="who">You <span className="small muted" style={{ fontWeight: 400 }}>{when(m.created_at)}</span>
                  {m.shared_event_id ? <span className="pill accent">Shared</span> : null}</div>
                <div style={{ fontSize: 14 }}>{m.text}</div>
              </div>
            ) : (
              <div key={m.id} className="bubble ai">
                <div className="who"><Sparkles size={18} color="var(--accent)" />Your Tenet AI <span className="pill">Private</span></div>
                <div style={{ fontSize: 14 }}>{m.text}</div>
              </div>
            ))}
            <div ref={bottom} />
          </div>

          {tagsSpace ? <div className="note warn">This message tags @{handle}: that paragraph will be shared with the space. Use the share panel to choose how.</div> : null}
          <ErrorNote error={sendError} />
          <form className="composer" onSubmit={(e) => { e.preventDefault(); void sendPrivate(); }}>
            <Plus size={18} color="var(--muted)" style={{ marginBottom: 10 }} />
            {session.attachments.length ? <span className="chip" style={{ marginBottom: 6 }}><FileText size={12} />{plural(session.attachments.length, "Doc")}</span> : null}
            <textarea aria-label="Message your AI" rows={2} value={draft} placeholder="Keep thinking with your AI…"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void sendPrivate(); } }} />
            <button className="icon-btn" type="submit" disabled={busy} aria-label="Send"><ArrowUp size={18} className={busy ? "spin" : ""} /></button>
          </form>

          <ContextTray session={session} google={google} onGoogle={reloadGoogle} onAttached={(a) => setData({ ...session, attachments: [...session.attachments, a] })} />
        </div>

        <div className="col-side" style={{ width: 440 }}>
          <Panel title="Preview what you'll share" className="accent" actions={<Link href={`/spaces/${handle}`}><ArrowUpRight size={18} color="var(--accent)" /></Link>}>
            <div className="field">
              <span className="tiny-label">Project tag</span>
              <div className="row between" style={{ background: "var(--accent-soft)", color: "var(--accent)", borderRadius: 6, padding: 12 }}>
                <strong>@{handle}</strong><span className="small">{space ? plural(space.members.length, "member") : ""}</span>
              </div>
            </div>
            <div className="field">
              <span className="tiny-label">Choose a sharing action</span>
              {ACTIONS.map((a) => (
                <button key={a.key} type="button" className={`choice ${action === a.key ? "selected" : ""}`} onClick={() => setAction(a.key)}>
                  <span className="radio" />
                  <span><span style={{ fontWeight: 500 }}>{a.label}</span><br /><span className="small muted">{a.hint}</span></span>
                </button>
              ))}
            </div>
            <div className="field">
              <label className="tiny-label" htmlFor="share">Only this text leaves your session</label>
              <textarea id="share" className="textarea" value={share} onChange={(e) => setShare(e.target.value)}
                placeholder={action === "question" ? "e.g. where are we on this? or @space/pr-12 why did this check fail?" : "Write exactly what the team should see"} />
            </div>
            {session.attachments.length ? (
              <div className="field">
                <span className="tiny-label">Share these Docs with it</span>
                <div className="row wrap">
                  {session.attachments.map((a) => {
                    const on = chosen.includes(a.id);
                    return (
                      <button key={a.id} type="button" className={`chip ${on ? "selected" : ""}`}
                        onClick={() => setChosen(on ? chosen.filter((x) => x !== a.id) : [...chosen, a.id])}>
                        {on ? <Check size={12} /> : <FileText size={12} />}{a.title}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
            {action === "decision" && stages.length ? (
              <div className="row small muted"><GitPullRequest size={16} />Review order: {stages.join(" → ")}</div>
            ) : null}
            <button className="btn primary block" disabled={busy || !share.trim()} onClick={sendShare}>
              {ACTIONS.find((a) => a.key === action)?.label}
            </button>
            <span className="hint">
              Sends “@{handle} …” with {plural(chosen.length, "Doc")} to the {space ? plural(space.members.length, "member") : "members"}. The rest of this conversation stays private.
              {action === "decision" ? ` Shared state stays v${space?.head_version ?? ""} until every reviewer approves.` : ""}
            </span>
          </Panel>

          {lastShare ? (
            <Panel title="Just shared">
              <div className="quote">{lastShare.tagged_text}</div>
              {lastShare.finding_id ? <Link className="link" href={`/spaces/${handle}/findings/${lastShare.finding_id}`}>Open the finding →</Link> : null}
              {lastShare.proposal_id ? <Link className="link" href={`/spaces/${handle}/proposals/${lastShare.proposal_id}`}>Open {lastShare.decision_key ?? "the proposal"} ({lastShare.status}) →</Link> : null}
              {lastShare.answer ? <span>{lastShare.answer.agent}: {lastShare.answer.answer}</span> : null}
              {lastShare.notes.map((n) => <span key={n} className="small muted">({n})</span>)}
            </Panel>
          ) : null}
        </div>
      </div>
    </Shell>
  );
}

function ContextTray({ session, google, onGoogle, onAttached }: {
  session: Session;
  google: GoogleStatus | null;
  onGoogle: () => void;
  onAttached: (a: Attachment) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [link, setLink] = useState("");
  const [docs, setDocs] = useState<GoogleDoc[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !google?.connected) return;
    const t = setTimeout(() => {
      api<GoogleDoc[]>(`/connect/google/docs?q=${encodeURIComponent(query)}`).then(setDocs).catch((e) => setError(String(e.message ?? e)));
    }, 250);
    return () => clearTimeout(t);
  }, [open, query, google?.connected]);

  async function attach(url: string) {
    setBusy(true);
    setError(null);
    try {
      onAttached(await api<Attachment>(`/sessions/${session.id}/attachments`, { method: "POST", json: { url } }));
      setLink("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel tight">
      <div className="row between">
        <button className="row" style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }} onClick={() => { setOpen(!open); onGoogle(); }}>
          <span className="source-mark" style={{ width: 28, height: 28 }}><Plus size={16} /></span>
          <span style={{ textAlign: "left" }}><strong>Add context</strong><br /><span className="small muted">Attach Google Docs to this conversation</span></span>
        </button>
        <span className="pill">Private</span>
      </div>
      {session.attachments.length ? (
        <div className="row wrap">
          {session.attachments.map((a) => (
            <a key={a.id} className="chip" href={a.url} target="_blank" rel="noreferrer">
              <FileText size={12} />{a.title}{a.shared_item_id ? " · shared" : ""}
            </a>
          ))}
        </div>
      ) : null}
      {open ? (
        !google?.configured ? <span className="small muted">Google Drive isn&apos;t set up on this server yet.</span>
          : !google.connected ? (
            <span className="small">Connect your Google account in <Link className="link" href="/settings/connections">Connections</Link> to attach Docs.</span>
          ) : (
            <>
              <div className="row">
                <div className="row" style={{ flex: 1, border: "1px solid var(--border)", borderRadius: 8, padding: "0 12px" }}>
                  <Search size={16} color="var(--muted)" />
                  <input className="input" style={{ border: "none" }} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search your Google Docs…" />
                </div>
              </div>
              {docs?.map((d) => (
                <div key={d.id} className="row between">
                  <span className="row"><FileText size={14} color="var(--muted)" />{d.title}</span>
                  <button className="btn small" disabled={busy} onClick={() => attach(d.id)}><Plus size={14} />Add to chat</button>
                </div>
              ))}
              <form className="row" onSubmit={(e) => { e.preventDefault(); if (link.trim()) void attach(link.trim()); }}>
                <input className="input" value={link} onChange={(e) => setLink(e.target.value)} placeholder="…or paste a Google Doc link" />
                <button className="btn" disabled={busy || !link.trim()}>Attach</button>
              </form>
              <span className="hint">Attached Docs are read with your Google permissions and stay private until you share them.</span>
            </>
          )
      ) : null}
      <ErrorNote error={error} />
    </section>
  );
}

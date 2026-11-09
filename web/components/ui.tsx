import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";

import { initials, KIND_LABEL, KIND_MARK } from "@/lib/format";
import type { Evidence, UserRef } from "@/lib/types";

export function Avatar({ name }: { name: string | null | undefined }) {
  return <div className="avatar" aria-hidden>{initials(name)}</div>;
}

export function Person({ user, sub }: { user: UserRef | null | undefined; sub?: ReactNode }) {
  return (
    <div className="person">
      <Avatar name={user?.name} />
      <div>
        <div className="person-name">{user?.name ?? "Unknown"}</div>
        {sub ? <div className="person-sub">{sub}</div> : null}
      </div>
    </div>
  );
}

const TONE: Record<string, string> = {
  approved: "success",
  active: "success",
  matches: "success",
  success: "success",
  complete: "success",
  agree: "success",
  pending: "warn",
  waiting: "accent",
  under_review: "warn",
  stale: "warn",
  concern: "warn",
  question: "accent",
  blocked: "danger",
  rejected: "danger",
  drift: "danger",
  failure: "danger",
  abandoned: "danger",
  orphaned: "warn",
  promoted: "accent",
  open: "accent",
};

export function Pill({ children, tone }: { children: ReactNode; tone?: string }) {
  return <span className={`pill ${tone ?? ""}`}>{children}</span>;
}

export function StatusPill({ status, label }: { status: string; label?: string }) {
  return <Pill tone={TONE[status]}>{label ?? status.replace(/_/g, " ")}</Pill>;
}

export function Panel({ title, meta, children, className = "", actions }: {
  title?: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
}) {
  return (
    <section className={`panel ${className}`}>
      {title || meta || actions ? (
        <div className="panel-head">
          {title ? <h2 className="panel-title">{title}</h2> : <span />}
          <div className="row">
            {meta ? <span className="panel-meta">{meta}</span> : null}
            {actions}
          </div>
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function SourceRow({ kind, title, sub, href, internal }: {
  kind: string;
  title: string;
  sub?: string;
  href?: string;
  internal?: boolean;
}) {
  const body = (
    <>
      <div className="source-mark">{KIND_MARK[kind] ?? kind.slice(0, 2).toUpperCase()}</div>
      <div className="source-body">
        <div className="source-title">{title}</div>
        <div className="source-sub">{sub ?? KIND_LABEL[kind] ?? kind}</div>
      </div>
      {href ? <ArrowUpRight size={15} color="var(--muted)" /> : null}
    </>
  );
  if (!href) return <div className="source">{body}</div>;
  if (internal) return <Link className="source" href={href}>{body}</Link>;
  return <a className="source" href={href} target="_blank" rel="noreferrer">{body}</a>;
}

export function EvidenceChips({ evidence, handle }: { evidence: Evidence[]; handle?: string }) {
  if (!evidence?.length) return null;
  return (
    <div className="row wrap">
      {evidence.map((e, i) => {
        const label = `${KIND_LABEL[e.kind] ?? e.kind} · ${e.title}`;
        if (e.url) return <a key={i} className="chip" href={e.url} target="_blank" rel="noreferrer">{label}</a>;
        if (handle && e.kind === "decision" && e.id) {
          return <Link key={i} className="chip" href={`/spaces/${handle}/decisions/${e.id}`}>{label}</Link>;
        }
        return <span key={i} className="chip">{label}</span>;
      })}
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <div className="empty">{what}…</div>;
}

export function ErrorNote({ error }: { error: string | null }) {
  return error ? <div className="note danger">{error}</div> : null;
}

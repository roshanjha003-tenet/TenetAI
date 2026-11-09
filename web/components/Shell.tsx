"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronRight, LogOut } from "lucide-react";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { Avatar } from "@/components/ui";
import { api } from "@/lib/api";
import type { Me, Proposal } from "@/lib/types";

type ShellState = { me: Me | null; approvals: number; refresh: () => Promise<void> };
const ShellContext = createContext<ShellState>({ me: null, approvals: 0, refresh: async () => {} });

export function useShell() {
  return useContext(ShellContext);
}

/** Sidebar + top bar. Everything in it comes from /me and /approvals. */
export function Shell({ crumbs, context, children }: {
  crumbs: { label: string; href?: string }[];
  context?: ReactNode;
  children: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [approvals, setApprovals] = useState(0);

  async function refresh() {
    const [m, a] = await Promise.all([api<Me>("/me"), api<Proposal[]>("/approvals")]);
    setMe(m);
    setApprovals(a.length);
  }

  useEffect(() => {
    refresh().catch(() => {}); // a 401 sends the browser to /login
  }, []);

  async function signOut() {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    router.push("/login");
  }

  const active = (href: string) => (pathname === href || pathname.startsWith(`${href}/`) ? "active" : "");

  return (
    <ShellContext.Provider value={{ me, approvals, refresh }}>
      <div className="shell">
        <nav className="sidebar" aria-label="Workspace">
          <Link href="/" className="logo">
            <div className="logo-mark">T</div>
            <div className="logo-name">Tenet AI</div>
          </Link>
          <div className="nav-label">SPACES</div>
          {me?.spaces.map((s) => (
            <Link key={s.id} href={`/spaces/${s.handle}`} className={`nav-item ${active(`/spaces/${s.handle}`)}`}>
              <span>@{s.handle}</span>
            </Link>
          ))}
          <Link href="/spaces/new" className={`nav-item subtle ${active("/spaces/new")}`}><span>+ New space</span></Link>
          <div className="nav-label">YOU</div>
          <Link href="/sessions" className={`nav-item ${active("/sessions")}`}><span>Private sessions</span></Link>
          <Link href="/approvals" className={`nav-item ${active("/approvals")}`}>
            <span>Approvals</span>
            <span className="nav-count">{approvals}</span>
          </Link>
          <Link href="/settings/connections" className={`nav-item ${active("/settings/connections")}`}><span>Connections</span></Link>
          <Link href="/settings/security" className={`nav-item ${active("/settings/security")}`}><span>Sign-in &amp; sessions</span></Link>
          {me?.is_org_admin ? (
            <>
              <div className="nav-label">ORG</div>
              <Link href="/admin" className={`nav-item ${active("/admin")}`}><span>Admin</span></Link>
            </>
          ) : null}
          <div className="grow" />
          {me ? (
            <button className="user-switch" onClick={signOut} title="Sign out">
              <Avatar name={me.name} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="user-name">{me.name}</div>
                <div className="user-title">{me.title ?? me.email}</div>
              </div>
              <LogOut size={14} color="var(--muted)" />
            </button>
          ) : null}
        </nav>
        <div className="main">
          <header className="topbar">
            <div className="crumbs">
              {crumbs.map((c, i) => (
                <span key={i} className="row" style={{ gap: 12 }}>
                  {i > 0 ? <ChevronRight size={13} /> : null}
                  {c.href ? <Link href={c.href}>{c.label}</Link> : <span className="here">{c.label}</span>}
                </span>
              ))}
            </div>
            <div className="top-context">{context}</div>
          </header>
          <main className="page">{children}</main>
        </div>
      </div>
    </ShellContext.Provider>
  );
}

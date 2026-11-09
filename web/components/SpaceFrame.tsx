"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Users } from "lucide-react";
import { createContext, useContext, type ReactNode } from "react";

import { Shell } from "@/components/Shell";
import { ErrorNote, Loading } from "@/components/ui";
import { useApi } from "@/lib/api";
import { plural } from "@/lib/format";
import type { SpaceDetail } from "@/lib/types";

type SpaceState = { space: SpaceDetail; reload: () => Promise<void> };
const SpaceContext = createContext<SpaceState | null>(null);

export function useSpace(): SpaceState {
  const value = useContext(SpaceContext);
  if (!value) throw new Error("useSpace outside SpaceFrame");
  return value;
}

const TABS = [
  { href: "", label: "Overview" },
  { href: "/reviews", label: "Reviews" },
  { href: "/findings", label: "Findings" },
  { href: "/sources", label: "Sources" },
  { href: "/agents", label: "Agents" },
  { href: "/history", label: "Decision history" },
];

/** Loads a space once and gives every tab its header, tabs and data. */
export function SpaceFrame({ handle, crumb, children }: { handle: string; crumb?: string; children: ReactNode }) {
  const { data: space, error, reload } = useApi<SpaceDetail>(`/spaces/${handle}`);
  const pathname = usePathname();
  const base = `/spaces/${handle}`;

  return (
    <Shell
      crumbs={[{ label: `@${handle}`, href: base }, ...(crumb ? [{ label: crumb }] : [])]}
      context={space ? (
        <>
          <span>Agreed · v{space.head_version}</span>
          <span className="sep" />
          <Users size={15} />
          <span>{plural(space.members.length, "collaborator")}</span>
        </>
      ) : null}
    >
      <ErrorNote error={error} />
      {!space ? <Loading /> : (
        <SpaceContext.Provider value={{ space, reload }}>
          <nav className="tabs" aria-label="Space">
            {TABS.map((t) => {
              const href = `${base}${t.href}`;
              const on = t.href === "" ? pathname === base : pathname.startsWith(href);
              return (
                <Link key={t.label} href={href} className={`tab ${on ? "active" : ""}`}>
                  {t.label}
                  {t.href === "/reviews" && space.pending_proposals ? <span className="count">{space.pending_proposals}</span> : null}
                </Link>
              );
            })}
          </nav>
          {children}
        </SpaceContext.Provider>
      )}
    </Shell>
  );
}

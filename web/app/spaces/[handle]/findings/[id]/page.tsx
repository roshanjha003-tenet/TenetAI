"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { FindingCard } from "@/components/FindingCard";
import { useShell } from "@/components/Shell";
import { useSpace } from "@/components/SpaceFrame";
import { ErrorNote, Loading } from "@/components/ui";
import { useApi } from "@/lib/api";
import type { Finding } from "@/lib/types";

export default function FindingPage() {
  const { id } = useParams<{ id: string }>();
  const { space } = useSpace();
  const { me } = useShell();
  const { data, error, setData } = useApi<Finding>(`/findings/${id}`);
  const ownsArea = Boolean(me && space.areas.some((a) => a.owner.id === me.id));
  return (
    <div className="stack" style={{ maxWidth: 820 }}>
      <Link className="link" href={`/spaces/${space.handle}/findings`}>← All findings</Link>
      <ErrorNote error={error} />
      {!data ? <Loading /> : (
        <FindingCard finding={data} handle={space.handle} expanded onChange={setData}
          canPromote={Boolean(me && (data.author?.id === me.id || ownsArea))} />
      )}
    </div>
  );
}

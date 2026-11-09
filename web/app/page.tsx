"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    api<Me>("/me")
      .then((me) => router.replace(me.spaces.length ? `/spaces/${me.spaces[0].handle}` : "/spaces/new"))
      .catch(() => router.replace("/login"));
  }, [router]);
  return <div className="center muted">Opening Tenet…</div>;
}

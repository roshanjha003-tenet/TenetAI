"use client";

import { useParams } from "next/navigation";

import { SpaceFrame } from "@/components/SpaceFrame";

export default function SpaceLayout({ children }: { children: React.ReactNode }) {
  const { handle } = useParams<{ handle: string }>();
  return <SpaceFrame handle={handle}>{children}</SpaceFrame>;
}

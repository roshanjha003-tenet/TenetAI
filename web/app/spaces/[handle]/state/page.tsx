"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

/** Links in Slack point here ("see what changed"); the history view answers that. */
export default function StateRedirect() {
  const { handle } = useParams<{ handle: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/spaces/${handle}/history`);
  }, [handle, router]);
  return null;
}

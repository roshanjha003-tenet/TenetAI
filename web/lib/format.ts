export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : parts[0][1] ?? "")).toUpperCase();
}

const dateFmt = new Intl.DateTimeFormat("en", { month: "short", day: "numeric" });
const timeFmt = new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false });

export function when(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${dateFmt.format(d)} · ${timeFmt.format(d)}`;
}

export function day(iso: string | null | undefined): string {
  return iso ? dateFmt.format(new Date(iso)) : "";
}

export function ago(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return day(iso);
}

export const KIND_MARK: Record<string, string> = {
  jira: "J",
  github: "GH",
  notion: "N",
  slack: "#",
  doc: "D",
  gdoc: "G",
  pr: "PR",
  decision: "D",
  finding: "F",
};

export const KIND_LABEL: Record<string, string> = {
  jira: "Jira",
  github: "GitHub",
  notion: "Notion",
  slack: "Slack",
  doc: "Link",
  gdoc: "Google Doc",
  pr: "Pull request",
  decision: "Decision",
  finding: "Finding",
};

export function plural(n: number, word: string, many = `${word}s`): string {
  return `${n} ${n === 1 ? word : many}`;
}

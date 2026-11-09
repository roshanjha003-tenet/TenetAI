export type UserRef = { id: string; name: string; email: string; title: string | null; github_login: string | null };

export type SpaceSummary = { id: string; handle: string; name: string; goal: string; head_version: number; created_at: string; role?: string };

export type Me = UserRef & { spaces: SpaceSummary[]; is_org_admin: boolean; external: boolean };

export type AuthConfig = { providers: { id: string; label: string }[]; dev: boolean };

export type InviteInfo = {
  org: string;
  space: string | null;
  role: string;
  email: string;
  invited_by: string;
  expired: boolean;
  accepted: boolean;
};

export type AuthSessionRow = {
  id: string;
  provider: string;
  ip: string;
  user_agent: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
};

export type Person = UserRef & { active: boolean; is_org_admin: boolean; external: boolean };

export type InviteRow = {
  id: string;
  email: string;
  space: string | null;
  role: string;
  status: "pending" | "accepted" | "expired";
  expires_at: string;
  created_at: string;
  link?: string;
};

export type DomainRow = { domain: string; verified: boolean; verified_at: string | null; txt_record: string };

export type AuditRow = {
  at: string;
  action: string;
  actor: string | null;
  subject: string;
  outcome: "success" | "failure";
  reason: string;
  ip: string;
  details: Record<string, unknown>;
};

export type Usage = {
  month_start: string;
  spent_usd: number;
  cap_usd: number | null;
  by_task: { task: string; model: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number }[];
};

export type Item = { id: string; kind: string; url: string; title: string; excerpt: string; added_at: string };

export type Stage = { number: number; name: string; area: string };

export type SpaceDetail = SpaceSummary & {
  members: (UserRef & { role: string; areas: string[] })[];
  areas: { key: string; name: string; owner: UserRef }[];
  items: Item[];
  stages: Stage[];
  pending_proposals: number;
};

export type Approval = { user_id: string; name: string; stage: string; at: string };

export type DecisionEntry = {
  key: string;
  title: string;
  statement: string;
  constraints: string[];
  parents: string[];
  area: string;
  status: string;
  revision: number;
  proposer: string;
  approved_by: Approval[];
};

export type StateVersion = {
  version: number;
  parent_version: number | null;
  summary: string;
  committed_by: UserRef | null;
  created_at: string;
  snapshot: { decisions: Record<string, DecisionEntry>; status?: { text: string; by: string; at: string; title: string } };
  head_version?: number;
};

export type ProposalStage = { number: number; name: string; owner: UserRef | null; state: string; note: string | null; at: string | null };

export type Pushback = { id: string; reason: string; raised_by: UserRef | null; outcome: string | null; note: string | null; resolved_by: UserRef | null; created_at: string };

export type Evidence = { kind: string; id?: string; title: string; url?: string };

export type Proposal = {
  id: string;
  type: string;
  title: string;
  content: {
    statement?: string;
    constraints?: string[];
    parents?: string[];
    area?: string;
    text?: string;
    tagged_text?: string;
    conflicts?: { decision: string; constraint: string; explanation: string }[];
  };
  evidence: Evidence[];
  decision_key: string | null;
  status: string;
  base_version: number;
  current_stage: number;
  committed_version: number | null;
  proposer: UserRef | null;
  created_at: string;
  resolved_at: string | null;
  stages: ProposalStage[];
  pushbacks: Pushback[];
  space?: SpaceSummary;
};

export type EventView = {
  id: string;
  seq: number;
  type: string;
  at: string;
  actor: UserRef | null;
  target: { kind: string; id: string; revision: number | null };
  payload: Record<string, unknown>;
};

export type CheckFinding = {
  decision: string;
  decision_title: string;
  revision: number;
  constraint: string;
  approvers: { name: string; stage: string }[];
  file: string;
  start_line: number;
  end_line: number;
  explanation: string;
};

export type PRCheck = {
  id: string;
  repo: string;
  pr_number: number;
  head_sha: string;
  result: string;
  conclusion: string;
  title: string;
  summary: string;
  findings: CheckFinding[];
  pr_title: string;
  pr_author: string;
  pr_url: string;
  created_at: string;
};

export type PRDetail = {
  latest: PRCheck;
  history: PRCheck[];
  links: { decision: string; title: string; pinned_revision: number; current_revision: number; status: string }[];
};

export type Source = { kind: string; id: string; title?: string; url?: string; revision?: number };

export type Answer = { question: string; answer: string; version: number; agent: string; sources: Source[] };

export type FindingReply = { id: string; stance: string; text: string; author: UserRef | null; created_at: string };

export type Finding = {
  id: string;
  text: string;
  author: UserRef | null;
  evidence: Evidence[];
  mentions: string[];
  status: string;
  proposal_id: string | null;
  created_at: string;
  counts: Record<string, number>;
  replies: FindingReply[];
};

export type Agents = {
  space: { agent: string; name: string };
  decisions: { agent: string; key: string; title: string; status: string; prs: number[] }[];
  prs: { agent: string; number: number; repo: string; title: string; url: string; result: string; conclusion: string; implements: string[] }[];
};

export type RewindStep = {
  version: number;
  parent_version: number | null;
  summary: string;
  at: string;
  committed_by: UserRef | null;
  changes: { key: string; change: string; decision?: DecisionEntry; previous?: DecisionEntry; status?: { text: string } }[];
  agreed: Record<string, DecisionEntry>;
  events: EventView[];
};

export type Rewind = { space: string; from: number; to: number; head_version: number; decision: string | null; steps: RewindStep[] };

export type DecisionDetail = {
  key: string;
  title: string;
  status: string;
  current_revision: number;
  area: { key: string; name: string; owner: UserRef };
  revisions: {
    revision: number;
    statement: string;
    constraints: string[];
    parents: string[];
    evidence: Evidence[];
    approvals: Approval[];
    proposer: UserRef | null;
    state_version: number;
    created_at: string;
  }[];
  prs: { repo: string; number: number; pinned_revision: number }[];
};

export type Attachment = { id: string; kind: string; title: string; url: string; chars: number; shared_item_id: string | null; created_at: string };

export type Message = { id: string; role: "user" | "assistant"; text: string; shared_event_id: string | null; created_at: string };

export type Session = { id: string; title: string; space: string; messages: Message[]; attachments: Attachment[] };

export type SessionSummary = { id: string; title: string; space: string; created_at: string };

export type Shared = {
  tagged_text: string;
  route: string;
  finding_id: string | null;
  proposal_id: string | null;
  decision_key: string | null;
  status: string | null;
  notes: string[];
  answer: Answer | null;
  evidence: Evidence[];
};

export type GoogleStatus = { configured: boolean; connected: boolean; email: string | null };

export type GoogleDoc = { id: string; title: string; modified: string; url: string };

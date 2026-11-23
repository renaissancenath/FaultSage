// Response shapes of the cloud routes (src/faultsage/cloud/routes). They return plain dicts, so
// these are written to match those functions; keep both in sync in the same PR.
export interface Plan {
  id: "free" | "pro";
  name: string;
  price_usd_month: number;
  projects: number;
  events_per_month: number;
  retention_days: number;
  seats: number;
  features: string[];
}
export interface Legal {
  operator_name: string;
  operator_address: string;
  grievance_officer: string;
  grievance_email: string;
  jurisdiction_city: string;
  hosting_region: string;
}
export interface Meta {
  mode: "cloud";
  version: string;
  github_login: boolean;
  signup_open: boolean;
  billing: boolean;
  email: boolean;
  support_email: string;
  legal: Legal;
  plans: Plan[];
}
export interface Me {
  user: {
    id: number;
    email: string;
    name: string;
    email_verified: boolean;
    has_password: boolean;
    github_linked: boolean;
    created_at: string;
  };
  org: { id: number; name: string; slug: string; role: "owner" | "maintainer" | "viewer"; plan: Plan };
  orgs: { id: number; name: string; role: string }[];
  usage: { events: number; dropped: number; projects: number; members: number };
}
export interface Project {
  id: number;
  name: string;
  slug: string;
  repo_url: string;
  created_at: string;
  open_issues: number;
  case_files: number;
}
export interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}
export interface IssueRow {
  id: number;
  fingerprint: string;
  title: string;
  exception_type: string | null;
  status: string;
  environment: string;
  last_release: string;
  first_seen_at: string;
  last_seen_at: string;
  event_count: number;
  triaged: boolean;
}
export interface Triage {
  certainty: "confirmed" | "strong" | "possible" | "unknown";
  summary: string;
  location: { file_path: string; line: number | null; function: string | null } | null;
  hypotheses: { rank: number; certainty: string; claim: string }[];
  missing: string[];
  draft_test?: string;
  agent_prompt?: string;
  github_issue_url?: string;
  releases: Record<string, number>;
  environments: Record<string, number>;
  count: number;
}
export interface IssueDetail extends IssueRow {
  triage: Triage | null;
  events: {
    id: number;
    received_at: string;
    payload: {
      exception?: import("./generated").ExceptionInfo;
      release?: string;
      environment?: string;
      server_name?: string;
      message?: string;
    };
  }[];
}
export interface CaseFileRow {
  id: number;
  local_incident_id: number;
  title: string;
  status: string;
  top_certainty: string | null;
  received_at: string;
  updated_at: string;
}
export interface Member {
  id: number;
  email: string;
  name: string;
  role: string;
  created_at: string;
}

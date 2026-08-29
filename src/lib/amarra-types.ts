// Row shapes mirror the Amarra backend contract (amarra/db/*.sql).
// Nothing here is invented client-side; every field is written by the backend.

export type RowId = string | number;

export type SpinePhase =
  | "detected"
  | "mandate_issued"
  | "market_open"
  | "negotiating"
  | "reserved"
  | "committed"
  | "verified"
  | "closed";

export type BranchPhase = "disrupted" | "renegotiating" | "escalated" | "resolved";

export type Phase = SpinePhase | BranchPhase | "failed";

export type ClockState = "safe" | "warning" | "critical" | "expired" | "stopped";

export const SPINE: SpinePhase[] = [
  "detected",
  "mandate_issued",
  "market_open",
  "negotiating",
  "reserved",
  "committed",
  "verified",
  "closed",
];

export const SPINE_LABEL: Record<SpinePhase, string> = {
  detected: "detected",
  mandate_issued: "mandate issued",
  market_open: "market open",
  negotiating: "negotiating",
  reserved: "reserved",
  committed: "committed",
  verified: "verified",
  closed: "closed",
};

export const BRANCHES: BranchPhase[] = ["disrupted", "renegotiating", "escalated", "resolved"];

export const isBranch = (p: Phase | null | undefined): p is BranchPhase =>
  !!p && (BRANCHES as string[]).includes(p);

export interface Operation {
  id: string;
  ref: string;
  container: string | null;
  origin: string | null;
  destination: string | null;
  cargo_value_usd: number | null;
  free_time_ends: string;
  demurrage_per_day: number;
  currency: string | null;
  status: string | null;
  phase: Phase;
  phase_since: string | null;
  clock_state: ClockState;
  clock_state_since: string | null;
  source_event: Record<string, unknown> | null;
  closed_at: string | null;
  outcome: string | null;
  created_at: string;
}

export interface EscalationBand {
  from?: number;
  to?: number;
  [k: string]: unknown;
}

export interface Mandate {
  id: string;
  operation_id: string;
  target_rate: number | null;
  max_rate: number | null;
  min_rate: number | null;
  max_rounds: number | null;
  pickup_from: string | null;
  pickup_to: string | null;
  may_reveal_best_price: boolean | null;
  may_reveal_competitor_name: boolean | null;
  may_reveal_max_rate: boolean | null;
  mandate_hash: string | null;
  issued_at: string | null;
  ladder: unknown[] | null;
  break_even_rate: number | null;
  escalation_band: EscalationBand | null;
  escalation_triggers: unknown[] | null;
  issue_warnings: string[] | null;
  created_at: string;
}

export interface PhaseEvent {
  id: RowId;
  operation_id: string;
  phase: Phase;
  previous: Phase | null;
  kind: "spine" | "branch" | "terminal" | string;
  trigger: string;
  detail: string | null;
  call_id: string | null;
  auction_id: string | null;
  payload: Record<string, unknown> | null;
  ms_in_previous: number | null;
  created_at: string;
}

export interface Auction {
  id: string;
  operation_id: string;
  mandate_id: string | null;
  status: string;
  winner_call_id: string | null;
  reserved_by: string | null;
  reserved_at: string | null;
  reserve_amount: number | null;
  released_from: string | null;
  release_reason: string | null;
  opened_at: string | null;
  dial_plan: unknown[] | null;
  legs_planned: number | null;
  legs_budget: number | null;
  soft_deadline_s: number | null;
  hard_deadline_s: number | null;
  admission_warnings: string[] | null;
  decided_at: string | null;
  decision_reason: string | null;
  created_at: string;
}

export interface AuctionQuote {
  id: RowId;
  auction_id: string;
  call_id: string | null;
  carrier_id: string;
  carrier_name: string | null;
  final_ask: number | null;
  approved: number | null;
  rounds: number;
  winner: boolean;
  reason: string;
  quote_ms: number | null;
  created_at: string;
}

export type CallStatus = "dialing" | "live" | "escalated" | "done" | "failed" | "released";

export interface Call {
  id: string;
  auction_id: string | null;
  operation_id: string | null;
  direction: string | null;
  carrier_id: string | null;
  carrier_name: string | null;
  phone: string | null;
  status: CallStatus | string;
  language: string | null;
  leg_role: "counterparty" | "agent" | "human" | string | null;
  dial_attempt: number | null;
  dial_error: string | null;
  answered_at: string | null;
  audio_public_url: string | null;
  transcript_words: number | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

export interface Utterance {
  id: RowId;
  call_id: string;
  speaker: "counterparty" | "agent" | "human" | string;
  text: string;
  t_ms: number | null;
  interrupted: boolean | null;
  created_at: string;
}

export type PolicyDecision = "allow" | "deny" | "escalate" | "block";

export interface PolicyEvent {
  id: RowId;
  call_id: string;
  counterparty_ask: number | null;
  decision: PolicyDecision | string;
  amount: number | null;
  reason: string | null;
  utterance: string | null;
  round: number | null;
  mandate_hash: string | null;
  created_at: string;
}

export type ReadBackOutcome = "confirmed" | "rejected" | "ambiguous" | "superseded" | "timeout";

export interface ReadBack {
  id: RowId;
  call_id: string;
  operation_id: string;
  token: string;
  slots: Record<string, unknown> | null;
  spoken_text: string;
  response_text: string | null;
  outcome: ReadBackOutcome | string | null;
  attempt: number;
  t_spoken_ms: number | null;
  t_response_ms: number | null;
  created_at: string;
}

export type AnchorState = "pending" | "anchored" | "not_found" | "low_confidence";

export interface Commitment {
  id: RowId;
  call_id: string | null;
  operation_id: string | null;
  field: string;
  value: string;
  quote: string | null;
  state: string;
  anchor_state: AnchorState | string;
  anchor_confidence: number | null;
  anchor_method: string | null;
  audio_url: string | null;
  confidence: number | null;
  t_start_ms: number | null;
  t_end_ms: number | null;
  affirmation_quote: string | null;
  affirmation_t_start_ms: number | null;
  affirmation_t_end_ms: number | null;
  mandate_hash: string | null;
  created_at: string;
}

export interface EscalationComputation {
  option_on_time?: Record<string, unknown>;
  option_late?: Record<string, unknown>;
  delta?: number;
  exceeds_mandate_by?: number;
  [k: string]: unknown;
}

export interface Escalation {
  id: RowId;
  call_id: string;
  trigger: string | null;
  brief: string;
  computation: EscalationComputation | null;
  human_phone: string | null;
  human_joined_at: string | null;
  resolution: string | null;
  created_at: string;
}

export interface RecapDelivery {
  id: RowId;
  operation_id: string;
  call_id: string | null;
  channel: string;
  target: string;
  subject: string | null;
  body: string;
  status: string;
  error: string | null;
  created_at: string;
}

export interface Dossier {
  operation_id: string;
  outcome: string;
  financial: Record<string, unknown>;
  operational: Record<string, unknown>;
  timeline: unknown[];
  commitments: unknown[];
  comparison: unknown[];
  escalations: unknown[];
  mandate_hash: string | null;
  headline: string | null;
  created_at: string;
}

// ── formatting ─────────────────────────────────────────────────────────────
export const money = (v: number | string | null | undefined, currency = "MXN") => {
  const n = typeof v === "string" ? Number(v) : v;
  if (n == null || Number.isNaN(n)) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(n);
  } catch {
    return `${n.toLocaleString("en-US", { maximumFractionDigits: 0 })} ${currency}`;
  }
};

export const num = (v: number | string | null | undefined) => {
  const n = typeof v === "string" ? Number(v) : v;
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
};

/** mm:ss from an audio offset in ms. */
export const mmss = (ms: number | null | undefined) => {
  if (ms == null) return "--:--";
  const total = Math.max(0, Math.round(ms / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
};

/** "1m 12s" from a phase duration in ms. */
export const held = (ms: number | null | undefined) => {
  if (ms == null) return null;
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${String(s % 60).padStart(2, "0")}s`;
};

export const clockLabel = (remainingMs: number) => {
  const over = remainingMs < 0;
  const t = Math.abs(remainingMs);
  const d = Math.floor(t / 86_400_000);
  const h = Math.floor((t % 86_400_000) / 3_600_000);
  const m = Math.floor((t % 3_600_000) / 60_000);
  const s = Math.floor((t % 60_000) / 1000);
  const core = `${d > 0 ? `${d}d ` : ""}${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return over ? `-${core}` : core;
};

export const shortHash = (h: string | null | undefined) =>
  h ? (h.length > 12 ? `${h.slice(0, 12)}…` : h) : "—";

export const timeOfDay = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      })
    : "--:--:--";

export const asNumber = (v: unknown): number | null => {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isNaN(n) ? null : n;
};

export const asText = (v: unknown): string | null =>
  v == null ? null : typeof v === "string" ? v : String(v);

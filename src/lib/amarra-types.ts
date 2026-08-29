export type CallStatus = "dialing" | "live" | "escalated" | "done" | "released";
export type PolicyDecision = "allow" | "deny" | "block" | "escalate";
export type AuctionState = "pending" | "running" | "settled" | "cancelled";
export type CommitmentState = "proposed" | "anchored" | "void";
export type EscalationState = "open" | "approved" | "rejected";

export interface Operation {
  id: string;
  ref: string;
  container: string;
  origin: string;
  destination: string;
  free_time_ends: string;
  demurrage_per_day: number;
  created_at: string;
}

export interface Mandate {
  id: string;
  operation_id: string;
  target_amount: number;
  max_amount: number;
  currency: string;
  pickup_window_start: string | null;
  pickup_window_end: string | null;
}

export interface Auction {
  id: string;
  operation_id: string;
  state: AuctionState;
  started_at: string | null;
  settled_at: string | null;
  winner_call_id: string | null;
  created_at: string;
}

export interface Call {
  id: string;
  auction_id: string;
  carrier_name: string;
  carrier_phone: string | null;
  status: CallStatus;
  final_ask: number | null;
  rounds: number;
  is_winner: boolean;
  outcome_reason: string | null;
  recording_url: string | null;
  released_at: string | null;
  created_at: string;
}

export interface Utterance {
  id: string;
  call_id: string;
  speaker: string;
  text: string;
  interrupted: boolean;
  t_start_ms: number | null;
  t_end_ms: number | null;
  created_at: string;
}

export interface PolicyEvent {
  id: string;
  call_id: string;
  ask: string;
  decision: PolicyDecision;
  reason: string | null;
  created_at: string;
}

export interface Commitment {
  id: string;
  call_id: string;
  field: string;
  value: string;
  state: CommitmentState;
  quote: string | null;
  t_start_ms: number | null;
  t_end_ms: number | null;
  created_at: string;
}

export interface EscalationComputation {
  option_on_time?: { label?: string; amount?: number; eta?: string };
  option_late?: { label?: string; amount?: number; demurrage?: number; eta?: string };
  delta?: number;
  exceeds_mandate_by?: number;
  [key: string]: unknown;
}

export interface Escalation {
  id: string;
  call_id: string;
  brief: string;
  computation: EscalationComputation;
  state: EscalationState;
  created_at: string;
}

export const money = (v: number | null | undefined, currency = "USD") =>
  v == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(v);

export const msWindow = (start: number | null, end: number | null) => {
  const fmt = (ms: number) => {
    const total = Math.max(0, Math.round(ms / 1000));
    return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
  };
  if (start == null) return null;
  return `[${fmt(start)}–${end == null ? "--:--" : fmt(end)}]`;
};

import { useEffect, useRef } from "react";
import {
  mmss,
  money,
  num,
  timeOfDay,
  type Call,
  type PolicyEvent,
  type ReadBack,
  type Utterance,
} from "@/lib/amarra-types";

const STATUS_TONE: Record<string, string> = {
  dialing: "border-warn text-warn",
  live: "border-live text-live phase-pulse",
  escalated: "border-danger text-danger phase-pulse",
  done: "border-border text-muted-foreground",
  released: "border-border text-muted-foreground",
  failed: "border-danger text-danger",
};

const DECISION_TONE: Record<string, string> = {
  allow: "border-live/60 bg-live/10 text-live",
  deny: "border-warn/70 bg-warn/10 text-warn",
  block: "border-danger bg-danger/15 text-danger",
  escalate: "border-danger bg-danger/15 text-danger",
};

const SPEAKER_TONE: Record<string, string> = {
  agent: "text-accent",
  counterparty: "text-foreground",
  human: "text-warn",
};

export function CallColumn({
  call,
  utterances,
  policyEvents,
  readBacks,
  currency,
  isWinner,
}: {
  call: Call;
  utterances: Utterance[];
  policyEvents: PolicyEvent[];
  readBacks: ReadBack[];
  currency: string;
  isWinner: boolean;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [utterances.length]);

  const lastPolicy = policyEvents[policyEvents.length - 1] ?? null;
  const lastRound = policyEvents.reduce((m, p) => Math.max(m, p.round ?? 0), 0);

  return (
    <div
      className={`panel flex min-h-0 flex-col rounded-md border-2 ${isWinner ? "border-live" : "border-border"}`}
    >
      <div className="border-b border-border px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="num text-lg font-bold">{call.carrier_name ?? call.carrier_id ?? "—"}</div>
          <span
            className={`num rounded border px-2 py-0.5 text-xs font-bold uppercase ${STATUS_TONE[call.status] ?? "border-border"}`}
          >
            {call.status}
          </span>
        </div>
        <div className="num flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          <span>{call.phone ?? "no number"}</span>
          <span>{call.leg_role ?? "counterparty"}</span>
          <span>{call.language ?? "—"}</span>
          <span>attempt {call.dial_attempt ?? 1}</span>
          {call.answered_at && <span>answered {timeOfDay(call.answered_at)}</span>}
          {lastRound > 0 && <span>round {lastRound}</span>}
          {call.transcript_words != null && <span>{num(call.transcript_words)} words</span>}
          {isWinner && <span className="font-bold text-live">WINNER</span>}
        </div>
        {call.dial_error && (
          <div className="num mt-1 text-xs text-danger">dial error: {call.dial_error}</div>
        )}
      </div>

      <div ref={scroller} className="min-h-[12rem] flex-1 overflow-y-auto px-3 py-2">
        {utterances.length === 0 ? (
          <div className="num text-sm text-muted-foreground">nothing said yet</div>
        ) : (
          <ul className="space-y-1.5">
            {utterances.map((u) => (
              <li key={String(u.id)} className="row-in text-sm leading-snug">
                <span className="num mr-2 text-xs text-muted-foreground">{mmss(u.t_ms)}</span>
                <span
                  className={`num mr-1 text-xs font-bold uppercase ${SPEAKER_TONE[u.speaker] ?? ""}`}
                >
                  {u.speaker}
                </span>
                <span className={u.interrupted ? "italic opacity-70" : ""}>{u.text}</span>
                {u.interrupted && <span className="num ml-1 text-xs text-warn">[cut off]</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      {readBacks.length > 0 && (
        <div className="border-t border-border px-3 py-1.5">
          <div className="label-caps">read-back</div>
          {readBacks.slice(-2).map((r) => (
            <div key={String(r.id)} className="num text-xs">
              <span className="text-muted-foreground">#{r.attempt}</span>{" "}
              <span
                className={
                  r.outcome === "confirmed"
                    ? "font-bold text-live"
                    : r.outcome === "rejected"
                      ? "font-bold text-danger"
                      : "text-warn"
                }
              >
                {r.outcome ?? "awaiting"}
              </span>{" "}
              <span className="text-muted-foreground">{r.token}</span>
            </div>
          ))}
        </div>
      )}

      <div className="border-t border-border px-3 py-2">
        <div className="label-caps">policy strip</div>
        {policyEvents.length === 0 ? (
          <div className="num text-xs text-muted-foreground">no decision yet</div>
        ) : (
          <div className="flex flex-wrap gap-1">
            {policyEvents.slice(-8).map((p) => (
              <span
                key={String(p.id)}
                title={`${p.reason ?? ""} ${p.utterance ?? ""}`}
                className={`num rounded border px-1.5 py-0.5 text-[0.7rem] font-bold uppercase ${DECISION_TONE[p.decision] ?? "border-border"}`}
              >
                {p.decision}
                {p.counterparty_ask != null && ` ${money(p.counterparty_ask, currency)}`}
              </span>
            ))}
          </div>
        )}
        {lastPolicy && (
          <div className="num mt-1 text-xs text-muted-foreground">
            {lastPolicy.reason ?? "—"}
            {lastPolicy.amount != null && ` → authorized ${money(lastPolicy.amount, currency)}`}
          </div>
        )}
      </div>
    </div>
  );
}

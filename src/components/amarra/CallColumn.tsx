import { useEffect, useRef } from "react";
import type { Call, PolicyEvent, Utterance } from "@/lib/amarra-types";

const statusTone: Record<Call["status"], string> = {
  dialing: "border-info text-info",
  live: "border-live text-live",
  escalated: "border-warn text-warn",
  done: "border-grid text-muted-foreground",
  released: "border-grid text-muted-foreground",
};

const decisionTone: Record<PolicyEvent["decision"], string> = {
  allow: "text-live",
  deny: "text-warn",
  block: "text-danger",
  escalate: "text-info",
};

export function CallColumn({
  call,
  utterances,
  policyEvents,
  released,
}: {
  call: Call;
  utterances: Utterance[];
  policyEvents: PolicyEvent[];
  released: boolean;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [utterances.length]);

  return (
    <section
      className={`panel enter-row relative flex min-h-0 flex-col rounded-lg transition-opacity duration-500 ${
        released ? "opacity-40" : "opacity-100"
      }`}
    >
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="text-2xl leading-tight font-bold tracking-wide uppercase">
            {call.carrier_name}
          </div>
          <div className="num text-sm text-muted-foreground">{call.carrier_phone ?? "no number"}</div>
        </div>
        <div
          className={`num flex items-center gap-2 rounded-full border-2 px-3 py-1 text-sm font-bold uppercase ${statusTone[call.status]}`}
        >
          {call.status === "live" && (
            <span className="pulse-dot inline-block size-2.5 rounded-full bg-live" />
          )}
          {call.status}
        </div>
      </div>

      {released && (
        <div className="pointer-events-none absolute top-1/2 left-1/2 z-10 -translate-x-1/2 -translate-y-1/2 -rotate-12 rounded border-4 border-danger px-6 py-2">
          <span className="num text-3xl font-bold tracking-widest text-danger uppercase">
            released
          </span>
        </div>
      )}

      <div ref={scroller} className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {utterances.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Live transcript appears here as the agent speaks.
          </p>
        ) : (
          utterances.map((u) => {
            const agent = u.speaker === "agent";
            return (
              <div
                key={u.id}
                className={`enter-row rounded-md px-3 py-2 text-[0.95rem] leading-snug ${
                  agent
                    ? "border-l-4 border-agent bg-panel-2 text-foreground"
                    : "border-l-4 border-primary bg-background text-foreground"
                }`}
              >
                <div className="label-caps flex items-center gap-2">
                  <span className={agent ? "text-agent" : "text-primary"}>
                    {agent ? "agent" : call.carrier_name}
                  </span>
                  {u.interrupted && (
                    <span className="num rounded bg-danger/25 px-1.5 text-[0.65rem] text-danger">
                      interrupted
                    </span>
                  )}
                </div>
                <p className="mt-0.5">{u.text}</p>
              </div>
            );
          })
        )}
      </div>

      <div className="border-t border-border bg-background/60 px-4 py-2">
        <div className="label-caps mb-1">policy</div>
        {policyEvents.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Policy decisions stream here per ask.
          </p>
        ) : (
          <ul className="max-h-32 space-y-0.5 overflow-y-auto">
            {policyEvents.map((p) => (
              <li
                key={p.id}
                title={p.reason ?? "no reason given"}
                className="num enter-row cursor-help truncate text-xs"
              >
                <span className="text-muted-foreground">{p.ask}</span>
                <span className="text-grid"> → </span>
                <span className={`font-bold uppercase ${decisionTone[p.decision]}`}>
                  {p.decision}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

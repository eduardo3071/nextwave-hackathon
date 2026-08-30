import { BRANCHES, held, timeOfDay, type PhaseEvent } from "@/lib/amarra-types";

const TONE: Record<string, string> = {
  disrupted: "text-warn",
  renegotiating: "text-accent",
  escalated: "text-danger",
  resolved: "text-live",
  failed: "text-danger",
  closed: "text-live",
};

export function PhaseTimeline({ events }: { events: PhaseEvent[] }) {
  const rows = [...events].reverse();
  return (
    <section className="panel flex min-h-0 flex-col rounded-md">
      <div className="border-b border-border px-3 py-2">
        <div className="label-caps">timeline · phase_events</div>
      </div>
      {rows.length === 0 ? (
        <div className="num px-3 py-4 text-sm text-muted-foreground">
          no transition recorded
        </div>
      ) : (
        <ul className="max-h-[22rem] divide-y divide-border overflow-y-auto">
          {rows.map((e) => {
            const branch = (BRANCHES as string[]).includes(e.phase);
            return (
              <li key={String(e.id)} className="row-in px-3 py-1.5">
                <div className="flex items-baseline justify-between gap-2">
                  <span
                    className={`text-sm font-bold tracking-wide uppercase ${TONE[e.phase] ?? (branch ? "text-warn" : "text-foreground")}`}
                  >
                    {e.phase.replace(/_/g, " ")}
                  </span>
                  <span className="num text-xs text-muted-foreground">
                    {timeOfDay(e.created_at)}
                  </span>
                </div>
                <div className="num text-xs text-muted-foreground opacity-70">{e.trigger}</div>
                {e.detail && <div className="text-xs leading-snug">{e.detail}</div>}
                {e.ms_in_previous != null && (
                  <div className="num text-[0.7rem] text-muted-foreground">
                    {e.previous ?? "—"} lasted {held(e.ms_in_previous)}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

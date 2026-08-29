import {
  BRANCHES,
  SPINE,
  SPINE_LABEL,
  asNumber,
  held,
  isBranch,
  money,
  type BranchPhase,
  type Operation,
  type Phase,
  type PhaseEvent,
} from "@/lib/amarra-types";

const BRANCH_TONE: Record<BranchPhase, { border: string; text: string; bg: string }> = {
  disrupted: { border: "border-warn", text: "text-warn", bg: "bg-warn/10" },
  renegotiating: { border: "border-accent", text: "text-accent", bg: "bg-accent/10" },
  escalated: { border: "border-danger phase-pulse", text: "text-danger", bg: "bg-danger/15" },
  resolved: { border: "border-live", text: "text-live", bg: "bg-live/10" },
};

/**
 * The spine is rendered from the database only. The last spine phase reached
 * comes from phase_events, so a branch never rewinds or advances it.
 */
export function PhaseRail({
  operation,
  phaseEvents,
  onOpenEscalation,
}: {
  operation: Operation | null;
  phaseEvents: PhaseEvent[];
  onOpenEscalation?: (() => void) | undefined;
}) {
  const phase: Phase | null = operation?.phase ?? null;
  const failed = phase === "failed";

  const spineEvents = phaseEvents.filter((e) => (SPINE as string[]).includes(e.phase));
  const lastSpine = spineEvents.length ? (spineEvents[spineEvents.length - 1]!.phase as Phase) : null;
  const anchorPhase =
    phase && (SPINE as string[]).includes(phase) ? phase : (lastSpine ?? (phase ? null : null));
  const anchorIndex = anchorPhase ? SPINE.indexOf(anchorPhase as never) : -1;

  const branchPhase = isBranch(phase) ? phase : null;
  const branchEvent = branchPhase
    ? [...phaseEvents].reverse().find((e) => e.phase === branchPhase)
    : null;
  const pastBranches = phaseEvents.filter((e) => (BRANCHES as string[]).includes(e.phase));

  const currentEvent = [...phaseEvents].reverse().find((e) => e.phase === phase) ?? null;
  const failedEvent = failed ? [...phaseEvents].reverse().find((e) => e.phase === "failed") : null;

  const durationOf = (step: string) => {
    // ms_in_previous on the event that LEFT this step is how long it was held.
    const leaving = phaseEvents.find((e) => e.previous === step && e.ms_in_previous != null);
    return held(leaving?.ms_in_previous ?? null);
  };

  const branchMarkersOn = (step: string) => {
    const idx = SPINE.indexOf(step as never);
    return pastBranches.filter((b) => {
      if (branchPhase && b.phase === branchPhase) return false;
      const prevIdx = b.previous ? SPINE.indexOf(b.previous as never) : -1;
      return prevIdx === idx;
    });
  };

  const empty = phaseEvents.length === 0 && !operation;

  return (
    <section className="border-b border-border bg-card/40 px-5 py-3">
      <div className="flex items-stretch gap-1">
        {SPINE.map((step, i) => {
          const done = anchorIndex > i || (anchorIndex === i && step === "closed" && !branchPhase);
          const current = anchorIndex === i;
          const closedAll = phase === "closed";
          const tone = failed && current
            ? "border-danger bg-danger/20 text-danger"
            : closedAll
              ? "border-live bg-live/20 text-live"
              : done
                ? "border-live/70 bg-live/12 text-live"
                : current
                  ? `border-accent bg-accent/12 text-accent ${branchPhase ? "" : "phase-pulse"} scale-[1.03]`
                  : "border-border bg-transparent text-muted-foreground";
          const duration = durationOf(step);
          const markers = branchMarkersOn(step);
          return (
            <div key={step} className="flex flex-1 flex-col">
              <div
                className={`flex min-h-[3rem] flex-col items-center justify-center rounded-md border-2 px-2 py-1 transition-all ${tone} ${empty ? "opacity-40" : ""}`}
              >
                <span
                  className={`text-center text-[0.72rem] leading-tight font-bold tracking-wider uppercase ${current ? "text-sm" : ""}`}
                >
                  {SPINE_LABEL[step]}
                </span>
                {duration && <span className="num text-[0.7rem] opacity-80">{duration}</span>}
              </div>
              <div
                className={`mt-1 h-1 rounded ${done || (current && phase === "closed") ? "bg-live" : current ? "bg-accent" : "bg-border"}`}
              />
              <div className="mt-1 flex justify-center gap-1">
                {markers.map((m) => {
                  const t = BRANCH_TONE[m.phase as BranchPhase];
                  return (
                    <span
                      key={String(m.id)}
                      title={`${m.phase} · ${m.trigger}${m.detail ? ` · ${m.detail}` : ""}`}
                      className={`num rounded border px-1 text-[0.6rem] ${t?.border ?? "border-border"} ${t?.text ?? ""}`}
                    >
                      {m.phase.slice(0, 3)}
                    </span>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="num mt-2 truncate text-sm text-muted-foreground">
        {empty
          ? "aguardando uma operação"
          : failedEvent
            ? `falhou · ${failedEvent.detail ?? failedEvent.trigger}`
            : (currentEvent?.detail ?? currentEvent?.trigger ?? "—")}
      </div>

      {branchPhase && branchEvent && (
        <BranchCard
          event={branchEvent}
          phase={branchPhase}
          currency={operation?.currency ?? "MXN"}
          onOpenEscalation={onOpenEscalation}
        />
      )}
    </section>
  );
}

function BranchCard({
  event,
  phase,
  currency,
  onOpenEscalation,
}: {
  event: PhaseEvent;
  phase: BranchPhase;
  currency: string;
  onOpenEscalation?: () => void;
}) {
  const t = BRANCH_TONE[phase];
  const payload = event.payload ?? {};
  const onTime = payload["option_on_time"] as Record<string, unknown> | undefined;
  const late = payload["option_late"] as Record<string, unknown> | undefined;
  const delta = asNumber(payload["delta"]);
  const exceeds = asNumber(payload["exceeds_mandate_by"]);

  return (
    <div className={`mt-3 rounded-md border-2 ${t.border} ${t.bg} px-4 py-3`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className={`label-caps ${t.text}`}>desvio · {phase}</div>
          <div className="text-lg font-bold">{event.detail ?? event.trigger}</div>
          <div className="num text-xs text-muted-foreground">{event.trigger}</div>
        </div>
        {phase === "escalated" && onOpenEscalation && (
          <button
            type="button"
            onClick={onOpenEscalation}
            className="rounded border-2 border-danger px-3 py-1.5 text-sm font-bold tracking-wide uppercase text-danger hover:bg-danger/20"
          >
            abrir decisão
          </button>
        )}
      </div>

      {(onTime || late) && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Option label="no prazo" data={onTime} currency={currency} tone="border-live" />
          <Option label="atrasado" data={late} currency={currency} tone="border-warn" />
        </div>
      )}
      {delta != null && (
        <div className="num mt-2 text-sm">
          delta: <span className="font-bold">{money(delta, currency)}</span>
        </div>
      )}
      {exceeds != null && exceeds > 0 && (
        <div className="num mt-1 text-base font-bold text-danger">
          excede o mandato em {money(exceeds, currency)}
        </div>
      )}
    </div>
  );
}

function Option({
  label,
  data,
  currency,
  tone,
}: {
  label: string;
  data: Record<string, unknown> | undefined;
  currency: string;
  tone: string;
}) {
  if (!data) return null;
  const amount = asNumber(data["amount"]);
  const demurrage = asNumber(data["demurrage"]);
  const total = asNumber(data["total"]) ?? (amount ?? 0) + (demurrage ?? 0);
  return (
    <div className={`rounded border ${tone} bg-background/50 px-3 py-2`}>
      <div className="label-caps">{String(data["label"] ?? label)}</div>
      <div className="num text-sm">frete: {money(amount, currency)}</div>
      <div className="num text-sm">demurrage: {money(demurrage ?? 0, currency)}</div>
      <div className="num text-base font-bold">total: {money(total, currency)}</div>
      {data["eta"] != null && (
        <div className="num text-xs text-muted-foreground">eta: {String(data["eta"])}</div>
      )}
    </div>
  );
}

import { SPINE, SPINE_LABEL, isBranch, type Operation, type Phase, type PhaseEvent } from "@/lib/amarra-types";

const BRANCH_TONE: Record<string, string> = {
  disrupted: "border-warn/60 bg-warn/10 text-warn",
  renegotiating: "border-accent/60 bg-accent/10 text-accent",
  escalated: "border-danger/70 bg-danger/15 text-danger phase-pulse",
  resolved: "border-live/60 bg-live/10 text-live",
  failed: "border-danger/70 bg-danger/15 text-danger",
};

/** Compact phase indicator: step counter, segmented bar, current detail line. */
export function MobilePhaseStrip({
  operation,
  phaseEvents,
  onOpenEscalation,
}: {
  operation: Operation | null;
  phaseEvents: PhaseEvent[];
  onOpenEscalation?: (() => void) | undefined;
}) {
  const phase: Phase | null = operation?.phase ?? null;
  const spineEvents = phaseEvents.filter((e) => (SPINE as string[]).includes(e.phase));
  const lastSpine = spineEvents.length ? (spineEvents[spineEvents.length - 1]!.phase as Phase) : null;
  const anchor = phase && (SPINE as string[]).includes(phase) ? phase : lastSpine;
  const index = anchor ? SPINE.indexOf(anchor as never) : -1;
  const branch = isBranch(phase) || phase === "failed" ? phase : null;
  const current = [...phaseEvents].reverse().find((e) => e.phase === phase) ?? null;

  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="label-caps text-[0.6rem]">phase</div>
          <div className="truncate text-lg leading-tight font-bold">
            {anchor ? SPINE_LABEL[anchor as never] : "waiting for operation"}
          </div>
        </div>
        <div className="num shrink-0 text-sm text-muted-foreground">
          {index >= 0 ? `${index + 1}/${SPINE.length}` : `—/${SPINE.length}`}
        </div>
      </div>

      <div className="flex gap-1">
        {SPINE.map((step, i) => (
          <span
            key={step}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              i < index
                ? "bg-live/80"
                : i === index
                  ? `bg-accent ${branch ? "" : "phase-pulse"}`
                  : "bg-border"
            }`}
          />
        ))}
      </div>

      {current?.detail || current?.trigger ? (
        <div className="num truncate text-[11px] text-muted-foreground">
          {current.detail ?? current.trigger}
        </div>
      ) : null}

      {branch && (
        <button
          type="button"
          onClick={branch === "escalated" ? onOpenEscalation : undefined}
          className={`w-full rounded-xl border px-3 py-2 text-left ${BRANCH_TONE[branch] ?? "border-border"}`}
        >
          <div className="label-caps text-[0.6rem]">detour · {branch}</div>
          <div className="text-sm font-bold">
            {[...phaseEvents].reverse().find((e) => e.phase === branch)?.detail ??
              "awaiting decision"}
          </div>
        </button>
      )}
    </section>
  );
}

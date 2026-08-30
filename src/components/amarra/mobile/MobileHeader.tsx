import { useEffect, useState } from "react";
import {
  clockLabel,
  money,
  shortHash,
  type ClockState,
  type Mandate,
  type Operation,
} from "@/lib/amarra-types";

const TONE: Record<ClockState, string> = {
  safe: "text-live",
  warning: "text-warn",
  critical: "text-danger phase-pulse",
  expired: "text-danger",
  stopped: "text-muted-foreground",
};

function useNow(active: boolean) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

function Chip({
  label,
  value,
  tone = "",
  strong = false,
}: {
  label: string;
  value: string;
  tone?: string;
  strong?: boolean;
}) {
  return (
    <div
      className={`shrink-0 rounded-xl border px-3 py-2 ${
        strong ? "border-danger/70 bg-danger/10" : "border-border bg-card/70"
      }`}
    >
      <div className="label-caps text-[0.6rem] leading-none">{label}</div>
      <div className={`num mt-1 text-base leading-none font-bold ${tone}`}>{value}</div>
    </div>
  );
}

/** Mobile header: identity, one big clock, and the mandate as a swipe rail. */
export function MobileHeader({
  operation,
  mandate,
  policyBlocks,
  anchored,
  hasDossier,
  onOpenDossier,
}: {
  operation: Operation | null;
  mandate: Mandate | null;
  policyBlocks: number;
  anchored: number;
  hasDossier: boolean;
  onOpenDossier: () => void;
}) {
  const frozen = !operation || operation.clock_state === "stopped" || !!operation.closed_at;
  const now = useNow(!frozen);
  const currency = operation?.currency ?? "MXN";

  const target = operation ? new Date(operation.free_time_ends).getTime() : null;
  const reference = operation
    ? frozen
      ? new Date(operation.closed_at ?? Date.now()).getTime()
      : now
    : null;
  const remaining = target != null && reference != null ? target - reference : null;
  const tone = operation ? (TONE[operation.clock_state] ?? "text-foreground") : "text-muted-foreground";

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur-xl">
      <div className="mx-auto w-full max-w-[430px] px-4 pt-3 pb-3">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
          <div className="min-w-0">
            <div className="num truncate text-sm font-bold tracking-wide text-accent">
              {operation?.ref ?? "sem operação"}
            </div>
            <div className="num truncate text-[11px] text-muted-foreground">
              {operation
                ? [operation.container, operation.origin && `${operation.origin} → ${operation.destination}`]
                    .filter(Boolean)
                    .join(" · ")
                : "aguardando descarga"}
            </div>
          </div>
          {hasDossier && (
            <button
              type="button"
              onClick={onOpenDossier}
              className="shrink-0 rounded-full border border-live px-3 py-1.5 text-[11px] font-bold tracking-wide text-live uppercase"
            >
              dossiê
            </button>
          )}
        </div>

        <div className="mt-3 flex flex-col items-center">
          <span className="label-caps text-[0.6rem]">
            {!operation
              ? "free time"
              : frozen
                ? `encerrada · ${operation.clock_state}`
                : remaining != null && remaining < 0
                  ? "demurrage correndo"
                  : "free time restante"}
          </span>
          <span
            className={`num text-[3.25rem] leading-[1.05] font-bold tracking-tight ${tone}`}
            aria-live="polite"
          >
            {remaining == null ? "--:--:--" : clockLabel(remaining)}
          </span>
          {operation && (
            <span className="num text-[11px] text-muted-foreground">
              depois:{" "}
              <span className="font-bold text-danger">
                {money(operation.demurrage_per_day, currency)}/dia
              </span>
            </span>
          )}
        </div>

        <div className="-mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {mandate ? (
            <>
              <Chip label="target" value={money(mandate.target_rate, currency)} tone="text-live" />
              <Chip label="teto" value={money(mandate.max_rate, currency)} tone="text-danger" strong />
              <Chip
                label="break-even"
                value={money(mandate.break_even_rate, currency)}
                tone="text-warn"
              />
              <Chip label="hash" value={shortHash(mandate.mandate_hash)} tone="text-accent" />
              <Chip label="blocks" value={String(policyBlocks)} tone="text-danger" />
              <Chip label="ancorados" value={String(anchored)} tone="text-live" />
            </>
          ) : (
            <div className="num rounded-xl border border-border bg-card/70 px-3 py-2 text-[11px] text-muted-foreground">
              mandato ainda não emitido
            </div>
          )}
        </div>

        {mandate?.issue_warnings?.length ? (
          <div className="num mt-2 rounded-lg border border-warn/40 bg-warn/10 px-3 py-1.5 text-[11px] text-warn">
            {mandate.issue_warnings.join(" · ")}
          </div>
        ) : null}
      </div>
    </header>
  );
}

import { useEffect, useRef, useState } from "react";
import {
  clockLabel,
  money,
  shortHash,
  type ClockState,
  type Mandate,
  type Operation,
} from "@/lib/amarra-types";

const CLOCK_TONE: Record<ClockState, string> = {
  safe: "text-live",
  warning: "text-warn",
  critical: "text-danger animate-[amarra-pulse_1s_ease-in-out_infinite]",
  expired: "text-danger",
  stopped: "text-muted-foreground",
};

function useTick(active: boolean) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

function Countdown({ operation }: { operation: Operation }) {
  const frozen = operation.clock_state === "stopped" || !!operation.closed_at;
  const now = useTick(!frozen);
  const target = new Date(operation.free_time_ends).getTime();
  const currency = operation.currency ?? "MXN";

  // Frozen clocks read from closed_at so the number stops moving on stage.
  const reference = frozen ? new Date(operation.closed_at ?? Date.now()).getTime() : now;
  const remaining = reference == null ? null : target - reference;
  const tone = CLOCK_TONE[operation.clock_state] ?? "text-foreground";

  const spare =
    frozen && remaining != null && remaining > 0
      ? `${Math.floor(remaining / 3_600_000)}h de folga`
      : null;

  return (
    <div className="flex flex-col items-center">
      <span className="label-caps">
        {frozen
          ? `encerrada · ${operation.clock_state}`
          : remaining != null && remaining < 0
            ? "demurrage correndo"
            : "free time restante"}
      </span>
      <span className={`num text-6xl leading-none font-bold xl:text-8xl ${tone}`} aria-live="polite">
        {remaining == null ? "--:--:--" : clockLabel(remaining)}
      </span>
      {spare ? (
        <span className="num mt-1 text-lg font-bold text-live">fechada com {spare}</span>
      ) : (
        <span className="num mt-1 text-base text-foreground">
          após esse prazo:{" "}
          <span className="font-bold text-danger">
            {money(operation.demurrage_per_day, currency)}/dia
          </span>{" "}
          de demurrage
        </span>
      )}
    </div>
  );
}

function Counter({
  label,
  value,
  flashOnIncrement,
  tone,
}: {
  label: string;
  value: number;
  flashOnIncrement?: boolean;
  tone?: string;
}) {
  const prev = useRef(value);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (flashOnIncrement && value > prev.current) {
      setFlash(true);
      const id = window.setTimeout(() => setFlash(false), 2200);
      prev.current = value;
      return () => window.clearTimeout(id);
    }
    prev.current = value;
    return undefined;
  }, [value, flashOnIncrement]);

  return (
    <div className="panel min-w-[8rem] rounded-md px-3 py-2 text-center">
      <div className="label-caps">{label}</div>
      <div
        className={`num text-4xl leading-none font-bold ${tone ?? ""} ${flash ? "flash-danger rounded" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}

export function TopBar({
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
  const currency = operation?.currency ?? "MXN";
  const win = (v: string | null | undefined) =>
    v
      ? new Date(v).toLocaleString(undefined, {
          month: "short",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "—";

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/97 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-3">
        <div className="min-w-[16rem]">
          <div className="label-caps">operação</div>
          <div className="num text-2xl font-bold text-accent">
            {operation?.ref ?? "nenhuma operação"}
          </div>
          <div className="num text-sm text-muted-foreground">
            {operation
              ? [operation.container, operation.origin && `${operation.origin} → ${operation.destination}`]
                  .filter(Boolean)
                  .join(" · ")
              : "aguardando uma linha em operations"}
          </div>
          {hasDossier && (
            <button
              type="button"
              onClick={onOpenDossier}
              className="mt-1 rounded border border-live px-2 py-0.5 text-xs font-bold tracking-wide text-live uppercase hover:bg-live/15"
            >
              ver dossiê
            </button>
          )}
        </div>

        {operation ? (
          <Countdown operation={operation} />
        ) : (
          <div className="num text-6xl font-bold text-muted-foreground">--:--:--</div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {mandate ? (
            <>
              <div className="panel rounded-md px-3 py-2">
                <div className="label-caps">target</div>
                <div className="num text-2xl font-bold text-live">
                  {money(mandate.target_rate, currency)}
                </div>
              </div>
              <div className="rounded-md border-2 border-danger bg-danger/15 px-3 py-2">
                <div className="label-caps text-danger">max · teto duro</div>
                <div className="num text-2xl font-bold text-danger">
                  {money(mandate.max_rate, currency)}
                </div>
              </div>
              <div className="panel rounded-md px-3 py-2">
                <div className="label-caps">break-even</div>
                <div className="num text-lg font-bold text-warn">
                  {money(mandate.break_even_rate, currency)}
                </div>
              </div>
              <div className="panel rounded-md px-3 py-2">
                <div className="label-caps">janela de coleta</div>
                <div className="num text-sm font-semibold">
                  {win(mandate.pickup_from)} → {win(mandate.pickup_to)}
                </div>
              </div>
              <div className="panel rounded-md px-3 py-2">
                <div className="label-caps">mandate hash</div>
                <div className="num text-sm font-semibold text-accent">
                  {shortHash(mandate.mandate_hash)}
                </div>
              </div>
            </>
          ) : (
            <div className="panel rounded-md px-3 py-2 text-sm text-muted-foreground">
              os chips do mandato aparecem quando o mandato é emitido
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Counter label="policy blocks" value={policyBlocks} flashOnIncrement tone="text-danger" />
          <Counter label="ancorados no áudio" value={anchored} tone="text-live" />
        </div>
      </div>

      {mandate?.issue_warnings?.length ? (
        <div className="num border-t border-warn/40 bg-warn/10 px-5 py-1 text-xs text-warn">
          avisos na emissão: {mandate.issue_warnings.join(" · ")}
        </div>
      ) : null}
    </header>
  );
}

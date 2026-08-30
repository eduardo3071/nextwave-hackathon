import { useState } from "react";
import type { Auction, Operation, Phase } from "@/lib/amarra-types";

type Action = {
  label: string;
  path: string;
  ok: string;
  tone: "live" | "accent" | "warn" | "danger";
};

const TONE: Record<Action["tone"], string> = {
  live: "border-live bg-live/15 text-live",
  accent: "border-accent bg-accent/12 text-accent",
  warn: "border-warn bg-warn/12 text-warn",
  danger: "border-danger bg-danger/12 text-danger",
};

/** One primary action for the current phase; everything else behind "mais". */
export function MobileActions({
  operation,
  auction,
  phase,
  ready,
  onRun,
}: {
  operation: Operation | null;
  auction: Auction | null;
  phase: Phase | null;
  ready: boolean;
  onRun: (path: string, ok: string) => void;
}) {
  const [sheet, setSheet] = useState(false);

  const actions: Action[] = [];
  if (operation && phase === "detected")
    actions.push({
      label: "issue mandate",
      path: `/phase2/issue/${operation.id}`,
      ok: "Mandate issued",
      tone: "live",
    });
  if (auction && (phase === "market_open" || phase === "negotiating"))
    actions.push({
      label: "abort auction",
      path: `/phase3/abort/${auction.id}`,
      ok: "Auction aborted",
      tone: "warn",
    });
  if (auction && phase === "reserved")
    actions.push({
      label: "release reservation",
      path: `/phase5/release/${auction.id}`,
      ok: "Reservation released",
      tone: "warn",
    });
  if (operation && phase === "verified")
    actions.push({
      label: "close operation",
      path: `/phase8/close/${operation.id}`,
      ok: "Operation closed",
      tone: "live",
    });
  if (operation && (phase === "closed" || phase === "failed"))
    actions.push({
      label: "reopen",
      path: `/phase8/reopen/${operation.id}`,
      ok: "Operation reopened",
      tone: "accent",
    });
  if (operation && phase !== "closed" && phase !== "failed")
    actions.push({
      label: "fail manually",
      path: `/phase8/fail/${operation.id}`,
      ok: "Operation marked as failed",
      tone: "danger",
    });

  const primary = actions[0];
  const rest = actions.slice(1);

  return (
    <>
      <div className="sticky bottom-0 z-30 border-t border-border bg-background/95 px-4 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-[430px] items-center gap-2">
          {primary ? (
            <button
              type="button"
              onClick={() => onRun(primary.path, primary.ok)}
              className={`num min-h-[52px] flex-1 rounded-full border-2 text-sm font-bold tracking-wide uppercase ${TONE[primary.tone]}`}
            >
              {primary.label}
            </button>
          ) : (
            <div className="num min-h-[52px] flex-1 rounded-full border border-border bg-card/60 px-4 text-center text-xs leading-[52px] text-muted-foreground">
              {ready ? `phase ${phase ?? "—"} · nothing to decide` : "connecting…"}
            </div>
          )}
          {rest.length > 0 && (
            <button
              type="button"
              onClick={() => setSheet(true)}
              className="num min-h-[52px] shrink-0 rounded-full border border-border px-4 text-xs font-bold text-muted-foreground uppercase"
            >
              more
            </button>
          )}
        </div>
      </div>

      {sheet && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end bg-background/70">
          <button type="button" aria-label="close" className="flex-1" onClick={() => setSheet(false)} />
          <div className="rounded-t-3xl border-t border-border bg-card px-5 pt-3 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
            <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-border" />
            <div className="space-y-2">
              {rest.map((a) => (
                <button
                  key={a.path}
                  type="button"
                  onClick={() => {
                    onRun(a.path, a.ok);
                    setSheet(false);
                  }}
                  className={`num min-h-[52px] w-full rounded-full border-2 text-sm font-bold tracking-wide uppercase ${TONE[a.tone]}`}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

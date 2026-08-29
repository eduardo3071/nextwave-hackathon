import { useEffect, useRef, useState } from "react";
import { money, type Mandate, type Operation } from "@/lib/amarra-types";

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

function Countdown({ operation }: { operation: Operation }) {
  const now = useNow(true);
  const target = new Date(operation.free_time_ends).getTime();
  const remaining = now == null ? null : target - now;

  const hours = remaining == null ? null : remaining / 3_600_000;
  const tone =
    hours == null
      ? "text-foreground"
      : hours <= 0
        ? "text-danger"
        : hours < 2
          ? "text-danger"
          : hours < 6
            ? "text-warn"
            : "text-live";

  const label = (() => {
    if (remaining == null) return "--:--:--";
    const over = remaining < 0;
    const t = Math.abs(remaining);
    const d = Math.floor(t / 86_400_000);
    const h = Math.floor((t % 86_400_000) / 3_600_000);
    const m = Math.floor((t % 3_600_000) / 60_000);
    const s = Math.floor((t % 60_000) / 1000);
    const core = `${d > 0 ? `${d}d ` : ""}${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return over ? `-${core}` : core;
  })();

  return (
    <div className="flex flex-col items-center">
      <span className="label-caps">
        {remaining != null && remaining < 0 ? "demurrage running" : "free time remaining"}
      </span>
      <span
        className={`num text-6xl leading-none font-bold xl:text-7xl ${tone}`}
        aria-live="polite"
      >
        {label}
      </span>
      <span className="num mt-1 text-base text-foreground">
        after this:{" "}
        <span className="font-bold text-danger">{money(operation.demurrage_per_day)}/day</span>{" "}
        demurrage
      </span>
    </div>
  );
}

function Counter({
  label,
  value,
  flashOnIncrement,
}: {
  label: string;
  value: number;
  flashOnIncrement?: boolean;
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
    <div className="panel min-w-[9rem] rounded-md px-3 py-2 text-center">
      <div className="label-caps">{label}</div>
      <div className={`num text-4xl leading-none font-bold ${flash ? "flash-danger rounded" : ""}`}>
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
}: {
  operation: Operation | null;
  mandate: Mandate | null;
  policyBlocks: number;
  anchored: number;
}) {
  const win = (v: string | null) =>
    v ? new Date(v).toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";

  return (
    <header className="fixed inset-x-0 top-0 z-40 border-b border-border bg-background/97 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-3">
        <div className="min-w-[16rem]">
          <div className="label-caps">operation</div>
          <div className="num text-2xl font-bold text-accent">{operation?.ref ?? "no operation"}</div>
          <div className="num text-sm text-muted-foreground">
            {operation ? `${operation.container} · ${operation.origin} → ${operation.destination}` : "waiting for an operation row"}
          </div>
        </div>

        {operation ? (
          <Countdown operation={operation} />
        ) : (
          <div className="num text-4xl font-bold text-muted-foreground">--:--:--</div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {mandate ? (
            <>
              <div className="panel rounded-md px-3 py-2">
                <div className="label-caps">target</div>
                <div className="num text-2xl font-bold text-live">
                  {money(mandate.target_amount, mandate.currency)}
                </div>
              </div>
              <div className="rounded-md border-2 border-danger bg-danger/15 px-3 py-2">
                <div className="label-caps text-danger">max · hard limit</div>
                <div className="num text-2xl font-bold text-danger">
                  {money(mandate.max_amount, mandate.currency)}
                </div>
              </div>
              <div className="panel rounded-md px-3 py-2">
                <div className="label-caps">pickup window</div>
                <div className="num text-sm font-semibold">
                  {win(mandate.pickup_window_start)} → {win(mandate.pickup_window_end)}
                </div>
              </div>
            </>
          ) : (
            <div className="panel rounded-md px-3 py-2 text-sm text-muted-foreground">
              mandate chips appear when a mandate is issued
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Counter label="policy blocks" value={policyBlocks} flashOnIncrement />
          <Counter label="commitments anchored" value={anchored} />
        </div>
      </div>
    </header>
  );
}

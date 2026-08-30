import { useState } from "react";
import { toast } from "sonner";
import { backendUrl } from "@/lib/backend";
import type { Call, Phase } from "@/lib/amarra-types";

export interface CarrierDraft {
  id: string;
  name: string;
  phone: string;
}

const ACTIVE = new Set(["dialing", "ringing", "live"]);

/** Turns any backend error body into a sentence plus a concrete remedy. */
function explain(status: number, body: string): string {
  const b = body.toLowerCase();
  if (b.includes("21215")) return "21215 · enable Brazil in Twilio Geo Permissions";
  if (b.includes("10004")) return "10004 · Twilio account concurrency exceeded";
  if (b.includes("21212")) return "21212 · the caller ID is not yours on Twilio";
  if (b.includes("orçamento") || b.includes("budget")) return `${body} · raise TWILIO_CONCURRENCY in the backend .env`;
  if (b.includes("r7")) return `${body} · needs 3 carriers`;
  return body || `${status} · failed to open the market`;
}

export function MarketDock({
  phase,
  calls,
  carriers,
  onUpdateCarriers,
}: {
  phase: Phase | null;
  calls: Call[];
  carriers: CarrierDraft[];
  onUpdateCarriers: (next: CarrierDraft[]) => void;
}) {
  const [sheet, setSheet] = useState(false);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [inlineError, setInlineError] = useState<string | null>(null);

  const activeLegs = calls.filter(
    (c) => (c.leg_role ?? "counterparty") === "counterparty" && ACTIVE.has(String(c.status)),
  ).length;

  const ready = phase === "mandate_issued";
  const open = phase === "market_open" || phase === "negotiating";

  const dial = async () => {
    if (!backendUrl) {
      toast.error("VITE_BACKEND_URL is not configured");
      return;
    }
    setBusy(true);
    setInlineError(null);
    try {
      const custom = carriers.filter((c) => c.phone.trim().length > 0);
      const body: Record<string, unknown> = {};
      if (editing && custom.length) body["carriers"] = custom;
      const res = await fetch(`${backendUrl}/demo/dial-market`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await res.text();
      let parsed: Record<string, unknown> = {};
      try {
        parsed = JSON.parse(text) as Record<string, unknown>;
      } catch {
        /* not JSON; keep raw */
      }
      const err = (parsed["error"] ?? parsed["detail"]) as string | undefined;
      if (!res.ok || err) {
        const msg = explain(res.status, typeof err === "string" ? err : text);
        setInlineError(msg);
        toast.error(msg);
        return;
      }
      setSheet(false);
      setEditing(false);
      toast.success("🎯 Dialing 3 carriers in parallel…");
    } catch (e) {
      const msg = `Backend unreachable: ${String(e)}`;
      setInlineError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const pill = (label: string, sub: string, tone: "live" | "idle", onClick?: () => void) => (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      title={
        onClick ? undefined : `operation in ${phase ?? "—"} — reset first`
      }
      className={`w-full rounded-full border-2 px-5 py-2 text-left transition disabled:cursor-not-allowed ${
        tone === "live"
          ? "border-live bg-live/10 text-live hover:bg-live/20"
          : "border-border bg-card/60 text-muted-foreground opacity-70"
      }`}
      style={{ minHeight: 56 }}
    >
      <div className="text-base font-bold tracking-wide uppercase">{label}</div>
      <div className="num text-xs opacity-80">{sub}</div>
    </button>
  );

  return (
    <section className="space-y-2">
      {ready
        ? pill(
            carriers.length ? `🎯 Open market (${carriers.length})` : "🎯 Open market",
            "dials the carriers in parallel",
            "live",
            () =>
              setSheet(true),
          )
        : open
          ? pill("🔓 Market open", `${activeLegs} active legs`, "idle")
          : phase
            ? pill(`⏳ operation in ${phase}`, "reset first to open the market", "idle")
            : pill("⏳ waiting for operation", "no live operation", "idle")}

      {inlineError && !sheet && (
        <div className="num rounded border border-danger/60 bg-danger/10 px-3 py-2 text-xs text-danger">
          {inlineError}
        </div>
      )}

      {sheet && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end bg-background/70">
          <button
            type="button"
            aria-label="close"
            className="flex-1"
            onClick={() => setSheet(false)}
          />
          <div className="max-h-[70vh] overflow-y-auto rounded-t-2xl border-t-2 border-accent bg-card px-5 pt-3 pb-5">
            <div className="mx-auto mb-3 h-1.5 w-12 rounded-full bg-border" />

            <div className="flex items-center justify-between">
              <div className="label-caps">will dial simultaneously</div>
              <button
                type="button"
                onClick={() => setEditing((v) => !v)}
                className="num rounded border border-border px-2 py-1 text-[11px] text-muted-foreground"
              >
                {editing ? "done" : "edit carriers"}
              </button>
            </div>

            <div className="mt-3 space-y-3">
              {carriers.length === 0 && !editing && (
                <div className="num text-sm text-muted-foreground">
                  the carriers configured in the backend will be dialed in parallel
                </div>
              )}
              {carriers.map((c, i) =>
                editing ? (
                  <div key={i} className="flex flex-wrap gap-1">
                    {(["id", "name", "phone"] as const).map((k) => (
                      <input
                        key={k}
                        value={c[k]}
                        placeholder={k}
                        onChange={(e) =>
                          onUpdateCarriers(
                            carriers.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)),
                          )
                        }
                        className="num min-w-0 flex-1 rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-accent"
                      />
                    ))}
                  </div>
                ) : (
                  <div key={i}>
                    <div className="text-base font-bold">📞 {c.name || c.id || "—"}</div>
                    <div className="num text-sm text-muted-foreground">{c.phone || "number from backend"}</div>
                  </div>
                ),
              )}
            </div>

            <div className="num mt-4 rounded border border-warn/50 bg-warn/10 px-3 py-2 text-xs text-warn">
              ⚠️ {carriers.length ? `${carriers.length} phones` : "the phones"} will ring in ~2s.
              If one does not answer, the watchdog closes it in 45s.
            </div>

            {inlineError && (
              <div className="num mt-2 rounded border border-danger/60 bg-danger/10 px-3 py-2 text-xs text-danger">
                {inlineError}
              </div>
            )}

            <div className="mt-4 flex gap-2">
              <button
                type="button"
                onClick={() => setSheet(false)}
                className="num flex-1 rounded-full border-2 border-border px-4 py-3 text-sm font-bold uppercase"
              >
                cancel
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void dial()}
                className="num flex-1 rounded-full border-2 border-live bg-live/15 px-4 py-3 text-sm font-bold text-live uppercase disabled:opacity-50"
              >
                {busy ? "dialing…" : "🎯 dial"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

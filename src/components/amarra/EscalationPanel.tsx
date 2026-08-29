import { useState } from "react";
import { toast } from "sonner";
import { money, type Call, type Escalation } from "@/lib/amarra-types";
import { backendUrl } from "@/lib/backend";

function Option({
  label,
  amount,
  note,
  tone,
}: {
  label: string;
  amount: number | undefined;
  note?: string;
  tone: "good" | "bad";
}) {
  return (
    <div
      className={`rounded-md border-2 px-3 py-2 ${
        tone === "good" ? "border-live bg-live/10" : "border-danger bg-danger/10"
      }`}
    >
      <div className="label-caps">{label}</div>
      <div className={`num text-2xl font-bold ${tone === "good" ? "text-live" : "text-danger"}`}>
        {money(amount ?? null)}
      </div>
      {note && <div className="num text-xs text-muted-foreground">{note}</div>}
    </div>
  );
}

export function EscalationPanel({
  escalation,
  calls,
}: {
  escalation: Escalation;
  calls: Call[];
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const call = calls.find((c) => c.id === escalation.call_id);
  const comp = escalation.computation ?? {};

  const resolve = async (decision: "approve" | "reject") => {
    if (!backendUrl) {
      toast.error("VITE_BACKEND_URL is not configured");
      return;
    }
    setBusy(decision);
    try {
      const res = await fetch(`${backendUrl}/escalate/${escalation.call_id}/resolve`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ escalation_id: escalation.id, decision }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      toast.success(`Escalation ${decision}d`);
    } catch (e) {
      toast.error(`Could not send decision: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="enter-row rounded-lg border-2 border-info bg-info/10">
      <h2 className="label-caps flex items-center gap-2 border-b border-info px-3 py-2 text-info">
        <span className="pulse-dot inline-block size-2.5 rounded-full bg-info" />
        escalation · human decision required
      </h2>
      <div className="space-y-3 px-3 py-3">
        <p className="text-base leading-snug font-semibold">{escalation.brief}</p>
        <div className="num text-xs text-muted-foreground uppercase">
          {call?.carrier_name ?? "unknown carrier"}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Option
            label={comp.option_on_time?.label ?? "on time"}
            amount={comp.option_on_time?.amount}
            note={comp.option_on_time?.eta}
            tone="good"
          />
          <Option
            label={comp.option_late?.label ?? "late + demurrage"}
            amount={comp.option_late?.amount}
            note={
              comp.option_late?.demurrage != null
                ? `incl. ${money(comp.option_late.demurrage)} demurrage`
                : comp.option_late?.eta
            }
            tone="bad"
          />
        </div>

        {comp.delta != null && (
          <div className="num flex items-baseline justify-between border-t border-info/40 pt-2 text-lg font-bold">
            <span className="label-caps text-foreground">delta</span>
            <span>{money(comp.delta)}</span>
          </div>
        )}
        {comp.exceeds_mandate_by != null && (
          <div className="num rounded bg-danger px-3 py-1.5 text-base font-bold text-destructive-foreground">
            exceeds mandate by {money(comp.exceeds_mandate_by)}
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 pt-1">
          <button
            type="button"
            disabled={busy != null}
            onClick={() => void resolve("approve")}
            className="num rounded-md border-2 border-live bg-live px-4 py-3 text-lg font-bold tracking-wider text-primary-foreground uppercase transition-opacity hover:opacity-85 disabled:opacity-50"
          >
            {busy === "approve" ? "sending…" : "approve"}
          </button>
          <button
            type="button"
            disabled={busy != null}
            onClick={() => void resolve("reject")}
            className="num rounded-md border-2 border-danger px-4 py-3 text-lg font-bold tracking-wider text-danger uppercase transition-colors hover:bg-danger hover:text-destructive-foreground disabled:opacity-50"
          >
            {busy === "reject" ? "sending…" : "reject"}
          </button>
        </div>
      </div>
    </section>
  );
}

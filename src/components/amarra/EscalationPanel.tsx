import { useState } from "react";
import { callBackend } from "@/lib/amarra-actions";
import {
  asNumber,
  money,
  timeOfDay,
  type Escalation,
  type EscalationComputation,
} from "@/lib/amarra-types";

function Option({
  data,
  fallbackLabel,
  currency,
  tone,
}: {
  data: Record<string, unknown> | undefined;
  fallbackLabel: string;
  currency: string;
  tone: string;
}) {
  if (!data) return null;
  const amount = asNumber(data["amount"]);
  const demurrage = asNumber(data["demurrage"]);
  const total = asNumber(data["total"]) ?? (amount ?? 0) + (demurrage ?? 0);
  const eta = data["eta"];
  return (
    <div className={`rounded border-2 ${tone} bg-background/60 px-3 py-2`}>
      <div className="label-caps">{String(data["label"] ?? fallbackLabel)}</div>
      <div className="num mt-1 flex justify-between text-sm">
        <span className="text-muted-foreground">frete</span>
        <span className="font-bold">{money(amount, currency)}</span>
      </div>
      <div className="num flex justify-between text-sm">
        <span className="text-muted-foreground">demurrage</span>
        <span className="font-bold">{money(demurrage ?? 0, currency)}</span>
      </div>
      <div className="num mt-1 flex justify-between border-t border-border pt-1 text-lg">
        <span className="text-muted-foreground">total</span>
        <span className="font-bold">{money(total, currency)}</span>
      </div>
      {eta != null && (
        <div className="num mt-1 text-xs text-muted-foreground">eta: {String(eta)}</div>
      )}
    </div>
  );
}

function Card({
  escalation,
  currency,
  live,
}: {
  escalation: Escalation;
  currency: string;
  live: boolean;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const comp: EscalationComputation = escalation.computation ?? {};
  const onTime = comp["option_on_time"] as Record<string, unknown> | undefined;
  const late = comp["option_late"] as Record<string, unknown> | undefined;
  const delta = asNumber(comp["delta"]);
  const exceeds = asNumber(comp["exceeds_mandate_by"]);
  const resolved = !!escalation.resolution;

  const decide = async (approved: boolean) => {
    setBusy(true);
    await callBackend(
      `/escalate/${escalation.call_id}/resolve`,
      { approved, note: note || null },
      approved ? "Aprovado — o agente já foi avisado" : "Recusado — o agente segue no mandato",
    );
    setBusy(false);
  };

  return (
    <div
      className={`rounded-md border-2 px-4 py-3 ${
        resolved ? "border-live bg-live/10" : "border-danger bg-danger/12 phase-pulse"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className={`label-caps ${resolved ? "text-live" : "text-danger"}`}>
            {resolved ? "decisão registrada" : "decisão do humano · uma só"}
          </div>
          <div className="num text-xs text-muted-foreground">
            {escalation.trigger ?? "escalation"} · {timeOfDay(escalation.created_at)}
            {escalation.human_joined_at && ` · humano entrou ${timeOfDay(escalation.human_joined_at)}`}
          </div>
        </div>
        {escalation.human_phone && (
          <div className="num text-xs text-muted-foreground">{escalation.human_phone}</div>
        )}
      </div>

      <p className="mt-2 text-base leading-snug">{escalation.brief}</p>

      {(onTime || late) && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Option data={onTime} fallbackLabel="no prazo" currency={currency} tone="border-live" />
          <Option data={late} fallbackLabel="atrasado" currency={currency} tone="border-warn" />
        </div>
      )}

      <div className="num mt-2 space-y-0.5">
        {delta != null && (
          <div className="text-sm">
            delta entre as opções: <span className="font-bold">{money(delta, currency)}</span>
          </div>
        )}
        {exceeds != null && exceeds > 0 && (
          <div className="rounded border-2 border-danger bg-danger/20 px-2 py-1 text-lg font-bold text-danger">
            excede o mandato em {money(exceeds, currency)}
          </div>
        )}
      </div>

      {resolved ? (
        <div className="num mt-2 text-sm font-bold text-live">
          resolução: {escalation.resolution}
        </div>
      ) : (
        live && (
          <div className="mt-3 space-y-2">
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="nota da decisão (opcional)"
              className="num w-full rounded border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-accent"
            />
            <div className="flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void decide(true)}
                className="num flex-1 rounded border-2 border-live bg-live/15 px-3 py-2 text-base font-bold uppercase text-live hover:bg-live/25 disabled:opacity-50"
              >
                aprovar
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void decide(false)}
                className="num flex-1 rounded border-2 border-danger bg-danger/15 px-3 py-2 text-base font-bold uppercase text-danger hover:bg-danger/25 disabled:opacity-50"
              >
                recusar
              </button>
            </div>
          </div>
        )
      )}
    </div>
  );
}

export function EscalationPanel({
  escalations,
  currency,
  live,
}: {
  escalations: Escalation[];
  currency: string;
  live: boolean;
}) {
  if (escalations.length === 0) {
    return (
      <section className="panel rounded-md px-3 py-4">
        <div className="label-caps">escalação</div>
        <div className="num mt-1 text-sm text-muted-foreground">
          nenhuma decisão pendente — tudo que cabe no mandato o agente resolve sozinho
        </div>
      </section>
    );
  }
  return (
    <section className="space-y-2">
      {[...escalations].reverse().map((e) => (
        <Card key={String(e.id)} escalation={e} currency={currency} live={live} />
      ))}
    </section>
  );
}

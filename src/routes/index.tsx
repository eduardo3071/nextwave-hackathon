import { useEffect, useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { CallColumn } from "@/components/amarra/CallColumn";
import { CommitmentsList } from "@/components/amarra/CommitmentsList";
import { EscalationPanel } from "@/components/amarra/EscalationPanel";
import { PhaseRail } from "@/components/amarra/PhaseRail";
import { PhaseTimeline } from "@/components/amarra/PhaseTimeline";
import { QuoteTable } from "@/components/amarra/QuoteTable";
import { RecapCard } from "@/components/amarra/RecapCard";
import { TopBar } from "@/components/amarra/TopBar";
import { callBackend } from "@/lib/amarra-actions";
import { money, num, type Dossier, type Phase } from "@/lib/amarra-types";
import { useAmarraRealtime, useByCall } from "@/lib/useAmarraRealtime";
import { backendUrl } from "@/lib/backend";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Amarra · sala de controle de negociação de frete" },
      {
        name: "description",
        content:
          "Painel ao vivo do agente de voz Amarra: mandato, leilão em paralelo, decisões de política e compromissos ancorados no áudio.",
      },
      { property: "og:title", content: "Amarra · sala de controle" },
      {
        property: "og:description",
        content:
          "Negociação de frete por telefone com compromissos ancorados no áudio e uma única decisão para o humano.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: Dashboard,
});

const DEFAULT_CARRIERS = [
  { id: "fletes-bajio", name: "Fletes del Bajío", phone: "" },
  { id: "transportes-ruiz", name: "Transportes Ruiz", phone: "" },
  { id: "autolineas-mx", name: "Autolíneas MX", phone: "" },
];

function useCarriers() {
  const [carriers, setCarriers] = useState(DEFAULT_CARRIERS);
  useEffect(() => {
    const raw = window.localStorage.getItem("amarra.carriers");
    if (raw) {
      try {
        setCarriers(JSON.parse(raw) as typeof DEFAULT_CARRIERS);
      } catch {
        /* keep defaults */
      }
    }
  }, []);
  const update = (next: typeof DEFAULT_CARRIERS) => {
    setCarriers(next);
    window.localStorage.setItem("amarra.carriers", JSON.stringify(next));
  };
  return { carriers, update };
}

function Btn({
  children,
  onClick,
  tone = "accent",
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  tone?: "accent" | "live" | "warn" | "danger";
  disabled?: boolean;
}) {
  const tones = {
    accent: "border-accent text-accent hover:bg-accent/15",
    live: "border-live text-live hover:bg-live/15",
    warn: "border-warn text-warn hover:bg-warn/15",
    danger: "border-danger text-danger hover:bg-danger/15",
  } as const;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`num rounded border-2 px-3 py-1.5 text-sm font-bold tracking-wide uppercase disabled:cursor-not-allowed disabled:opacity-40 ${tones[tone]}`}
    >
      {children}
    </button>
  );
}

function DossierModal({ dossier, onClose }: { dossier: Dossier; onClose: () => void }) {
  const block = (title: string, value: unknown) => (
    <div key={title} className="panel rounded-md p-3">
      <div className="label-caps">{title}</div>
      <pre className="num mt-1 overflow-x-auto text-xs whitespace-pre-wrap">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/90 p-6">
      <div className="w-full max-w-4xl space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="label-caps">dossiê da operação</div>
            <h2 className="text-2xl font-bold text-live">
              {dossier.headline ?? dossier.outcome}
            </h2>
          </div>
          <Btn onClick={onClose} tone="danger">
            fechar
          </Btn>
        </div>
        {block("financeiro", dossier.financial)}
        {block("operacional", dossier.operational)}
        {block("compromissos", dossier.commitments)}
        {block("comparação", dossier.comparison)}
        {block("escalações", dossier.escalations)}
        {block("timeline", dossier.timeline)}
      </div>
    </div>
  );
}

function Dashboard() {
  const state = useAmarraRealtime();
  const grouped = useByCall(state);
  const { carriers, update } = useCarriers();
  const [showDossier, setShowDossier] = useState(false);
  const [showCarriers, setShowCarriers] = useState(false);

  const {
    operation,
    mandate,
    auction,
    phaseEvents,
    quotes,
    calls,
    commitments,
    escalations,
    recaps,
    dossier,
  } = state;

  const currency = operation?.currency ?? "MXN";
  const phase: Phase | null = operation?.phase ?? null;

  const counterpartyCalls = useMemo(
    () => calls.filter((c) => (c.leg_role ?? "counterparty") === "counterparty"),
    [calls],
  );
  const otherLegs = useMemo(
    () => calls.filter((c) => c.leg_role === "human" || c.leg_role === "agent"),
    [calls],
  );

  const policyBlocks = state.policyEvents.filter(
    (p) => p.decision === "block" || p.decision === "deny",
  ).length;
  const anchored = commitments.filter((c) => c.anchor_state === "anchored").length;
  const winnerCallId = auction?.winner_call_id ?? auction?.reserved_by ?? null;

  const run = (path: string, body?: unknown, ok?: string) => () =>
    void callBackend(path, body, ok);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar
        operation={operation}
        mandate={mandate}
        policyBlocks={policyBlocks}
        anchored={anchored}
        hasDossier={!!dossier}
        onOpenDossier={() => setShowDossier(true)}
      />

      <PhaseRail
        operation={operation}
        phaseEvents={phaseEvents}
        onOpenEscalation={() => {
          document.getElementById("amarra-escalation")?.scrollIntoView({ behavior: "smooth" });
        }}
      />

      <main className="grid gap-4 px-5 py-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="min-w-0 space-y-4">
          <section className="grid gap-3 lg:grid-cols-3">
            {counterpartyCalls.length === 0 ? (
              <div className="panel num rounded-md px-3 py-6 text-sm text-muted-foreground lg:col-span-3">
                as colunas aparecem quando o leilão disca — uma por perna
              </div>
            ) : (
              counterpartyCalls.map((c) => (
                <CallColumn
                  key={c.id}
                  call={c}
                  utterances={grouped.utterances.get(c.id) ?? []}
                  policyEvents={grouped.policyEvents.get(c.id) ?? []}
                  readBacks={grouped.readBacks.get(c.id) ?? []}
                  currency={currency}
                  isWinner={c.id === winnerCallId}
                />
              ))
            )}
          </section>

          {otherLegs.length > 0 && (
            <section className="panel num rounded-md px-3 py-2 text-xs">
              <span className="label-caps mr-2">outras pernas na conferência</span>
              {otherLegs.map((c) => (
                <span key={c.id} className="mr-3">
                  {c.leg_role}: {c.phone ?? c.carrier_name ?? c.id.slice(0, 8)} · {c.status}
                </span>
              ))}
            </section>
          )}

          <QuoteTable quotes={quotes} auction={auction} currency={currency} />

          <div id="amarra-escalation">
            <EscalationPanel
              escalations={escalations}
              currency={currency}
              live={phase === "escalated" || escalations.some((e) => !e.resolution)}
            />
          </div>
        </div>

        <aside className="min-w-0 space-y-4">
          <PhaseTimeline events={phaseEvents} />
          <CommitmentsList commitments={commitments} />
          <RecapCard
            recaps={recaps}
            dossier={dossier}
            onOpenDossier={() => setShowDossier(true)}
          />
          {auction && (
            <section className="panel num rounded-md px-3 py-2 text-xs">
              <div className="label-caps">leilão</div>
              <div>status: {auction.status}</div>
              {auction.reserved_by && (
                <div className="text-live">reservado por {auction.reserved_by.slice(0, 8)}</div>
              )}
              {auction.reserve_amount != null && (
                <div>reserva: {money(auction.reserve_amount, currency)}</div>
              )}
              {auction.release_reason && <div className="text-warn">{auction.release_reason}</div>}
              <div>cotações: {num(quotes.length)}</div>
            </section>
          )}
        </aside>
      </main>

      <footer className="sticky bottom-0 z-30 border-t border-border bg-background/97 px-5 py-3 backdrop-blur">
        {!backendUrl && (
          <div className="num mb-2 text-xs text-danger">
            VITE_BACKEND_URL não configurado — os botões de ação ficam sem destino
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <span className="label-caps mr-1">fase atual: {phase ?? "—"}</span>

          {phase === "detected" && operation && (
            <Btn
              tone="live"
              onClick={run(`/phase2/issue/${operation.id}`, undefined, "Mandato emitido")}
            >
              emitir mandato
            </Btn>
          )}

          {phase === "mandate_issued" && operation && (
            <>
              <Btn
                tone="live"
                onClick={run(
                  "/phase3/open",
                  { operation_ref: operation.ref, carriers },
                  "Mercado aberto — discando",
                )}
                disabled={carriers.length < 3}
              >
                abrir mercado ({carriers.length})
              </Btn>
              <Btn tone="accent" onClick={() => setShowCarriers((v) => !v)}>
                transportadoras
              </Btn>
            </>
          )}

          {(phase === "market_open" || phase === "negotiating") && auction && (
            <Btn
              tone="warn"
              onClick={run(`/phase3/abort/${auction.id}`, undefined, "Leilão abortado")}
            >
              abortar leilão
            </Btn>
          )}

          {phase === "reserved" && auction && (
            <Btn
              tone="warn"
              onClick={run(`/phase5/release/${auction.id}`, undefined, "Reserva devolvida")}
            >
              devolver reserva
            </Btn>
          )}

          {phase === "verified" && operation && (
            <Btn
              tone="live"
              onClick={run(`/phase8/close/${operation.id}`, undefined, "Operação encerrada")}
            >
              encerrar
            </Btn>
          )}

          {operation && phase !== "closed" && phase !== "failed" && (
            <Btn
              tone="danger"
              onClick={run(`/phase8/fail/${operation.id}`, undefined, "Operação marcada como falha")}
            >
              falhar manualmente
            </Btn>
          )}

          {operation && (phase === "closed" || phase === "failed") && (
            <Btn
              tone="accent"
              onClick={run(`/phase8/reopen/${operation.id}`, undefined, "Operação reaberta")}
            >
              reabrir
            </Btn>
          )}

          {!state.ready && <span className="num text-xs text-muted-foreground">conectando…</span>}
        </div>

        {showCarriers && (
          <div className="mt-3 space-y-1">
            {carriers.map((c, i) => (
              <div key={i} className="flex flex-wrap gap-1">
                {(["id", "name", "phone"] as const).map((k) => (
                  <input
                    key={k}
                    value={c[k]}
                    placeholder={k}
                    onChange={(e) =>
                      update(carriers.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))
                    }
                    className="num rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-accent"
                  />
                ))}
              </div>
            ))}
            <Btn
              tone="accent"
              onClick={() => update([...carriers, { id: "", name: "", phone: "" }])}
            >
              + perna
            </Btn>
          </div>
        )}
      </footer>

      {showDossier && dossier && (
        <DossierModal dossier={dossier} onClose={() => setShowDossier(false)} />
      )}
    </div>
  );
}

import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { TopBar } from "@/components/amarra/TopBar";
import { CallColumn } from "@/components/amarra/CallColumn";
import { QuoteTable } from "@/components/amarra/QuoteTable";
import { CommitmentsList } from "@/components/amarra/CommitmentsList";
import { EscalationPanel } from "@/components/amarra/EscalationPanel";
import { useAmarraRealtime } from "@/lib/useAmarraRealtime";
import { backendUrl } from "@/lib/backend";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Amarra — Live Freight Negotiation Control Room" },
      {
        name: "description",
        content:
          "Real-time operations dashboard for a voice AI agent negotiating freight by phone: live transcripts, policy decisions, anchored commitments and demurrage countdown.",
      },
      { property: "og:title", content: "Amarra — Live Freight Negotiation Control Room" },
      {
        property: "og:description",
        content:
          "Monitor live carrier calls, policy blocks, quote comparison and audio-backed commitments in real time.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Amarra,
});

function Amarra() {
  const state = useAmarraRealtime();
  const [starting, setStarting] = useState(false);

  const running = state.auction?.state === "running";
  const calls = useMemo(
    () => (state.auction ? state.calls.filter((c) => c.auction_id === state.auction!.id) : []),
    [state.calls, state.auction],
  );

  const policyBlocks = state.policyEvents.filter((p) => p.decision === "block").length;
  const anchored = state.commitments.filter((c) => c.state === "anchored").length;
  const openEscalations = state.escalations.filter((e) => e.state === "open");
  const currency = state.mandate?.currency ?? "USD";
  const winnerExists = calls.some((c) => c.is_winner);

  const startAuction = async () => {
    if (!backendUrl) {
      toast.error("VITE_BACKEND_URL is not configured");
      return;
    }
    if (!state.operation) {
      toast.error("No operation loaded yet");
      return;
    }
    setStarting(true);
    try {
      const res = await fetch(`${backendUrl}/auction/start`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          operation_ref: state.operation.ref,
          carriers: calls.map((c) => ({
            carrier_name: c.carrier_name,
            carrier_phone: c.carrier_phone,
          })),
        }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      toast.success("Auction start requested");
    } catch (e) {
      toast.error(`Could not start auction: ${String(e)}`);
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col pt-[8.5rem] pb-20">
      <TopBar
        operation={state.operation}
        mandate={state.mandate}
        policyBlocks={policyBlocks}
        anchored={anchored}
      />

      <main className="flex min-h-0 flex-1 gap-4 px-4 py-4">
        <div className="grid min-h-[70vh] flex-1 grid-cols-1 gap-4 lg:grid-cols-3">
          {calls.length === 0 ? (
            <div className="panel col-span-full flex items-center justify-center rounded-lg p-10 text-center">
              <p className="max-w-lg text-lg text-muted-foreground">
                {state.ready
                  ? running
                    ? "Calls will appear here the moment the agent starts dialing carriers."
                    : "No auction is running. Start one below — one live call column per carrier will open here."
                  : "Connecting to the live feed…"}
              </p>
            </div>
          ) : (
            calls.slice(0, 3).map((call) => (
              <CallColumn
                key={call.id}
                call={call}
                released={
                  call.status === "released" ||
                  (winnerExists && !call.is_winner && call.status === "done")
                }
                utterances={state.utterances.filter((u) => u.call_id === call.id)}
                policyEvents={state.policyEvents.filter((p) => p.call_id === call.id)}
              />
            ))
          )}
        </div>

        <aside className="flex w-[26rem] shrink-0 flex-col gap-4 overflow-y-auto">
          {openEscalations.map((e) => (
            <EscalationPanel key={e.id} escalation={e} calls={state.calls} />
          ))}
          <QuoteTable calls={calls} currency={currency} />
          <CommitmentsList commitments={state.commitments} calls={state.calls} />
          {openEscalations.length === 0 && (
            <section className="panel rounded-lg px-3 py-3">
              <h2 className="label-caps text-foreground">escalations</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                When the agent hits the mandate ceiling, the decision brief appears here.
              </p>
            </section>
          )}
        </aside>
      </main>

      <footer className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-between gap-4 border-t border-border bg-background/97 px-5 py-2.5 backdrop-blur">
        <div className="num text-sm uppercase">
          <span className="label-caps">auction</span>{" "}
          <span
            className={
              running ? "font-bold text-live" : "font-bold text-muted-foreground"
            }
          >
            {state.auction?.state ?? "none"}
          </span>
        </div>
        <button
          type="button"
          onClick={() => void startAuction()}
          disabled={starting || running}
          className="num rounded-md border-2 border-primary bg-primary px-8 py-2.5 text-xl font-bold tracking-widest text-primary-foreground uppercase transition-opacity hover:opacity-85 disabled:opacity-40"
        >
          {starting ? "starting…" : running ? "auction running" : "start auction"}
        </button>
      </footer>
    </div>
  );
}

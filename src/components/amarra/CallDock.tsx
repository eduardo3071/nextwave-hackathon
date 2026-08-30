import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { backendUrl } from "@/lib/backend";
import type { Call } from "@/lib/amarra-types";

const ACTIVE = new Set(["dialing", "ringing", "live"]);
const FAILED = new Set(["no-answer", "no_answer", "failed", "busy", "canceled", "cancelled"]);

const sid = (c: Call) => (c as unknown as Record<string, unknown>)["call_sid"] as string | undefined;

/** 1s tick, used only for the local "ringing for Ns" / duration readouts. */
function useTick(on: boolean) {
  const [, setN] = useState(0);
  useEffect(() => {
    if (!on) return;
    const t = window.setInterval(() => setN((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [on]);
}

const secondsSince = (iso: string | null | undefined) =>
  iso ? Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000)) : 0;

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

function ring() {
  try {
    const Ctx =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const now = ctx.currentTime;
    for (const at of [0, 0.45]) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0, now + at);
      gain.gain.linearRampToValueAtTime(0.12, now + at + 0.02);
      gain.gain.linearRampToValueAtTime(0, now + at + 0.32);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + at);
      osc.stop(now + at + 0.35);
    }
    window.setTimeout(() => void ctx.close(), 1400);
  } catch {
    /* audio is a nicety, never a requirement */
  }
}

export function CallDock({ calls, big = false }: { calls: Call[]; big?: boolean }) {
  const [pending, setPending] = useState<{ sid?: string; to?: string } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seenInbound = useRef<Set<string>>(new Set());
  const bootstrapped = useRef(false);

  const inbound = useMemo(() => {
    const rows = calls.filter((c) => c.direction === "inbound");
    const live = rows.filter((c) => ACTIVE.has(String(c.status)));
    return live.length ? live[live.length - 1] : null;
  }, [calls]);

  const demo = useMemo(() => {
    if (!pending) return null;
    const rows = calls.filter(
      (c) =>
        (pending.sid && (sid(c) === pending.sid || c.id === pending.sid)) ||
        c.direction === "outbound_demo",
    );
    return rows.length ? rows[rows.length - 1] : null;
  }, [calls, pending]);

  useTick(!!inbound || !!pending);

  // Ring + vibrate the first time an inbound leg shows up (never for our own demo call).
  useEffect(() => {
    const first = !bootstrapped.current;
    for (const c of calls) {
      if (c.direction !== "inbound") continue;
      if (seenInbound.current.has(c.id)) continue;
      seenInbound.current.add(c.id);
      if (!first && ACTIVE.has(String(c.status))) {
        navigator.vibrate?.([200, 100, 200]);
        ring();
      }
    }
    bootstrapped.current = true;
  }, [calls]);

  // Demo call reached a terminal state.
  useEffect(() => {
    if (!pending || !demo) return;
    const s = String(demo.status);
    if (FAILED.has(s)) {
      setFailure(s);
      setPending(null);
    } else if (s === "done") {
      toast.success(`✓ chamada com ${demo.phone ?? pending.to ?? "—"} encerrada`);
      setPending(null);
    }
  }, [demo, pending]);

  const callMe = async () => {
    if (!backendUrl) {
      toast.error("VITE_BACKEND_URL não está configurado");
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const res = await fetch(`${backendUrl}/demo/call-me`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = (await res.json().catch(() => ({}))) as {
        call_sid?: string;
        to?: string;
        error?: string;
      };
      if (!res.ok || data.error) {
        toast.error(data.error ?? `${res.status} · falha ao discar`);
        return;
      }
      setPending({ sid: data.call_sid, to: data.to });
      toast.success(`Discando pra ${data.to ?? "seu número"}`);
    } catch (e) {
      toast.error(`Backend inacessível: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  if (inbound) {
    const live = String(inbound.status) === "live";
    const secs = secondsSince(live ? (inbound.answered_at ?? inbound.created_at) : inbound.created_at);
    return (
      <section
        className={`rounded-xl border-2 px-4 py-3 ${
          live ? "border-live bg-live/10" : "border-live bg-live/20 animate-[amarra-pulse_1s_ease-in-out_infinite]"
        }`}
      >
        {live ? (
          <>
            <div className="text-sm font-bold tracking-wide text-live">🟢 EM CHAMADA</div>
            <div className="num mt-1 text-lg">{inbound.phone ?? "—"}</div>
            <div className="num text-xs text-muted-foreground">Duração: {clock(secs)}</div>
          </>
        ) : (
          <>
            <div className="text-sm font-bold tracking-wide text-live">📞⬇️ CHAMADA ENTRANDO</div>
            <div className="num mt-1 text-lg">De: {inbound.phone ?? "—"}</div>
            <div className="num text-xs text-muted-foreground">Toca há: {secs}s</div>
            <div className="mt-2 text-xs text-live">⏳ agente entrando em segundos</div>
          </>
        )}
      </section>
    );
  }

  if (pending) {
    const status = demo ? String(demo.status) : "dialing";
    const live = status === "live";
    return (
      <section className="rounded-xl border-2 border-accent bg-accent/10 px-4 py-3">
        <div className="text-sm font-bold tracking-wide text-accent">
          {live ? "🟢 conectado" : "📞⬆️ Discando"}
        </div>
        <div className="num mt-1 text-lg">{demo?.phone ?? pending.to ?? "seu número"}</div>
        <div className="text-xs text-muted-foreground">
          {live ? "você mandou a Twilio ligar pra você" : "⚡ atende quando tocar"}
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded bg-border">
          <div
            className={`h-full ${live ? "w-full bg-live" : "w-1/3 animate-[amarra-pulse_1.2s_ease-in-out_infinite] bg-accent"}`}
          />
        </div>
      </section>
    );
  }

  return (
    <section>
      <button
        type="button"
        onClick={() => void callMe()}
        disabled={busy}
        className={`w-full rounded-full border-2 border-accent bg-accent/10 px-6 font-bold tracking-wide text-accent uppercase transition hover:bg-accent/20 disabled:opacity-50 ${
          big ? "min-h-16 text-lg" : "min-h-14 text-base"
        }`}
      >
        📞 Me liga
      </button>
      <div className="num mt-2 text-center text-xs text-muted-foreground">
        A Twilio vai discar pro seu celular · sem gasto internacional
      </div>
      {failure && (
        <div className="num mt-2 text-center text-xs text-danger">❌ chamada falhou: {failure}</div>
      )}
    </section>
  );
}

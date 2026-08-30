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

/** A leg only counts as "on the line now" while it is recent; stale rows never
 *  hold the banner hostage (the backend does not always write an end state). */
const FRESH_MS = 15 * 60 * 1000;
const fresh = (c: Call) =>
  Date.now() - new Date(c.answered_at ?? c.started_at ?? c.created_at).getTime() < FRESH_MS;

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

const E164 = /^\+[1-9]\d{7,14}$/;
const PHONE_KEY = "amarra:my_phone";

export function CallDock({ calls, big = false }: { calls: Call[]; big?: boolean }) {
  const [pending, setPending] = useState<{
    sid?: string | undefined;
    to?: string | undefined;
  } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [phone, setPhone] = useState("+55");
  const seenInbound = useRef<Set<string>>(new Set());
  const bootstrapped = useRef(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(PHONE_KEY);
    if (saved) setPhone(saved);
  }, []);

  const valid = E164.test(phone.trim());


  const inbound = useMemo(() => {
    const live = calls.filter(
      (c) => c.direction === "inbound" && ACTIVE.has(String(c.status)) && fresh(c),
    );
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
      if (!first && ACTIVE.has(String(c.status)) && fresh(c)) {
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
      toast.success(`✓ call with ${demo.phone ?? pending.to ?? "—"} ended`);
      setPending(null);
    }
  }, [demo, pending]);

  const callMe = async () => {
    if (!backendUrl) {
      toast.error("VITE_BACKEND_URL is not configured");
      return;
    }
    const to = phone.trim();
    if (!E164.test(to)) {
      toast.error("Enter your number in E.164 format, e.g. +5511999999999");
      return;
    }
    window.localStorage.setItem(PHONE_KEY, to);
    setBusy(true);
    setFailure(null);
    try {
      const res = await fetch(`${backendUrl}/demo/call-me`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ to }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        call_sid?: string;
        to?: string;
        error?: string;
      };
      if (!res.ok || data.error) {
        toast.error(data.error ?? `${res.status} · failed to dial`);
        return;
      }
      setPending({ sid: data.call_sid, to: data.to ?? to });
      toast.success(`Dialing ${data.to ?? to}`);

    } catch (e) {
      toast.error(`Backend unreachable: ${String(e)}`);
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
            <div className="text-sm font-bold tracking-wide text-live">🟢 ON THE CALL</div>
            <div className="num mt-1 text-lg">{inbound.phone ?? "—"}</div>
            <div className="num text-xs text-muted-foreground">Duration: {clock(secs)}</div>
          </>
        ) : (
          <>
            <div className="text-sm font-bold tracking-wide text-live">📞⬇️ INCOMING CALL</div>
            <div className="num mt-1 text-lg">From: {inbound.phone ?? "—"}</div>
            <div className="num text-xs text-muted-foreground">Ringing for: {secs}s</div>
            <div className="mt-2 text-xs text-live">⏳ agent joining in seconds</div>
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
          {live ? "🟢 connected" : "📞⬆️ Dialing"}
        </div>
        <div className="num mt-1 text-lg">{demo?.phone ?? pending.to ?? "your number"}</div>
        <div className="text-xs text-muted-foreground">
          {live ? "you asked Twilio to call you" : "⚡ pick up when it rings"}
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
      <label className="label-caps mb-1 block" htmlFor="amarra-phone">
        Your phone (E.164)
      </label>
      <input
        id="amarra-phone"
        inputMode="tel"
        autoComplete="tel"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && valid && !busy) void callMe();
        }}
        placeholder="+5511999999999"
        className={`num min-h-12 w-full rounded-xl border-2 bg-background/40 px-4 text-base text-foreground outline-none transition placeholder:text-muted-foreground ${
          phone.trim() && !valid ? "border-danger" : "border-border focus:border-accent"
        }`}
      />
      <button
        type="button"
        onClick={() => void callMe()}
        disabled={busy || !valid}
        className={`mt-3 w-full rounded-full border-2 border-accent bg-accent/10 px-6 font-bold tracking-wide text-accent uppercase transition hover:bg-accent/20 disabled:opacity-50 ${
          big ? "min-h-16 text-lg" : "min-h-14 text-base"
        }`}
      >
        📞 Call me
      </button>
      <div className="num mt-2 text-center text-xs text-muted-foreground">
        Twilio will dial this number · only numbers verified in Twilio can be reached
      </div>

      {failure && (
        <div className="num mt-2 text-center text-xs text-danger">❌ call failed: {failure}</div>
      )}
    </section>
  );
}

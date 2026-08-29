import { useEffect, useRef, useState } from "react";
import { Play, Square } from "lucide-react";
import { msWindow, type Call, type Commitment } from "@/lib/amarra-types";

const stateTone: Record<Commitment["state"], string> = {
  proposed: "border-warn text-warn",
  anchored: "border-live text-live",
  void: "border-grid text-muted-foreground",
};

export function CommitmentsList({
  commitments,
  calls,
}: {
  commitments: Commitment[];
  calls: Call[];
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const stopAt = useRef<number | null>(null);

  useEffect(() => {
    const el = audio.current;
    if (!el) return undefined;
    const onTime = () => {
      if (stopAt.current != null && el.currentTime >= stopAt.current) {
        el.pause();
        setPlaying(null);
      }
    };
    const onEnd = () => setPlaying(null);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("ended", onEnd);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("ended", onEnd);
    };
  }, []);

  const play = (c: Commitment) => {
    const el = audio.current;
    const call = calls.find((k) => k.id === c.call_id);
    if (!el || !call?.recording_url || c.t_start_ms == null) return;
    if (playing === c.id) {
      el.pause();
      setPlaying(null);
      return;
    }
    if (el.src !== call.recording_url) el.src = call.recording_url;
    stopAt.current = c.t_end_ms != null ? c.t_end_ms / 1000 : null;
    const start = () => {
      el.currentTime = c.t_start_ms! / 1000;
      void el.play();
      setPlaying(c.id);
    };
    if (el.readyState >= 1) start();
    else el.addEventListener("loadedmetadata", start, { once: true });
  };

  return (
    <section className="panel rounded-lg">
      <h2 className="label-caps border-b border-border px-3 py-2 text-foreground">
        commitments · click to hear the exact words
      </h2>
      <audio ref={audio} preload="metadata" className="hidden" />
      {commitments.length === 0 ? (
        <p className="px-3 py-3 text-sm text-muted-foreground">
          Every commitment the agent extracts appears here with its audio proof.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {commitments.map((c) => {
            const call = calls.find((k) => k.id === c.call_id);
            const playable = Boolean(call?.recording_url) && c.t_start_ms != null;
            const active = playing === c.id;
            return (
              <li key={c.id} className="enter-row">
                <button
                  type="button"
                  onClick={() => play(c)}
                  disabled={!playable}
                  className={`group flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors ${
                    playable ? "hover:bg-panel-2" : "cursor-not-allowed"
                  } ${active ? "bg-accent/15" : ""}`}
                >
                  <span
                    className={`num mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full border-2 ${
                      active
                        ? "ping-ring border-accent bg-accent text-accent-foreground"
                        : playable
                          ? "border-accent text-accent group-hover:bg-accent group-hover:text-accent-foreground"
                          : "border-grid text-muted-foreground"
                    }`}
                  >
                    {active ? <Square className="size-4" /> : <Play className="size-4" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-baseline gap-2">
                      <span className="label-caps text-foreground">{c.field}</span>
                      <span className="num text-lg font-bold text-accent">{c.value}</span>
                      <span
                        className={`num rounded-full border px-2 text-[0.65rem] font-bold uppercase ${stateTone[c.state]}`}
                      >
                        {c.state}
                      </span>
                    </span>
                    {c.quote && (
                      <span className="mt-1 block text-sm italic text-muted-foreground">
                        “{c.quote}”{" "}
                        <span className="num not-italic text-accent">
                          {msWindow(c.t_start_ms, c.t_end_ms) ?? ""}
                        </span>
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

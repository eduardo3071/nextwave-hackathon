import { useEffect, useRef, useState } from "react";
import { mmss, type Commitment } from "@/lib/amarra-types";

const ANCHOR_TONE: Record<string, string> = {
  anchored: "border-live text-live",
  pending: "border-warn text-warn",
  not_found: "border-danger text-danger",
  low_confidence: "border-warn text-warn",
};

const STATE_TONE: Record<string, string> = {
  proposed: "text-muted-foreground",
  read_back: "text-warn",
  confirmed: "text-live",
  anchored: "text-live",
  void: "text-danger line-through",
  retracted: "text-danger line-through",
};

type Slice = { url: string; start: number; end: number | null };

/**
 * Every ▶ plays exactly the slice of audio the commitment is anchored to.
 * A fresh Audio element per click: no preloading, works on the first press.
 */
function useSlicePlayer() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const stopper = useRef<number | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);

  const stop = () => {
    if (stopper.current != null) window.clearTimeout(stopper.current);
    stopper.current = null;
    if (audio.current) {
      audio.current.pause();
      audio.current = null;
    }
    setPlaying(null);
  };

  useEffect(() => stop, []);

  const play = (id: string, slice: Slice) => {
    stop();
    const el = new Audio(slice.url);
    audio.current = el;
    setPlaying(id);
    const startAt = slice.start / 1000;
    const duration = slice.end != null ? Math.max(300, slice.end - slice.start) : null;

    const begin = () => {
      try {
        el.currentTime = startAt;
      } catch {
        /* some browsers refuse before metadata; the seek below retries */
      }
      void el.play().catch(() => stop());
      if (duration != null) {
        stopper.current = window.setTimeout(stop, duration + 120);
      }
    };

    el.addEventListener("loadedmetadata", () => {
      el.currentTime = startAt;
    });
    el.addEventListener("ended", stop);
    el.addEventListener("error", stop);
    begin();
  };

  return { play, stop, playing };
}

export function CommitmentsList({ commitments }: { commitments: Commitment[] }) {
  const { play, stop, playing } = useSlicePlayer();

  const sliceFor = (c: Commitment, affirmation: boolean): Slice | null => {
    if (!c.audio_url) return null;
    const start = affirmation ? c.affirmation_t_start_ms : c.t_start_ms;
    if (start == null) return null;
    const end = affirmation ? c.affirmation_t_end_ms : c.t_end_ms;
    return { url: c.audio_url, start, end };
  };

  return (
    <section className="panel rounded-md">
      <div className="border-b border-border px-3 py-2">
        <div className="label-caps">compromissos · ancorados no áudio</div>
      </div>
      {commitments.length === 0 ? (
        <div className="num px-3 py-4 text-sm text-muted-foreground">
          nenhum compromisso ainda — sem âncora no áudio, o campo não entra
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {commitments.map((c) => {
            const id = String(c.id);
            const main = sliceFor(c, false);
            const affirm = sliceFor(c, true);
            return (
              <li key={id} className="row-in px-3 py-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="num text-sm">
                      <span className="font-bold text-accent">{c.field}</span>
                      <span className="mx-1 text-muted-foreground">=</span>
                      <span className="text-base font-bold">{c.value}</span>
                    </div>
                    {c.quote && (
                      <div className="mt-0.5 truncate text-xs italic text-muted-foreground">
                        “{c.quote}”
                      </div>
                    )}
                    <div className="num mt-1 flex flex-wrap items-center gap-1.5 text-[0.7rem]">
                      <span
                        className={`rounded border px-1 uppercase ${ANCHOR_TONE[c.anchor_state] ?? "border-border"}`}
                      >
                        {c.anchor_state}
                      </span>
                      <span className={`uppercase ${STATE_TONE[c.state] ?? ""}`}>{c.state}</span>
                      {c.t_start_ms != null && (
                        <span className="text-muted-foreground">
                          [{mmss(c.t_start_ms)}–{mmss(c.t_end_ms)}]
                        </span>
                      )}
                      {c.anchor_confidence != null && (
                        <span className="text-muted-foreground">
                          conf {(c.anchor_confidence * 100).toFixed(0)}%
                        </span>
                      )}
                      {c.anchor_method && (
                        <span className="text-muted-foreground">{c.anchor_method}</span>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <button
                      type="button"
                      disabled={!main}
                      onClick={() => (playing === id ? stop() : main && play(id, main))}
                      title={main ? "tocar o trecho exato" : "sem áncora de áudio"}
                      className={`num rounded border-2 px-2.5 py-1 text-sm font-bold ${
                        main
                          ? playing === id
                            ? "border-live bg-live/20 text-live"
                            : "border-live text-live hover:bg-live/15"
                          : "cursor-not-allowed border-border text-muted-foreground"
                      }`}
                    >
                      {playing === id ? "■" : "▶"} trecho
                    </button>
                    {affirm && (
                      <button
                        type="button"
                        onClick={() =>
                          playing === `${id}-a` ? stop() : play(`${id}-a`, affirm)
                        }
                        className={`num rounded border px-2 py-0.5 text-xs ${
                          playing === `${id}-a`
                            ? "border-accent bg-accent/20 text-accent"
                            : "border-accent text-accent hover:bg-accent/15"
                        }`}
                      >
                        ▶ “sim”
                      </button>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

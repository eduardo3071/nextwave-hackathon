/** AI CREW brand mark: a hex "crew" badge with an audio waveform inside —
 *  voice agents working as one crew. Pure SVG, uses theme tokens. */
export function CrewMark({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="crew-stroke" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="1" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.45" />
        </linearGradient>
      </defs>
      <path
        d="M24 2.6 43 13.3v21.4L24 45.4 5 34.7V13.3z"
        fill="none"
        stroke="url(#crew-stroke)"
        strokeWidth="2.4"
        strokeLinejoin="round"
      />
      <g stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
        <line x1="14" y1="21" x2="14" y2="27" opacity="0.55" />
        <line x1="19" y1="17" x2="19" y2="31" opacity="0.75" />
        <line x1="24" y1="12.5" x2="24" y2="35.5" />
        <line x1="29" y1="17" x2="29" y2="31" opacity="0.75" />
        <line x1="34" y1="21" x2="34" y2="27" opacity="0.55" />
      </g>
    </svg>
  );
}

export function CrewLogo({
  size = "md",
  tagline,
}: {
  size?: "sm" | "md";
  tagline?: string;
}) {
  const sm = size === "sm";
  return (
    <div className="flex items-center gap-2.5">
      <CrewMark className={sm ? "h-8 w-8 text-accent" : "h-11 w-11 text-accent"} />
      <div className="min-w-0">
        <div
          className={`display tracking-[0.28em] text-foreground uppercase ${
            sm ? "text-base leading-none" : "text-2xl leading-none"
          }`}
        >
          AI <span className="text-accent">CREW</span>
        </div>
        {tagline && (
          <div className="num mt-1 truncate text-[11px] tracking-wide text-muted-foreground">
            {tagline}
          </div>
        )}
      </div>
    </div>
  );
}

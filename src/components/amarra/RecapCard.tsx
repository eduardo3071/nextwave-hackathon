import { timeOfDay, type Dossier, type RecapDelivery } from "@/lib/amarra-types";

export function RecapCard({
  recaps,
  dossier,
  onOpenDossier,
}: {
  recaps: RecapDelivery[];
  dossier: Dossier | null;
  onOpenDossier: () => void;
}) {
  return (
    <section className="panel rounded-md">
      <div className="border-b border-border px-3 py-2">
        <div className="label-caps">recap sent · R3a</div>
      </div>
      {recaps.length === 0 ? (
        <div className="num px-3 py-3 text-sm text-muted-foreground">
          no recap yet — the operation cannot close without it
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {[...recaps].reverse().map((r) => (
            <li key={String(r.id)} className="row-in px-3 py-2">
              <div className="num flex items-center justify-between gap-2 text-xs">
                <span className="font-bold uppercase">{r.channel}</span>
                <span
                  className={r.status === "sent" ? "font-bold text-live" : "font-bold text-danger"}
                >
                  {r.status}
                </span>
                <span className="text-muted-foreground">{timeOfDay(r.created_at)}</span>
              </div>
              <div className="num truncate text-sm">{r.target}</div>
              {r.subject && <div className="truncate text-xs text-muted-foreground">{r.subject}</div>}
              {r.error && <div className="num text-xs text-danger">{r.error}</div>}
            </li>
          ))}
        </ul>
      )}
      {dossier && (
        <div className="border-t border-border px-3 py-2">
          <div className="text-sm font-bold text-live">{dossier.headline ?? dossier.outcome}</div>
          <button
            type="button"
            onClick={onOpenDossier}
            className="num mt-1 rounded border border-live px-2 py-0.5 text-xs font-bold uppercase text-live hover:bg-live/15"
          >
            view dossier
          </button>
        </div>
      )}
    </section>
  );
}

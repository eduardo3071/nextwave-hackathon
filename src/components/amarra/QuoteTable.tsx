import { money, type Call } from "@/lib/amarra-types";

export function QuoteTable({ calls, currency }: { calls: Call[]; currency: string }) {
  return (
    <section className="panel rounded-lg">
      <div className="flex items-baseline justify-between border-b border-border px-3 py-2">
        <h2 className="label-caps text-foreground">quote comparison</h2>
        <span className="num text-[0.65rem] tracking-widest text-muted-foreground uppercase">
          audit record
        </span>
      </div>
      {calls.length === 0 ? (
        <p className="px-3 py-3 text-sm text-muted-foreground">
          Each carrier's final ask lands here as the auction resolves.
        </p>
      ) : (
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="label-caps border-b border-grid">
              <th className="px-3 py-1.5">carrier</th>
              <th className="px-3 py-1.5 text-right">final ask</th>
              <th className="px-3 py-1.5 text-right">rds</th>
              <th className="px-3 py-1.5">reason</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr
                key={c.id}
                className={`enter-row border-b border-border/70 align-top ${
                  c.is_winner ? "bg-live/15" : ""
                }`}
              >
                <td className="px-3 py-2 text-base font-bold uppercase">
                  {c.is_winner && <span className="num mr-1 text-live">▸</span>}
                  {c.carrier_name}
                  {c.is_winner && (
                    <span className="num ml-2 rounded bg-live px-1.5 py-0.5 text-[0.65rem] font-bold tracking-wider text-primary-foreground uppercase">
                      winner
                    </span>
                  )}
                </td>
                <td className="num px-3 py-2 text-right text-base font-bold">
                  {money(c.final_ask, currency)}
                </td>
                <td className="num px-3 py-2 text-right text-base">{c.rounds}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {c.outcome_reason ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

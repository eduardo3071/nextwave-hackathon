import { money, num, type Auction, type AuctionQuote } from "@/lib/amarra-types";

/**
 * The R7 audit table: every carrier that was dialed, what it asked, what the
 * policy approved, and why it won or lost. Rendered straight from auction_quotes.
 */
export function QuoteTable({
  quotes,
  auction,
  currency,
}: {
  quotes: AuctionQuote[];
  auction: Auction | null;
  currency: string;
}) {
  const sorted = (Array.isArray(quotes) ? [...quotes] : []).sort((a, b) => {
    if (a.winner !== b.winner) return a.winner ? -1 : 1;
    const av = a.approved ?? a.final_ask ?? Number.POSITIVE_INFINITY;
    const bv = b.approved ?? b.final_ask ?? Number.POSITIVE_INFINITY;
    return av - bv;
  });

  return (
    <section className="panel rounded-md">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="label-caps">comparação de cotações · auditável</div>
        <div className="num flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          {auction && <span>status: {auction.status}</span>}
          {auction?.legs_planned != null && (
            <span>
              pernas: {auction.legs_planned}
              {auction.legs_budget != null ? `/${auction.legs_budget}` : ""}
            </span>
          )}
          {auction?.soft_deadline_s != null && <span>soft {auction.soft_deadline_s}s</span>}
          {auction?.hard_deadline_s != null && <span>hard {auction.hard_deadline_s}s</span>}
          {auction?.reserve_amount != null && (
            <span className="font-bold text-live">
              reserva {money(auction.reserve_amount, currency)}
            </span>
          )}
        </div>
      </div>

      {auction?.admission_warnings?.length ? (
        <div className="num border-b border-warn/40 bg-warn/10 px-3 py-1 text-xs text-warn">
          admissão: {auction.admission_warnings.join(" · ")}
        </div>
      ) : null}

      {sorted.length === 0 ? (
        <div className="num px-3 py-4 text-sm text-muted-foreground">
          a tabela se preenche à medida que as cotações chegam
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="label-caps border-b border-border text-left">
              <th className="px-3 py-1.5">transportadora</th>
              <th className="px-3 py-1.5 text-right">pediu</th>
              <th className="px-3 py-1.5 text-right">aprovado</th>
              <th className="px-3 py-1.5 text-right">rodadas</th>
              <th className="px-3 py-1.5 text-right">tempo</th>
              <th className="px-3 py-1.5">razão</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((q) => (
              <tr
                key={String(q.id)}
                className={`row-in border-b border-border/60 ${q.winner ? "bg-live/10" : ""}`}
              >
                <td className="num px-3 py-1.5 font-bold">
                  {q.winner && <span className="mr-1 text-live">★</span>}
                  {q.carrier_name ?? q.carrier_id}
                </td>
                <td className="num px-3 py-1.5 text-right">{money(q.final_ask, currency)}</td>
                <td
                  className={`num px-3 py-1.5 text-right font-bold ${q.winner ? "text-live" : ""}`}
                >
                  {money(q.approved, currency)}
                </td>
                <td className="num px-3 py-1.5 text-right">{num(q.rounds)}</td>
                <td className="num px-3 py-1.5 text-right text-muted-foreground">
                  {q.quote_ms == null ? "—" : `${(q.quote_ms / 1000).toFixed(1)}s`}
                </td>
                <td className="num px-3 py-1.5 text-muted-foreground">{q.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {auction?.decision_reason && (
        <div className="num border-t border-border px-3 py-1.5 text-xs text-muted-foreground">
          decisão: {auction.decision_reason}
        </div>
      )}
    </section>
  );
}

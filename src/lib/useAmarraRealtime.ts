import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import type {
  Auction,
  AuctionQuote,
  Call,
  Commitment,
  Dossier,
  Escalation,
  Mandate,
  Operation,
  PhaseEvent,
  PolicyEvent,
  ReadBack,
  RecapDelivery,
  RowId,
  Utterance,
} from "./amarra-types";

// The backend tables are not in the generated Database types, so use an
// untyped view of the client and rely on the hand-written row interfaces.
const db = supabase as unknown as {
  from: (table: string) => any;
  channel: typeof supabase.channel;
  removeChannel: typeof supabase.removeChannel;
};

export interface AmarraState {
  ready: boolean;
  operation: Operation | null;
  mandate: Mandate | null;
  auction: Auction | null;
  phaseEvents: PhaseEvent[];
  quotes: AuctionQuote[];
  calls: Call[];
  utterances: Utterance[];
  policyEvents: PolicyEvent[];
  readBacks: ReadBack[];
  commitments: Commitment[];
  escalations: Escalation[];
  recaps: RecapDelivery[];
  dossier: Dossier | null;
}

const empty: AmarraState = {
  ready: false,
  operation: null,
  mandate: null,
  auction: null,
  phaseEvents: [],
  quotes: [],
  calls: [],
  utterances: [],
  policyEvents: [],
  readBacks: [],
  commitments: [],
  escalations: [],
  recaps: [],
  dossier: null,
};

const key = (id: RowId) => String(id);

const upsert = <T extends { id: RowId }>(list: T[], row: T) => {
  const i = list.findIndex((r) => key(r.id) === key(row.id));
  if (i === -1) return [...list, row];
  const next = [...list];
  next[i] = { ...next[i], ...row };
  return next;
};

const byTime = <T extends { id: RowId; created_at: string }>(list: T[]) =>
  [...list].sort(
    (a, b) => a.created_at.localeCompare(b.created_at) || key(a.id).localeCompare(key(b.id)),
  );

type ChangePayload = { new?: Record<string, unknown> | null; eventType?: string };

/**
 * Subscription-only view of the operation the backend is currently running.
 * Bootstraps once, then every later update arrives through Realtime.
 * There is no polling anywhere in this file.
 */
export function useAmarraRealtime() {
  const [state, setState] = useState<AmarraState>(empty);
  const opId = useRef<string | null>(null);
  const auctionId = useRef<string | null>(null);
  const callIds = useRef<Set<string>>(new Set());

  const belongsToCall = (row: Record<string, unknown> | null | undefined) =>
    !!row && typeof row["call_id"] === "string" && callIds.current.has(row["call_id"]);

  const belongsToOp = (row: Record<string, unknown> | null | undefined) =>
    !!row && !!opId.current && row["operation_id"] === opId.current;

  const loadCallChildren = useCallback(async (ids: string[]) => {
    if (!ids.length) return;
    const [u, p, r] = await Promise.all([
      db.from("utterances").select("*").in("call_id", ids),
      db.from("policy_events").select("*").in("call_id", ids),
      db.from("read_backs").select("*").in("call_id", ids),
    ]);
    setState((s) => ({
      ...s,
      utterances: byTime<Utterance>(u.data ?? []),
      policyEvents: byTime<PolicyEvent>(p.data ?? []),
      readBacks: byTime<ReadBack>(r.data ?? []),
    }));
  }, []);

  const bootstrap = useCallback(async () => {
    const { data: ops } = await db
      .from("operations")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(1);
    const operation: Operation | null = ops?.[0] ?? null;
    if (!operation) {
      opId.current = null;
      auctionId.current = null;
      callIds.current = new Set();
      setState({ ...empty, ready: true });
      return;
    }
    opId.current = operation.id;

    const [
      { data: mandates },
      { data: auctions },
      { data: events },
      { data: commitments },
      { data: recaps },
      { data: dossiers },
      { data: opCalls },
    ] = await Promise.all([
      db
        .from("mandates")
        .select("*")
        .eq("operation_id", operation.id)
        .order("created_at", { ascending: false })
        .limit(1),
      db
        .from("auctions")
        .select("*")
        .eq("operation_id", operation.id)
        .order("created_at", { ascending: false })
        .limit(1),
      db.from("phase_events").select("*").eq("operation_id", operation.id).order("id"),
      db.from("commitments").select("*").eq("operation_id", operation.id),
      db.from("recap_deliveries").select("*").eq("operation_id", operation.id),
      db.from("dossiers").select("*").eq("operation_id", operation.id).limit(1),
      db.from("calls").select("*").eq("operation_id", operation.id),
    ]);

    const auction: Auction | null = auctions?.[0] ?? null;
    auctionId.current = auction?.id ?? null;

    let calls: Call[] = opCalls ?? [];
    let quotes: AuctionQuote[] = [];
    if (auction) {
      const [{ data: aCalls }, { data: aQuotes }] = await Promise.all([
        db.from("calls").select("*").eq("auction_id", auction.id),
        db.from("auction_quotes").select("*").eq("auction_id", auction.id).order("id"),
      ]);
      const merged = new Map<string, Call>();
      for (const c of [...calls, ...((aCalls ?? []) as Call[])]) merged.set(c.id, c);
      calls = [...merged.values()];
      quotes = aQuotes ?? [];
    }
    calls = byTime<Call>(calls);
    callIds.current = new Set(calls.map((c) => c.id));

    const [{ data: escalations }] = await Promise.all([
      callIds.current.size
        ? db.from("escalations").select("*").in("call_id", [...callIds.current])
        : Promise.resolve({ data: [] }),
    ]);

    setState({
      ready: true,
      operation,
      mandate: mandates?.[0] ?? null,
      auction,
      phaseEvents: byTime<PhaseEvent>(events ?? []),
      quotes,
      calls,
      utterances: [],
      policyEvents: [],
      readBacks: [],
      commitments: byTime<Commitment>(commitments ?? []),
      escalations: byTime<Escalation>(escalations ?? []),
      recaps: byTime<RecapDelivery>(recaps ?? []),
      dossier: dossiers?.[0] ?? null,
    });

    await loadCallChildren([...callIds.current]);
  }, [loadCallChildren]);

  useEffect(() => {
    void bootstrap();

    const on = (channel: any, table: string, handler: (row: any) => void) =>
      channel.on("postgres_changes", { event: "*", schema: "public", table }, (p: ChangePayload) => {
        if (p.new) handler(p.new);
      });

    let channel = db.channel("amarra-realtime");

    channel = on(channel, "operations", (row: Operation) => {
      // A brand new operation takes over the room; the current one keeps updating.
      if (opId.current && row.id !== opId.current) {
        void bootstrap();
        return;
      }
      opId.current = row.id;
      setState((s) => ({ ...s, ready: true, operation: row }));
    });

    channel = on(channel, "mandates", (row: Mandate) => {
      if (!belongsToOp(row as unknown as Record<string, unknown>)) return;
      setState((s) => ({ ...s, mandate: row }));
    });

    channel = on(channel, "phase_events", (row: PhaseEvent) => {
      if (!belongsToOp(row as unknown as Record<string, unknown>)) return;
      setState((s) => ({ ...s, phaseEvents: byTime(upsert(s.phaseEvents, row)) }));
    });

    channel = on(channel, "auctions", (row: Auction) => {
      if (!belongsToOp(row as unknown as Record<string, unknown>)) return;
      auctionId.current = row.id;
      setState((s) => ({ ...s, auction: row }));
    });

    channel = on(channel, "auction_quotes", (row: AuctionQuote) => {
      if (auctionId.current && row.auction_id !== auctionId.current) return;
      setState((s) => ({ ...s, quotes: byTime(upsert(s.quotes, row)) }));
    });

    channel = on(channel, "calls", (row: Call) => {
      const mine =
        (auctionId.current && row.auction_id === auctionId.current) ||
        (opId.current && row.operation_id === opId.current);
      if (!mine) return;
      const isNew = !callIds.current.has(row.id);
      callIds.current.add(row.id);
      setState((s) => ({ ...s, calls: byTime(upsert(s.calls, row)) }));
      if (isNew) void loadCallChildren([row.id]);
    });

    channel = on(channel, "utterances", (row: Utterance) => {
      if (!belongsToCall(row as unknown as Record<string, unknown>)) return;
      setState((s) => ({ ...s, utterances: byTime(upsert(s.utterances, row)) }));
    });

    channel = on(channel, "policy_events", (row: PolicyEvent) => {
      if (!belongsToCall(row as unknown as Record<string, unknown>)) return;
      setState((s) => ({ ...s, policyEvents: byTime(upsert(s.policyEvents, row)) }));
    });

    channel = on(channel, "read_backs", (row: ReadBack) => {
      if (!belongsToCall(row as unknown as Record<string, unknown>)) return;
      setState((s) => ({ ...s, readBacks: byTime(upsert(s.readBacks, row)) }));
    });

    channel = on(channel, "commitments", (row: Commitment) => {
      const r = row as unknown as Record<string, unknown>;
      if (!belongsToOp(r) && !belongsToCall(r)) return;
      setState((s) => ({ ...s, commitments: byTime(upsert(s.commitments, row)) }));
    });

    channel = on(channel, "escalations", (row: Escalation) => {
      if (!belongsToCall(row as unknown as Record<string, unknown>)) return;
      setState((s) => ({ ...s, escalations: byTime(upsert(s.escalations, row)) }));
    });

    channel = on(channel, "recap_deliveries", (row: RecapDelivery) => {
      if (!belongsToOp(row as unknown as Record<string, unknown>)) return;
      setState((s) => ({ ...s, recaps: byTime(upsert(s.recaps, row)) }));
    });

    channel = on(channel, "dossiers", (row: Dossier) => {
      if (!belongsToOp(row as unknown as Record<string, unknown>)) return;
      setState((s) => ({ ...s, dossier: row }));
    });

    channel = on(channel, "call_briefs", () => {
      /* subscribed for completeness; the brief is rendered from commitments */
    });

    channel.subscribe();

    return () => {
      void db.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrap, loadCallChildren]);

  return state;
}

/** Utterances / policy events / read-backs grouped by call, for the columns. */
export function useByCall(state: AmarraState) {
  return useMemo(() => {
    const group = <T extends { call_id: string }>(rows: T[]) => {
      const m = new Map<string, T[]>();
      for (const r of rows) {
        const list = m.get(r.call_id);
        if (list) list.push(r);
        else m.set(r.call_id, [r]);
      }
      return m;
    };
    return {
      utterances: group(state.utterances),
      policyEvents: group(state.policyEvents),
      readBacks: group(state.readBacks),
      escalations: group(state.escalations),
    };
  }, [state.utterances, state.policyEvents, state.readBacks, state.escalations]);
}

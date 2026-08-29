import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import type {
  Auction,
  Call,
  Commitment,
  Escalation,
  Mandate,
  Operation,
  PolicyEvent,
  Utterance,
} from "./amarra-types";

// Tables are not present in the generated Database types yet, so use an
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
  calls: Call[];
  utterances: Utterance[];
  policyEvents: PolicyEvent[];
  commitments: Commitment[];
  escalations: Escalation[];
}

const empty: AmarraState = {
  ready: false,
  operation: null,
  mandate: null,
  auction: null,
  calls: [],
  utterances: [],
  policyEvents: [],
  commitments: [],
  escalations: [],
};

const upsert = <T extends { id: string }>(list: T[], row: T) => {
  const i = list.findIndex((r) => r.id === row.id);
  if (i === -1) return [...list, row];
  const next = [...list];
  next[i] = { ...next[i], ...row };
  return next;
};

const byTime = <T extends { created_at: string }>(list: T[]) =>
  [...list].sort((a, b) => a.created_at.localeCompare(b.created_at));

export function useAmarraRealtime() {
  const [state, setState] = useState<AmarraState>(empty);
  const callIds = useRef<Set<string>>(new Set());

  const loadCallChildren = useCallback(async (ids: string[]) => {
    if (!ids.length) return;
    const [u, p, c, e] = await Promise.all([
      db.from("utterances").select("*").in("call_id", ids),
      db.from("policy_events").select("*").in("call_id", ids),
      db.from("commitments").select("*").in("call_id", ids),
      db.from("escalations").select("*").in("call_id", ids),
    ]);
    setState((s) => ({
      ...s,
      utterances: byTime(u.data ?? []),
      policyEvents: byTime(p.data ?? []),
      commitments: byTime(c.data ?? []),
      escalations: byTime(e.data ?? []),
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
      setState({ ...empty, ready: true });
      return;
    }
    const [{ data: mandates }, { data: auctions }] = await Promise.all([
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
    ]);
    const auction: Auction | null = auctions?.[0] ?? null;
    let calls: Call[] = [];
    if (auction) {
      const { data } = await db
        .from("calls")
        .select("*")
        .eq("auction_id", auction.id)
        .order("created_at", { ascending: true });
      calls = data ?? [];
    }
    callIds.current = new Set(calls.map((c) => c.id));
    setState((s) => ({
      ...s,
      ready: true,
      operation,
      mandate: mandates?.[0] ?? null,
      auction,
      calls,
    }));
    await loadCallChildren(calls.map((c) => c.id));
  }, [loadCallChildren]);

  useEffect(() => {
    void bootstrap();

    const channel = db
      .channel("amarra-ops")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "operations" },
        ({ new: row }: any) =>
          setState((s) =>
            !s.operation || s.operation.id === row?.id ? { ...s, operation: row } : s,
          ),
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "mandates" },
        ({ new: row }: any) =>
          setState((s) =>
            s.operation && row?.operation_id === s.operation.id ? { ...s, mandate: row } : s,
          ),
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "auctions" },
        ({ new: row }: any) => {
          setState((s) => {
            if (!row) return s;
            if (s.operation && row.operation_id !== s.operation.id) return s;
            return { ...s, auction: row };
          });
        },
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "calls" },
        ({ new: row }: any) => {
          if (!row) return;
          callIds.current.add(row.id);
          setState((s) => {
            if (s.auction && row.auction_id !== s.auction.id) return s;
            return { ...s, calls: byTime(upsert(s.calls, row as Call)) };
          });
        },
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "utterances" },
        ({ new: row }: any) =>
          row && setState((s) => ({ ...s, utterances: byTime(upsert(s.utterances, row)) })),
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "policy_events" },
        ({ new: row }: any) =>
          row && setState((s) => ({ ...s, policyEvents: byTime(upsert(s.policyEvents, row)) })),
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "commitments" },
        ({ new: row }: any) =>
          row && setState((s) => ({ ...s, commitments: byTime(upsert(s.commitments, row)) })),
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "escalations" },
        ({ new: row }: any) =>
          row && setState((s) => ({ ...s, escalations: byTime(upsert(s.escalations, row)) })),
      )
      .subscribe();

    return () => {
      void db.removeChannel(channel);
    };
  }, [bootstrap]);

  return state;
}

"""
AMARRA · acesso ao Supabase.

Fino de propósito. O backend só escreve; o Realtime do Supabase empurra
para o Lovable. Nenhuma rota de leitura para o frontend precisa existir.
"""
from __future__ import annotations
import os
from supabase import Client, create_client


class DB:
    def __init__(self) -> None:
        self.c: Client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],   # service_role: só no backend
        )
        self._pending: dict[str, list[dict]] = {}

    # ── escrita ────────────────────────────────────────────────────────────
    def insert(self, table: str, row: dict) -> dict:
        return self.c.table(table).insert(row).execute().data[0]

    def update(self, table: str, id_: str, patch: dict) -> None:
        self.c.table(table).update(patch).eq("id", id_).execute()

    def update_by(self, table: str, col: str, val, patch: dict) -> None:
        self.c.table(table).update(patch).eq(col, val).execute()

    # ── leitura ────────────────────────────────────────────────────────────
    def get(self, table: str, id_: str) -> dict:
        return self.c.table(table).select("*").eq("id", id_).single().execute().data

    def find(self, table: str, col: str, val) -> dict | None:
        r = self.c.table(table).select("*").eq(col, val).limit(1).execute().data
        return r[0] if r else None

    def operation(self, ref: str) -> dict:
        return self.c.table("operations").select("*").eq("ref", ref).single().execute().data

    def mandate(self, operation_id: str) -> dict:
        return (self.c.table("mandates").select("*")
                .eq("operation_id", operation_id).single().execute().data)

    # ── compromissos aguardando âncora ─────────────────────────────────────
    def stash_pending_commitment(self, call_id: str, args: dict) -> None:
        self._pending.setdefault(call_id, []).append(args)

    def pop_pending(self, call_id: str) -> list[dict]:
        return self._pending.pop(call_id, [])

    # ── usados pela máquina de fases ───────────────────────────────────────
    def count(self, table: str, col: str, val) -> int:
        r = self.c.table(table).select("id", count="exact").eq(col, val).execute()
        return r.count or 0

    def rpc(self, fn: str, params: dict):
        return self.c.rpc(fn, params).execute()

    def insert_event(self, *a, **k) -> None:   # placeholder p/ eventos de conference
        pass


db = DB()

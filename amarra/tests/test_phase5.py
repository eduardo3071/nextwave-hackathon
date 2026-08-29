import asyncio
from decimal import Decimal

import pytest

from app.phase5_reserved import _build_comparison, release, try_reserve


@pytest.mark.asyncio
async def test_so_um_vencedor_em_corrida(auction):
    """Três sessões pedindo a reserva no mesmo instante."""
    rs = await asyncio.gather(*[
        try_reserve(auction, cid, Decimal(8400), "buy_it_now")
        for cid in list(auction.legs)[:3]
    ])
    assert sum(1 for r in rs if r["granted"]) == 1
    negados = [r for r in rs if not r["granted"]]
    assert all(r["reason"] == "already_reserved" for r in negados)


@pytest.mark.asyncio
async def test_banco_recusa_acima_do_teto(auction):
    """Mesmo que a sessão tenha bug, o Postgres barra."""
    r = await try_reserve(auction, list(auction.legs)[0], Decimal(9500), "bug")
    assert r["granted"] is False and r["reason"] == "above_max_rate"


@pytest.mark.asyncio
async def test_release_reabre_para_o_segundo(auction):
    a = list(auction.legs)[0]
    assert (await try_reserve(auction, a, Decimal(8400), "buy_it_now"))["granted"]
    assert (await release(auction, "winner_did_not_confirm"))["released"]
    b = list(auction.legs)[1]
    assert (await try_reserve(auction, b, Decimal(8900), "runner_up"))["granted"]


def test_comparacao_explica_cada_linha(auction):
    rows = _build_comparison(auction, winner=list(auction.legs)[0], reason="buy_it_now")
    assert rows[0]["winner"] is True
    assert all(r["reason"] for r in rows)      # nenhuma linha sem justificativa

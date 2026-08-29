"""
AMARRA · Pilar 02 — sem âncora, sem dado.

O ConversationRelay não expõe timestamps por palavra. Então a evidência
nasce DEPOIS da chamada: gravação da conference -> Deepgram nova-3 com
word-level timing -> casa a citação literal com o índice de palavras.

REGRA: se a citação não é encontrada no áudio, o compromisso NÃO É GRAVADO.
Alucinação vira falha de gravação, nunca dado errado. Isso é feature.
"""
from __future__ import annotations
import os, re, unicodedata
import httpx
from app.db import db

DG_URL = ("https://api.deepgram.com/v1/listen"
          "?model=nova-3&language=multi&punctuate=true&utterances=true&diarize=true")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", "", s)


async def transcribe(recording_url: str) -> list[dict]:
    """Devolve [{word, start, end, confidence}] em segundos."""
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            DG_URL,
            headers={"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}",
                     "Content-Type": "application/json"},
            json={"url": recording_url + ".wav"},
        )
        r.raise_for_status()
        alt = r.json()["results"]["channels"][0]["alternatives"][0]
        return alt.get("words", [])


def anchor(words: list[dict], quote: str) -> tuple[int, int, float] | None:
    """Janela de tempo da citação, em ms. None se a frase não existe no áudio."""
    toks = _norm(quote).split()
    if not toks:
        return None
    norm = [_norm(w["word"]) for w in words]
    n = len(toks)
    for i in range(len(norm) - n + 1):
        if norm[i:i + n] == toks:
            confs = [w.get("confidence", 1.0) for w in words[i:i + n]]
            return (int(words[i]["start"] * 1000),
                    int(words[i + n - 1]["end"] * 1000),
                    min(confs))
    # tolerância: 80% dos tokens em janela do mesmo tamanho
    for i in range(len(norm) - n + 1):
        janela = norm[i:i + n]
        if sum(1 for t in toks if t in janela) / n >= 0.8:
            confs = [w.get("confidence", 1.0) for w in words[i:i + n]]
            return (int(words[i]["start"] * 1000),
                    int(words[i + n - 1]["end"] * 1000),
                    min(confs) * 0.8)
    return None


async def anchor_recording(call_id: str, recording_url: str) -> None:
    words = await transcribe(recording_url)
    call = db.get("calls", call_id)
    gravados, rejeitados = 0, 0

    for p in db.pop_pending(call_id):
        win = anchor(words, p["exact_quote"])
        if win is None:
            rejeitados += 1          # ← e isso é o comportamento CORRETO
            continue
        t0, t1, conf = win
        db.insert("commitments", {
            "call_id": call_id, "operation_id": call["operation_id"],
            "field": p["field"], "value": p["value"], "quote": p["exact_quote"],
            "t_start_ms": t0, "t_end_ms": t1, "confidence": round(conf, 3),
            "state": "confirmed",
        })
        gravados += 1

    print(f"[evidence] {call_id}: {gravados} ancorados, {rejeitados} rejeitados")

"""
AMARRA · FASE 7 — verified

A ligação acabou. Agora o compromisso vira prova.

    gravação → índice de palavras com tempo → âncora por citação
             → dupla âncora (fala original + sim do read-back)
             → recap escrito → fase 'verified'

REGRA: sem âncora, não verifica. Um compromisso que o áudio não sustenta é
marcado como `not_found` e NÃO entra na trilha auditável — o que é
comportamento correto e é a frase que se diz no palco.
"""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.db import db
from app.phases import Phase, PhaseError, advance

router = APIRouter(prefix="/phase7", tags=["fase 7 · verified"])

DG_URL = ("https://api.deepgram.com/v1/listen"
          "?model=nova-3&language=multi&punctuate=true&smart_format=false"
          "&utterances=true&diarize=true&filler_words=true")
MIN_CONFIDENCE = 0.55
FUZZY_THRESHOLD = 0.75      # 75% dos tokens numa janela do mesmo tamanho
BUCKET = os.getenv("SUPABASE_AUDIO_BUCKET", "call-audio")


# ═══════════════════════════════════════════════════════════════════════════
# normalização — o pedaço que faz a âncora funcionar de verdade
# ═══════════════════════════════════════════════════════════════════════════
UNITS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
         6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
HUNDREDS = {1: "one hundred", 2: "two hundred", 3: "three hundred",
            4: "four hundred", 5: "five hundred", 6: "six hundred",
            7: "seven hundred", 8: "eight hundred", 9: "nine hundred"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", s)


def spell_number(n: int, lang: str | None = None) -> str:
    """
    8400 → 'eight thousand four hundred'. Covers hundreds/thousands, the
    range that shows up in freight rate quotes.
    """
    partes = []
    milhares, resto = divmod(n, 1000)
    if milhares:
        if milhares == 1:
            partes.append("one thousand")
        else:
            partes += [UNITS.get(milhares, str(milhares)), "thousand"]
    centenas, resto2 = divmod(resto, 100)
    if centenas:
        partes.append(HUNDREDS.get(centenas, ""))
    if resto2:
        partes.append(UNITS.get(resto2, str(resto2)))
    return " ".join(p for p in partes if p)


def number_variants(text: str, lang: str | None = None) -> list[str]:
    """
    Both forms of the same value. Without this, 'eight thousand four hundred'
    and '8400' never meet — and legitimate commitments get rejected.
    """
    out = [norm(text)]
    for m in re.finditer(r"\b\d[\d.,]*\b", text):
        bruto = m.group()
        try:
            n = int(re.sub(r"[.,]", "", bruto))
        except ValueError:
            continue
        out.append(norm(text.replace(bruto, spell_number(n))))
    return list(dict.fromkeys(out))


# ═══════════════════════════════════════════════════════════════════════════
# transcrição
# ═══════════════════════════════════════════════════════════════════════════
async def fetch_recording(recording_url: str) -> bytes:
    """
    A gravação da Twilio exige autenticação. Passar a URL para o Deepgram
    devolve 401 — é preciso baixar e enviar os bytes.
    """
    auth = (os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    url = recording_url if recording_url.endswith(".wav") else recording_url + ".wav"
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
        for tentativa in range(6):          # a gravação demora a ficar pronta
            r = await c.get(url, auth=auth)
            if r.status_code == 200 and r.content:
                return r.content
            await asyncio.sleep(2 * (tentativa + 1))
        r.raise_for_status()
        return r.content


async def transcribe(audio: bytes) -> list[dict]:
    """[{word, start, end, confidence, speaker}] com tempo em segundos."""
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(DG_URL, content=audio, headers={
            "Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}",
            "Content-Type": "audio/wav"})
        r.raise_for_status()
        alt = r.json()["results"]["channels"][0]["alternatives"][0]
        return alt.get("words", [])


async def publish_audio(call_id: str, audio: bytes) -> str | None:
    """
    O navegador também não consegue autenticar na Twilio. Para o painel
    tocar o trecho exato, o áudio precisa estar em lugar público.
    """
    path = f"{call_id}.wav"
    try:
        db.c.storage.from_(BUCKET).upload(
            path, audio, {"content-type": "audio/wav", "upsert": "true"})
        return db.c.storage.from_(BUCKET).get_public_url(path)
    except Exception as e:
        print(f"[fase7] upload do áudio falhou: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# a âncora
# ═══════════════════════════════════════════════════════════════════════════
def anchor(words: list[dict], quote: str, lang: str | None = None) -> dict | None:
    """
    Acha a citação no índice de palavras. Três passadas, da mais estrita
    para a mais tolerante, e o método usado fica registrado.
    """
    if not words or not (quote or "").strip():
        return None
    idx = [norm(w["word"]) for w in words]

    def janela(i: int, n: int, metodo: str, fator: float = 1.0) -> dict:
        confs = [w.get("confidence", 1.0) for w in words[i:i + n]]
        return {
            "t_start_ms": int(words[i]["start"] * 1000),
            "t_end_ms": int(words[i + n - 1]["end"] * 1000),
            "confidence": round(min(confs) * fator, 3),
            "method": metodo,
            "matched": " ".join(w["word"] for w in words[i:i + n]),
        }

    for variante in number_variants(quote):
        toks = variante.split()
        n = len(toks)
        if not n or n > len(idx):
            continue

        # 1 · exata
        for i in range(len(idx) - n + 1):
            if idx[i:i + n] == toks:
                return janela(i, n, "exact")

        # 2 · numérica: o valor aparece, a fraseologia difere
        nums = [t for t in toks if t.isdigit()]
        if nums:
            for i, t in enumerate(idx):
                if t in nums:
                    return janela(max(0, i - 2), min(5, len(idx) - max(0, i - 2)),
                                  "numeric", 0.9)

        # 3 · fuzzy: 75% dos tokens numa janela do mesmo tamanho
        for i in range(len(idx) - n + 1):
            janela_toks = idx[i:i + n]
            score = sum(1 for t in toks if t in janela_toks) / n
            if score >= FUZZY_THRESHOLD:
                return janela(i, n, "fuzzy", score)

    return None


# ═══════════════════════════════════════════════════════════════════════════
# o processo
# ═══════════════════════════════════════════════════════════════════════════
async def verify_call(call_id: str, recording_url: str) -> dict:
    """
    Disparado pelo webhook /twilio/recording. Ancora tudo que a chamada
    produziu e, se houver ao menos uma âncora, avança a fase.
    """
    call = db.get("calls", call_id)
    op = db.get("operations", call["operation_id"])
    lang = call.get("language") or "en-US"

    audio = await fetch_recording(recording_url)
    words = await transcribe(audio)
    public_url = await publish_audio(call_id, audio)

    db.update("calls", call_id, {
        "recording_url": recording_url,
        "audio_public_url": public_url,
        "transcript": words[:4000],           # o suficiente para o painel
        "transcript_words": len(words),
    })

    rows = db.c.table("commitments").select("*") \
             .eq("call_id", call_id).eq("state", "confirmed").execute().data

    ancorados, rejeitados, fracos = 0, 0, 0
    for c in rows:
        a = anchor(words, c["quote"], lang)

        # ── a segunda âncora: o SIM do read-back ───────────────────────────
        b = anchor(words, c.get("affirmation_quote") or "", lang)

        if a is None:
            db.update("commitments", c["id"], {
                "anchor_state": "not_found", "audio_url": public_url})
            rejeitados += 1
            print(f"[fase7] REJEITADO {c['field']}: citação não está no áudio "
                  f"— {c['quote']!r}")
            continue

        estado = "anchored" if a["confidence"] >= MIN_CONFIDENCE else "low_confidence"
        if estado == "low_confidence":
            fracos += 1
        else:
            ancorados += 1

        db.update("commitments", c["id"], {
            "t_start_ms": a["t_start_ms"], "t_end_ms": a["t_end_ms"],
            "confidence": a["confidence"], "anchor_state": estado,
            "anchor_method": a["method"], "audio_url": public_url,
            "affirmation_t_start_ms": b["t_start_ms"] if b else None,
            "affirmation_t_end_ms": b["t_end_ms"] if b else None,
        })

    resumo = {"call_id": call_id, "anchored": ancorados,
              "low_confidence": fracos, "not_found": rejeitados,
              "words": len(words), "audio_url": public_url}
    print(f"[fase7] {resumo}")

    if ancorados == 0:
        print("[fase7] nada ancorado — a fase NÃO avança, e isso está correto")
        return resumo

    recap = await send_recap(op["id"], call_id)
    resumo["recap"] = recap

    try:
        advance(op["id"], Phase.VERIFIED, trigger="evidence_anchored",
                call_id=call_id,
                payload={**resumo, "mandate_hash":
                         db.mandate(op["id"]).get("mandate_hash")},
                detail=f"{ancorados} campos ancorados no áudio · "
                       f"{rejeitados} rejeitados · recap enviado")
    except PhaseError as e:
        print(f"[fase7] guarda recusou: {e}")
        return resumo

    # Fluxograma completo: com áudio ancorado E recap enviado, a fase 8
    # tem tudo que precisa. Encerra automaticamente pra o painel mostrar
    # DETECTED → ... → VERIFIED → CLOSED numa varredura só.
    try:
        from app.phase8_closed import close_operation
        dossier = await close_operation(op["id"], reason="verified_and_recap_ok")
        resumo["closed"] = True
        resumo["dossier_headline"] = dossier.get("headline")
    except Exception as e:
        print(f"[fase7→fase8] fechamento automático falhou: {e}")

    return resumo


# ═══════════════════════════════════════════════════════════════════════════
# o recap escrito — R3a
# ═══════════════════════════════════════════════════════════════════════════
def build_recap(op: dict, call: dict, commitments: list[dict],
                mandate: dict) -> tuple[str, str]:
    def mmss(ms: int | None) -> str:
        if ms is None:
            return "—"
        return f"{ms // 60000:02d}:{(ms % 60000) // 1000:02d}"

    linhas = []
    # Ancorados no áudio (fase 7 rodou)
    for c in commitments:
        if c["anchor_state"] not in ("anchored", "low_confidence"):
            continue
        linhas.append(
            f"  • {c['field']}: {c['value']}\n"
            f"    dito às {mmss(c['t_start_ms'])} — “{c['quote']}”\n"
            f"    confirmado às {mmss(c.get('affirmation_t_start_ms'))}"
        )

    # Confirmados mas ainda não ancorados (recap pré-processamento de áudio)
    pre_anchor = [c for c in commitments
                  if c.get("state") == "confirmed"
                  and c.get("anchor_state") in ("pending", None)]
    for c in pre_anchor:
        linhas.append(
            f"  • {c['field']}: {c['value']}   (aguardando âncora no áudio)\n"
            f"    citação: “{c['quote']}”"
        )

    rejeitados = [c for c in commitments if c["anchor_state"] == "not_found"]

    assunto = f"[{op['ref']}] Confirmação — {call.get('carrier_name')}"
    corpo = f"""Confirmação de contratação de transporte

Operação:      {op['ref']}
Contêiner:     {op['container']}
Trecho:        {op['origin']} → {op['destination']}
Transportadora:{call.get('carrier_name')} ({call.get('phone')})
Chamada:       {call.get('call_sid')}

ACORDADO
{chr(10).join(linhas) if linhas else '  (nada ancorado)'}

SOB QUAL MANDATO
  {mandate.get('mandate_hash')}
  teto {mandate['max_rate']} {op['currency']} · janela
  {mandate['pickup_from']} a {mandate['pickup_to']}

ÁUDIO
  {call.get('audio_public_url') or '(indisponível)'}
  Cada horário acima aponta para o trecho exato da gravação.
"""
    if rejeitados:
        corpo += ("\nNÃO REGISTRADO\n" + "\n".join(
            f"  • {c['field']}: mencionado, mas não localizado no áudio — "
            f"precisa de confirmação humana" for c in rejeitados))
    corpo += "\n\n— Amarra, assistente de logística da Textiles Pacífico"
    return assunto, corpo


async def send_recap(operation_id: str, call_id: str) -> dict:
    op = db.get("operations", operation_id)
    call = db.get("calls", call_id)
    mandate = db.mandate(operation_id)
    commitments = db.c.table("commitments").select("*") \
                    .eq("call_id", call_id).execute().data
    assunto, corpo = build_recap(op, call, commitments, mandate)

    out = {"email": None}

    # e-mail é o canal confiável do R3a. RECAP_TO aceita comma-separated pra
    # múltiplos destinatários (ex: dono + jurados NextWave). RECAP_CC opcional
    # também vira BCC pra manter compromisso auditável mesmo se algum email
    # cair em spam.
    to_raw = os.getenv("RECAP_TO", "")
    cc_raw = os.getenv("RECAP_CC", "")
    to_list = [e.strip() for e in to_raw.split(",") if e.strip()]
    cc_list = [e.strip() for e in cc_raw.split(",") if e.strip()]
    all_recipients = to_list + [c for c in cc_list if c not in to_list]

    if all_recipients and os.getenv("RESEND_API_KEY"):
        target_display = ", ".join(all_recipients)
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                payload = {
                    "from": os.getenv("RECAP_FROM", "amarra@resend.dev"),
                    "to": to_list or all_recipients,
                    "subject": assunto,
                    "text": corpo,
                }
                if cc_list:
                    payload["cc"] = cc_list
                r = await c.post("https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
                    json=payload)
            ok = r.status_code < 300
            db.insert("recap_deliveries", {
                "operation_id": operation_id, "call_id": call_id, "channel": "email",
                "target": target_display, "subject": assunto, "body": corpo,
                "provider_id": (r.json() or {}).get("id") if ok else None,
                "status": "sent" if ok else "failed",
                "error": None if ok else r.text[:400]})
            out["email"] = "sent" if ok else "failed"
        except Exception as e:
            db.insert("recap_deliveries", {
                "operation_id": operation_id, "call_id": call_id, "channel": "email",
                "target": target_display, "subject": assunto, "body": corpo,
                "status": "failed", "error": str(e)[:400]})
            out["email"] = "failed"

    # SMS removido: e-mail é o canal único do R3a.

    db.c.table("call_briefs").update({
        "recap_sent_to": to or call.get("phone"),
        "recap_sent_at": datetime.now(timezone.utc).isoformat(),
    }).eq("call_id", call_id).execute()

    return out


# ═══════════════════════════════════════════════════════════════════════════
# rotas
# ═══════════════════════════════════════════════════════════════════════════
@router.post("/verify/{call_id}")
async def verify(call_id: str, bg: BackgroundTasks):
    """Reprocessa a evidência de uma chamada. Útil no ensaio."""
    call = db.get("calls", call_id)
    if not call.get("recording_url"):
        raise HTTPException(409, "gravação ainda não disponível")
    bg.add_task(verify_call, call_id, call["recording_url"])
    return {"queued": True}


@router.get("/evidence/{operation_id}")
async def evidence(operation_id: str):
    """
    O que o painel usa para tocar o trecho exato ao clicar num compromisso.
    """
    rows = db.c.table("commitments").select("*") \
             .eq("operation_id", operation_id).order("id").execute().data
    return {
        "operation_id": operation_id,
        "anchored": [{
            "field": r["field"], "value": r["value"], "quote": r["quote"],
            "audio_url": r["audio_url"],
            "said": {"from_ms": r["t_start_ms"], "to_ms": r["t_end_ms"]},
            "confirmed": {"from_ms": r.get("affirmation_t_start_ms"),
                          "to_ms": r.get("affirmation_t_end_ms")},
            "confidence": r["confidence"], "method": r["anchor_method"],
            "mandate_hash": r.get("mandate_hash"),
        } for r in rows if r["anchor_state"] in ("anchored", "low_confidence")],
        "rejected": [{"field": r["field"], "value": r["value"], "quote": r["quote"],
                      "why": "citação não localizada no áudio"}
                     for r in rows if r["anchor_state"] == "not_found"],
    }


@router.get("/recaps/{operation_id}")
async def recaps(operation_id: str):
    return db.c.table("recap_deliveries").select("*") \
             .eq("operation_id", operation_id).order("id").execute().data

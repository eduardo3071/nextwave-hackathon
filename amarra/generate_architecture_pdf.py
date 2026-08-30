"""
Gera ARCHITECTURE.pdf — diagrama de arquitetura em uma página A3 landscape.
Uso: python generate_architecture_pdf.py
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.patches as mp
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


def box(ax, xy, wh, label, sub=None, color="#0b1f2a", edge="#4de3d4",
        text_color="#e6faf7", radius=0.15):
    x, y = xy
    w, h = wh
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                 boxstyle=f"round,pad=0.02,rounding_size={radius}",
                                 fc=color, ec=edge, lw=1.5))
    ax.text(x + w/2, y + h - 0.25, label, ha="center", va="top",
            fontsize=9, color=text_color, weight="bold")
    if sub:
        ax.text(x + w/2, y + h - 0.55, sub, ha="center", va="top",
                fontsize=7, color="#8bc4bb", family="monospace")


def phase_pill(ax, xy, wh, num, name, color="#0f3d3a"):
    x, y = xy
    w, h = wh
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                 boxstyle="round,pad=0.02,rounding_size=0.1",
                                 fc=color, ec="#4de3d4", lw=1))
    ax.text(x + w/2, y + h/2 + 0.08, f"{num}", ha="center", va="center",
            fontsize=8, color="#4de3d4", weight="bold")
    ax.text(x + w/2, y + h/2 - 0.13, name, ha="center", va="center",
            fontsize=6.5, color="#e6faf7", family="monospace")


def arrow(ax, start, end, label=None, color="#4de3d4", style="-|>",
          rad=0.0, lw=1.2, offset=(0, 0)):
    ax.add_patch(FancyArrowPatch(start, end,
                                  arrowstyle=style, mutation_scale=12,
                                  color=color, lw=lw,
                                  connectionstyle=f"arc3,rad={rad}"))
    if label:
        mx = (start[0] + end[0]) / 2 + offset[0]
        my = (start[1] + end[1]) / 2 + offset[1]
        ax.text(mx, my, label, fontsize=6, color=color,
                ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc="#0d1826", ec="none"))


def main():
    fig, ax = plt.subplots(figsize=(16.5, 11.7))  # A3 landscape in inches
    ax.set_xlim(0, 16.5)
    ax.set_ylim(0, 11.7)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("#0d1826")
    ax.set_facecolor("#0d1826")

    # ── Title
    ax.text(8.25, 11.2, "AMARRA · Arquitetura", ha="center", fontsize=18,
            color="#4de3d4", weight="bold")
    ax.text(8.25, 10.85,
            "Agente de voz para negociação de frete · NextWave 2026 · Desafio 04",
            ha="center", fontsize=10, color="#8bc4bb")

    # ═════ FRONTEND ROW ═════
    box(ax, (0.5, 9.2), (15.5, 1.3),
        "FRONTEND · https://nextwave-hackathon.lovable.app",
        sub="Vite + React + TanStack Router · mobile-first (430px) · Supabase Realtime",
        color="#132a45", edge="#7dd3fc", radius=0.2)

    # Frontend components
    comps = ["Top bar\n(countdown)", "Phase rail", "Call dock", "Quote table",
             "Escalation\npanel", "Dossier view", "Recap card"]
    for i, c in enumerate(comps):
        x = 0.9 + i * 2.13
        ax.add_patch(FancyBboxPatch((x, 9.4), 1.95, 0.6,
                                     boxstyle="round,pad=0.02,rounding_size=0.08",
                                     fc="#0e1e33", ec="#7dd3fc", lw=0.8))
        ax.text(x + 0.98, 9.7, c, ha="center", va="center",
                fontsize=7, color="#e0f2fe")

    # ═════ BACKEND ═════
    box(ax, (0.5, 5.3), (15.5, 3.5),
        "BACKEND · FastAPI + uvicorn (via ngrok  clique-lukewarm-frail.ngrok-free.dev)",
        sub="",
        color="#1a2b2a", edge="#4de3d4", radius=0.2)

    ax.text(8.25, 8.3, "9 routers + 3 endpoints Twilio + WebSocket /ws",
            ha="center", fontsize=8, color="#8bc4bb", family="monospace")

    # Endpoints boxes
    ax.text(1.2, 7.85, "REST /demo/*", fontsize=8, color="#4de3d4", weight="bold")
    demo_eps = ["/demo/scenario/full", "/demo/dial-market", "/demo/call-me",
                "/demo/call-judge/{id}", "/demo/recap/{op_id}",
                "/demo/test-email", "/demo/scenario/status/{ref}"]
    for i, ep in enumerate(demo_eps):
        ax.text(1.2, 7.55 - i*0.2, ep, fontsize=6.5,
                color="#c9e6e0", family="monospace")

    ax.text(5.7, 7.85, "REST /phaseN/*", fontsize=8, color="#4de3d4", weight="bold")
    phase_eps = ["/phase1/detect", "/phase2/issue/{op_id}",
                 "/phase3/open", "/phase5/release/{auc_id}",
                 "/phase6/commitments/{op_id}", "/phase7/verify/{call_id}",
                 "/phase8/close/{op_id}", "/phase8/dossier/{op_id}",
                 "/disruption/report/{op_id}"]
    for i, ep in enumerate(phase_eps):
        ax.text(5.7, 7.55 - i*0.2, ep, fontsize=6.5,
                color="#c9e6e0", family="monospace")

    ax.text(10.2, 7.85, "Twilio webhooks", fontsize=8, color="#4de3d4", weight="bold")
    tw_eps = ["POST /twiml/inbound     (call comes in)",
              "POST /twiml/agent       (agent leg TwiML)",
              "POST /twilio/recording  (recording done)",
              "POST /twilio/conference (join/leave)",
              "POST /twilio/status     (call state)",
              "WS   /ws                (ConversationRelay)"]
    for i, ep in enumerate(tw_eps):
        ax.text(10.2, 7.55 - i*0.2, ep, fontsize=6.5,
                color="#c9e6e0", family="monospace")

    # 8-phase spine
    spine_y = 5.7
    phases_spine = [
        ("1", "detected"), ("2", "mandate_issued"), ("3", "market_open"),
        ("4", "negotiating"), ("5", "reserved"), ("6", "committed"),
        ("7", "verified"), ("8", "closed"),
    ]
    for i, (n, name) in enumerate(phases_spine):
        x = 0.9 + i * 1.85
        phase_pill(ax, (x, spine_y), (1.7, 0.6), n, name)
        if i < 7:
            arrow(ax, (x + 1.72, spine_y + 0.3),
                  (x + 1.83, spine_y + 0.3), color="#4de3d4", style="-|>", lw=0.8)

    ax.text(8.25, 6.4, "SPINE DE 8 FASES", ha="center", fontsize=8,
            color="#8bc4bb", weight="bold")

    # Branches
    ax.text(8.25, 5.5, "desvios: disrupted → renegotiating → escalated → resolved",
            ha="center", fontsize=6.5, color="#f59e0b", style="italic")

    # ═════ EXTERNAL SERVICES ═════
    services = [
        ("TWILIO", "Voice + ConversationRelay\nCalls · Conferences · Recording",
         "#5a1a1a", "#f87171"),
        ("DEEPGRAM", "nova-3 ASR (audio → words\nwith timestamps)",
         "#1a3a5a", "#7dd3fc"),
        ("OPENAI", "gpt-4.1-mini\n(negotiation reasoning)",
         "#1a3a2a", "#86efac"),
        ("RESEND", "Email SMTP\n(recap R3a)",
         "#3a2a1a", "#fbbf24"),
    ]
    for i, (name, sub, bg, edge) in enumerate(services):
        x = 0.5 + i * 3.9
        box(ax, (x, 3.2), (3.7, 1.5), name, sub, color=bg, edge=edge, radius=0.15)

    # ═════ SUPABASE ═════
    box(ax, (0.5, 0.6), (15.5, 2.3),
        "SUPABASE · Postgres + Realtime + Storage",
        sub="RLS off para demo (permissivo em leitura, service_role escreve)",
        color="#2d1a3a", edge="#a78bfa", radius=0.2)

    # Tables
    tables = [
        ("operations", "phase, clock_state,\nfree_time_ends"),
        ("mandates", "mandate_hash, ladder,\nbreak_even, band"),
        ("auctions", "reserved_by lock,\ndeadlines"),
        ("auction_quotes", "R7 comparison\n(auditable)"),
        ("calls", "leg_role, phone,\naudio_public_url"),
        ("utterances", "speaker, text,\nt_ms, interrupted"),
        ("policy_events", "decision, amount,\nmandate_hash"),
        ("commitments", "field, quote,\nt_start_ms, audio_url"),
        ("read_backs", "token, slots,\noutcome"),
        ("escalations", "brief, computation,\nresolution"),
        ("recap_deliveries", "channel=email,\nstatus, target"),
        ("dossiers", "financial, timeline,\nheadline"),
    ]
    for i, (t, sub) in enumerate(tables):
        col = i % 6
        row = i // 6
        x = 0.75 + col * 2.55
        y = 1.85 - row * 0.7
        ax.add_patch(FancyBboxPatch((x, y - 0.05), 2.4, 0.55,
                                     boxstyle="round,pad=0.01,rounding_size=0.06",
                                     fc="#1e0a2e", ec="#a78bfa", lw=0.7))
        ax.text(x + 1.2, y + 0.33, t, ha="center", va="center",
                fontsize=7, color="#e0d4ff", weight="bold", family="monospace")
        ax.text(x + 1.2, y + 0.08, sub, ha="center", va="center",
                fontsize=5.5, color="#b8a6d9", family="monospace")

    # Storage
    ax.text(15.5 - 1, 2.6, "Storage:\ncall-audio bucket",
            ha="right", fontsize=6, color="#a78bfa",
            family="monospace", style="italic")

    # ═════ ARROWS between layers ═════
    # Frontend → Backend (actions)
    arrow(ax, (5, 9.2), (5, 8.8), "POST actions\n(HTTPS)", color="#7dd3fc")
    # Backend → Frontend (via Realtime)
    arrow(ax, (11.5, 2.9), (11.5, 9.2),
          "Realtime\npub/sub", color="#a78bfa", rad=-0.3)

    # Backend → external services
    arrow(ax, (2.5, 5.3), (2.5, 4.7), None, color="#f87171")
    arrow(ax, (6.5, 5.3), (6.5, 4.7), None, color="#7dd3fc")
    arrow(ax, (10.5, 5.3), (10.5, 4.7), None, color="#86efac")
    arrow(ax, (14, 5.3), (14, 4.7), None, color="#fbbf24")

    # External → Backend (webhooks/callbacks)
    arrow(ax, (2, 4.7), (2, 5.3), "webhooks",
          color="#f87171", style="-|>", lw=0.8)

    # Backend → Supabase (write)
    arrow(ax, (4, 3.2), (4, 2.9), "service_role\nwrite", color="#a78bfa")
    # Supabase → Frontend (realtime)
    # already drawn above

    # Footer
    ax.text(8.25, 0.25,
            "23 tabelas · 9 fases (8 espinha + 4 desvios) · 951 pytest verdes · "
            "13 endpoints REST + 6 webhooks Twilio + 1 WebSocket",
            ha="center", fontsize=7, color="#8bc4bb", family="monospace")

    plt.savefig("amarra/ARCHITECTURE.pdf", format="pdf",
                facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.3)
    plt.savefig("amarra/ARCHITECTURE.png", format="png",
                facecolor=fig.get_facecolor(), bbox_inches="tight",
                pad_inches=0.3, dpi=180)
    print("OK amarra/ARCHITECTURE.pdf + ARCHITECTURE.png gerados")


if __name__ == "__main__":
    main()

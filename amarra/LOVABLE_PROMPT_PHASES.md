# Prompt incremental para o Lovable

**Não reconstrua o app.** Cole isto como uma nova instrução sobre o que já existe
em nextwave-hackathon.lovable.app.

---

Add a **phase rail** to the Amarra dashboard. Two new Supabase sources:
`operations.phase` (current phase) and `phase_events` (append-only timeline).
Subscribe to both with Realtime, same as the other tables.

## The spine — a horizontal progress rail, directly under the top bar

Eight steps, always in this order, always all visible:

`detected → mandate issued → market open → negotiating → reserved → committed → verified → closed`

- **Completed** steps: filled, with the elapsed time inside them, from
  `phase_events.ms_in_previous`, formatted as `1m 12s`.
- **Current** step: pulsing outline, larger, and the step's caption
  (`phase_events.detail`) shown beneath the whole rail in a single line.
- **Future** steps: dimmed outline only.
- Connect them with a line that fills as it progresses.

This rail is the second most important element on screen, after the free-time
countdown. Someone at the back of the room should read the current phase in
under a second.

## The branches — they interrupt the spine, they do not replace it

Four branch phases: `disrupted`, `renegotiating`, `escalated`, `resolved`.

When `operations.phase` is one of these:
- Keep the spine visible and **freeze the current spine step in place** — do not
  advance it. The spine step stays where it was.
- Drop a **branch card below the rail**, visually hanging off the frozen step,
  with the branch phase name and its `detail`.
- Colors: `disrupted` amber, `renegotiating` blue, `escalated` red and pulsing,
  `resolved` green.
- On `escalated`, the branch card expands into the full decision brief and
  renders `payload` as the comparison — option on-time vs option late, each with
  rate, demurrage and total, then the delta, then a red line
  **"exceeds mandate by $X"**. Approve / Reject buttons POST to
  `${VITE_BACKEND_URL}/escalate/{call_id}/resolve`.
- When the phase returns to the spine, collapse the branch card into a small
  marker that stays attached to that spine step. **The detour must remain
  visible in the finished rail** — it is the most interesting thing that
  happened, and the jury will ask about it.

## The timeline — right rail, above the commitments list

Reverse-chronological list of `phase_events`. Each row: the phase label, the
`trigger` in monospace and dimmed, the `detail`, and the time. Rows for branch
phases get their color. New rows slide in.

The `trigger` field matters: it is the machine event that caused the transition
(`lock_acquired`, `above_max_rate`, `inbound_problem_reported`). Show it
verbatim, in monospace — it is evidence that the phase came from the system
and not from a script.

## Terminal states

- `closed`: the rail fills entirely in green, and the free-time countdown
  freezes with a "closed with Xh to spare" label instead of continuing.
- `failed`: rail turns red at the point it stopped, with the `detail` as reason.

## Rules
- Never invent a phase client-side. The rail renders only what the database says.
- If `phase_events` is empty, show the rail with all steps dimmed and the caption
  "waiting for an operation".
- Monospace and `tabular-nums` for all durations.

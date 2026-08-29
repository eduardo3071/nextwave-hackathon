# NextWave-Hackathon

# Prompt para o Lovable




Cole isto no Lovable. Depois conecte o Supabase pelo botão nativo e cole a

`SUPABASE_URL` + a **anon key** (nunca a service_role).




---




Build a real-time operations dashboard called **Amarra**, for a voice AI agent

that negotiates freight over the phone. Dark, dense, control-room aesthetic —

this is monitored during a live phone negotiation, not browsed.




**Data comes from Supabase Realtime. Subscribe, never poll.**

Tables: `operations`, `mandates`, `auctions`, `calls`, `utterances`,

`policy_events`, `commitments`, `escalations`.




## Layout




**Top bar** — fixed:

- Operation ref, container, origin → destination.

- **A live countdown to `operations.free_time_ends`**, big, monospace. Under it:

  "after this: $X/day demurrage". Turns amber under 6h, red under 2h.

  This is the emotional center of the screen — make it the largest element.

- Mandate chips: `target` / `max` / pickup window. Max is styled as a hard

  boundary, not a suggestion.

- Two counters: **POLICY BLOCKS** and **COMMITMENTS ANCHORED**. Policy blocks

  flashes red when it increments.




**Main area — three call columns side by side**, one per row in `calls` where

`auction_id` matches the running auction. Each column:

- Carrier name, phone, status pill (dialing / live / escalated / done).

  A live call gets a pulsing dot.

- **Live transcript**: `utterances` for that `call_id`, newest at the bottom,

  auto-scroll. Agent lines and counterparty lines visually distinct.

  Rows with `interrupted = true` get a small "interrupted" marker.

- **Policy strip** under the transcript: each `policy_events` row as a compact

  line — `ask → decision`. `allow` in green, `deny` in amber, `block` in red,

  `escalate` in blue. Hovering shows the `reason`.

- When a call ends because another won, fade the column and stamp it "released".




**Right rail:**

- **Quote comparison table** — carrier, final ask, rounds, winner flag, reason.

  The winning row is highlighted. This is an audit artifact; make it look like one.

- **Commitments list** — for each: field, value, state, and the quote in italics

  with its `[mm:ss–mm:ss]` window. **Clicking a commitment plays that exact slice

  of `calls.recording_url`** using an `<audio>` element with `currentTime` set

  from `t_start_ms`, pausing at `t_end_ms`. This is the single most important

  interaction on the page — make it obvious and satisfying.

- **Escalation panel** — appears when an `escalations` row arrives. Shows the

  `brief`, and renders `computation` as a comparison: option on-time vs option

  late-with-demurrage, with the delta, and a red line "exceeds mandate by $X".

  Two buttons: "Approve" and "Reject". Both POST to

  `${VITE_BACKEND_URL}/escalate/{call_id}/resolve`.




**Bottom:** an "Start auction" button that POSTs to

`${VITE_BACKEND_URL}/auction/start` with the operation ref and the carrier list.




## Rules

- Everything animates in from realtime events. Nothing is fetched on an interval.

- Monospace for all numbers, times and money. `tabular-nums`.

- No placeholder or mock data — empty states say what will appear.

- Two env vars: `VITE_BACKEND_URL`, plus the Supabase connection.

- Must be readable from the back of a room on a projector: large type,

  high contrast, no thin greys.

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://nextwave-hackathon.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/f9a1a643-57ba-4dd3-ae99-4819dff36a19).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```

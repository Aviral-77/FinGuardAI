# FinGuard AI — Demo Specification

Companion to `CLAUDE.md`. This file defines exactly what the demo does and how it is driven. Where this file and `CLAUDE.md` disagree, **this file wins** — it reflects the latest decisions.

---

## Core change from the earlier plan

The demo is **API-driven, not auto-playing**. Nothing happens until a trigger is fired. The presenter controls the pace by hitting endpoints (via Postman, curl, or buttons in a hidden control strip), and the UI reacts live over WebSocket.

This matters because the story is told in three deliberate beats, each with a pause for narration. An auto-playing animation cannot do that.

**Theme is light.** White/near-white background, dark text, coloured nodes. This is a change from the earlier dark mockup — it reads as a bank tool rather than a hacker console, and the coloured nodes carry far more contrast against white.

---

## The three beats

### Beat 0 — Idle (before any trigger)

- White canvas with ambient transactions flowing between grey nodes: small amounts, normal accounts, nothing flagged.
- Dashboard right panel shows an empty state: "No accounts under investigation."
- A counter somewhere subtle: accounts monitored, transactions today.
- **Presenter says:** "This is a normal afternoon at the bank."

### Beat 1 — The victim transfer (first API call)

**Trigger:** `POST /api/transaction` with a large transfer from a customer to Account A.

**What happens on screen:**
- A new node appears for **Account A** with an entrance animation, and turns **amber/yellow**.
- An edge is drawn from the sender to Account A, thicker than ambient edges, labelled with the amount.
- The dashboard populates for Account A: current score, and the rules that fired with their point values.
- **Crucially: the recommended action is "Monitor only" — no freeze, no block.** The score sits in the 31–50 band. There is no mule pattern yet, only an unusual transfer.
- Dashboard shows an explicit line: *"Insufficient evidence for action. Watching for onward movement."*

**Presenter says:** "One large transfer to a valid account. We've flagged it as unusual — but a single transfer isn't fraud. Today's systems stop here, and so do we. For now."

This beat is the most important one in the whole demo. It proves the system does not cry wolf.

### Beat 2 — The fan-out (second API call)

**Trigger:** `POST /api/transaction/batch` — Account A sends the money onward to 4–6 mule accounts in quick succession, and those onward to a second tier.

**What happens on screen:**
- New nodes appear for each mule account, edges animating outward from Account A.
- Nodes shift **amber → red** one by one as their scores cross thresholds.
- Score chips pop above each node as rules fire (`M1 +25`, `M2 +20`, `G2 +20`…), then fade.
- Account A's score climbs visibly in the dashboard — animate the number counting up, don't just replace it.
- When the cluster is detected, a red halo/boundary is drawn around the whole ring with a label: **"MULE RING DETECTED · N accounts · ₹X in motion"**.
- The dashboard now shows the full case: score in the 86–100 band, every triggered rule, the generated explanation, and the recommended action **Temporary block / freeze**.

**Presenter says:** "Now the money splits. Watch the scores climb — and the ring assemble itself."

### Beat 3 — Act

Now, and **only now**, action controls become enabled in the dashboard:

- **Freeze accounts** — blocks the flagged accounts from further transactions
- **Report** — files the case
- **Download report** — produces the full PDF (see below)

**After freeze:** flagged nodes get a lock icon, the header status changes to "RING CONTAINED", and any further `POST /api/transaction` involving a frozen account is **rejected** with a clear response — this is important, because it proves the freeze is real and not cosmetic. Fire one more transfer attempt on stage to show it bouncing.

---

## API contract

Keep it small and demo-friendly. All endpoints return the updated state so the presenter can see what happened.

```
POST /api/transaction
{
  "from_account": "AC8821",
  "to_account": "AC4471",
  "amount": 1000000,
  "channel": "IMPS",
  "device_id": "dev_a91",       // optional
  "timestamp": "auto if omitted"
}
→ 200 { transaction_id, accepted: true, scores_updated: [...] }
→ 409 { accepted: false, reason: "Account AC4471 is frozen" }
```

```
POST /api/transaction/batch
{ "transactions": [ {...}, {...} ] , "stagger_ms": 400 }
```
Sends them in sequence with a delay so the fan-out animates rather than appearing all at once.

```
POST /api/account/{id}/freeze     → locks the account
POST /api/account/{id}/report     → files the case
GET  /api/account/{id}/report.pdf → downloads the full report
GET  /api/account/{id}            → current score, rules, explanation
POST /api/demo/reset              → clears everything back to Beat 0
```

`POST /api/demo/reset` is essential. You will run this demo many times.

**Also provide preset triggers** so the presenter never has to type JSON on stage — either a small hidden control strip in the UI, or a `demo/` folder of curl scripts: `01-victim-transfer.sh`, `02-fanout.sh`, `03-blocked-attempt.sh`.

---

## Scoring must be visible on the UI

This is a hard requirement — the score is the product.

**On each node:** a small score badge attached to the node, colour-coded by band. It should update live, not on refresh.

**In the dashboard, for the selected account:**
- Large score number with the band name beside it (e.g. `87 / 100 — Temporary block / freeze`)
- A visual band indicator showing where the score sits across all five bands
- **A breakdown table:** every triggered rule as a row — rule code, plain-English name, points contributed, and the evidence that triggered it (e.g. "84% of balance moved within 6 minutes"). The points must sum visibly to the total.
- Timestamp of when each rule fired

**Colour bands (use consistently on nodes, badges and dashboard):**

| Score | Band | Colour |
|---|---|---|
| 0–30 | Allow | grey / neutral |
| 31–50 | Enhanced monitoring | amber `#D9A441` |
| 51–70 | Step-up authentication | orange `#E08A1E` |
| 71–85 | Manual fraud review | deep orange |
| 86–100 | Temporary block / freeze | red `#C1121F` |

---

## The downloadable report

Wherever the flagging reason is shown, there is a **Download full report** button producing a PDF.

**Contents:**
1. **Header** — case reference, account ID, generation timestamp, final score and band
2. **Executive summary** — the generated plain-English narrative of what happened
3. **Score breakdown table** — every rule, its condition, points, evidence, and time fired, summing to the total
4. **Network summary** — accounts in the ring, their individual scores, total value in motion, and how they connect
5. **Transaction appendix** — the transactions that triggered each rule, with timestamps and amounts
6. **Recommended action and audit trail** — what the system recommended, who actioned it, when

This is a genuine differentiator, so make it look like a bank document, not a debug dump: clean typography, the FinGuard mark, page numbers, and a footer noting it was auto-generated with the case reference and timestamp.

Generate server-side (ReportLab or WeasyPrint). Do not build it client-side.

---

## Visual design (light theme)

- **Background:** `#F8FAFC`. Canvas is white with a very light grid or nothing at all.
- **Ambient nodes/edges:** light grey `#C3CBDD`, thin edges, low visual weight.
- **Victim/unusual node:** amber `#D9A441`.
- **Flagged/ring nodes:** red `#C1121F`, with the ring boundary a dashed red on a very light red wash.
- **Frozen nodes:** teal `#17A398` lock badge.
- **Text:** ink `#0B2545`. **Muted:** `#5B6780`.
- **Fonts:** Inter for UI, IBM Plex Mono for account IDs, amounts and timestamps.
- Node size scales with money volume. Edge thickness scales with amount.
- Animate transitions (colour changes, score counts, edge draws) over 300–600ms — the movement is what makes it feel live.

---

## What must be true for the demo to work on stage

- **Deterministic.** Same triggers → same result, every time.
- **Reset in one call.** No restarting the server between runs.
- **No live model calls.** Case summaries are generated from templates with real case values slotted in (see below). Nothing can hang, time out or cost money mid-demo.
- **Freeze actually blocks.** Rejecting a subsequent transfer attempt is a scripted beat, not an edge case.
- **No console errors visible.** If something fails, fail silently to a cached state.

---

## Case summaries: templates, not a model

The dashboard shows a plain-English paragraph explaining why the account was flagged. **Generate this from templates**, not an LLM. It renders instantly, never fails, and reads identically on screen.

Build a small composer that assembles sentences from the rules that actually fired, filling in real values from the case:

```
M1 → "moved {pct}% of the incoming balance out within {minutes} minutes"
M2 → "received funds from {n} unrelated accounts in the past {days} days"
G2 → "shares a device fingerprint with {n} other flagged accounts"
S1 → "the beneficiary was added {hours}h before a transfer {x}× its usual value"
G3 → "sits inside a cluster of {n} accounts moving money on near-identical timing"
```

Composed output, for example:

> Account AC4471 received ₹9,00,000 from a counterparty it has never transacted with, then moved 84% of the balance out within 6 minutes across four beneficiaries, each below the reporting threshold. Three of those beneficiaries share a device fingerprint with this account. The pattern is consistent with a mule account layering proceeds from a social-engineering scam.

Order the clauses by points contributed, highest first, and close with a fixed classification line chosen by the highest-scoring rule category (mule layering / scam indicator / account takeover). If asked, this is generated from the case facts — which is exactly what it is.

**No ML model in the demo.** The rules do the detection and the score does the talking. An unsupervised anomaly model adds nothing visible on screen and is not worth build time.

---

## Build order for this demo

1. `POST /api/transaction` + rule engine + scoring + WebSocket push
2. Light-theme canvas with nodes/edges appearing on transaction events
3. Dashboard with live score, band and rule breakdown
4. Batch endpoint + fan-out animation + ring detection
5. Template-based case summary composer
6. Freeze / report actions, and rejection of transactions on frozen accounts
7. PDF report generation
8. Preset trigger scripts and `POST /api/demo/reset`
9. Ambient background traffic (last — it is decoration)

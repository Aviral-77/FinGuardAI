# FinGuard AI — Project Brief

Paste this into a fresh repo as `CLAUDE.md` before starting work. It is the single source of truth for what we are building and why.

---

## 1. What this is

A fraud detection console for retail banking, built for the Coforge TechCon 2026 hackathon (use case #47, BFS / Digital Banking).

**Team:** 2 people. **Registration:** 276-FinGuard AI.
**Deadline:** evaluations begin 14 August 2026. Semi-finals 9–10 September. Finale 16 September.

**The pitch in one line:** banks see every transaction but never see the network those transactions form, so mule rings stay invisible until the money is gone.

## 2. The problem we are solving

A scam victim is tricked into transferring money. It lands in an account rented from an ordinary person — a *mule*, often a student or gig worker paid a few thousand rupees. From there the money splits across a dozen accounts, each amount kept below reporting thresholds, hops onward to break the trail, and exits as cash or crypto. After roughly 72 hours recovery is effectively impossible.

There are two failures, and the product has one half for each:

**Failure 1 — detection.** Banks score transactions one at a time. Every hop is individually legitimate, so the ring never surfaces. *Our answer: the graph layer.*

**Failure 2 — investigation.** Even when an alert fires it arrives as an account ID, a score and a rule number. The analyst manually pulls history, traces links and writes the case — 30–45 minutes per alert, hundreds queued daily. *Our answer: the investigator copilot.*

## 3. What we are building

Three components. **The detection is entirely deterministic — that is the point, not a shortcut.**

| Stage | Component | Job |
|---|---|---|
| SEE | Graph layer | Live account-to-account graph; rings appear as shapes |
| SCORE | Rule engine | 10 fraud rules score every account in real time |
| ACT | Investigator copilot | Composes the case file and recommends one named action |

**Non-negotiable design rule:** the score and the action are always computed by rules and thresholds, never inferred. Every point in a score must trace back to a named rule. This is what makes the output auditable, and it is our core differentiator — do not "improve" this by adding a model that decides things.

The copilot's case narrative is **generated from templates** filled with real case values, not from a model. It renders instantly, cannot fail live, and reads identically on screen. See `DEMO-SPEC.md` for the composer design.

No ML model in the demo. An unsupervised anomaly layer adds nothing visible on screen and is not worth the build time.

## 4. The rules (implement all ten)

Each fires independently and adds points to a running account score.

**Mule behaviour**
- **M1 Rapid fund movement** — funds credited, then >80% of balance transferred out within 24h → **+25**
- **M2 Multiple source accounts** — receives from >5 unique accounts in 7 days, average incoming amount within ±20% range → **+20**
- **M3 Circular transactions** — funds move among 3+ connected accounts and return to the originating network within 72h → **+30**

**Scam indicators**
- **S1 New beneficiary, high value** — beneficiary added, first transfer >5× customer's average transfer value → **+20**
- **S2 Sudden behavioural change** — transfer location/device differs from history AND value >3× historical average → **+25**
- **S3 Elderly / vulnerable pattern** — multiple high-value transfers, new payee added within previous 48h → **+15**

**Account takeover**
- **A1 Device change + transfer** — new device login + password reset within 24h + outbound transfer → **+30**
- **A2 Failed logins** — 5 failed logins, then successful login from a different IP/device → **+20**

**Graph / network**
- **G1 High-risk proximity** — account connected to a known suspicious account within 2 hops → **+15**
- **G2 Shared identifiers** — multiple accounts share a device fingerprint, phone number or address → **+20**
- **G3 Emerging ring** — cluster of >10 accounts with similar transaction timing and routing → **+35**

**Score → action mapping (drives the whole product):**

| Score | Action |
|---|---|
| 0–30 | Allow transaction |
| 31–50 | Enhanced monitoring |
| 51–70 | Step-up authentication |
| 71–85 | Manual fraud review |
| 86–100 | Temporary block / freeze |

No alert may leave the system without a named next step attached.

## 5. Data

Generate it. Public AML datasets carry transactions only — S1, S2, A1, A2 and G2 need device fingerprints, login events, password resets, IPs and beneficiary-addition timestamps that none of them have.

**Four tables:**
- `accounts` — id, open_date, dormancy_flag, age_band, phone, address, kyc_date
- `transactions` — from_account, to_account, amount, timestamp, channel
- `device_sessions` — account, device_fingerprint, ip, login_result, timestamp, password_reset_flag
- `beneficiaries` — account, payee, added_timestamp

**Calibration:** shape amount distributions, transfer frequencies and account-degree against IBM's open *Transactions for Anti Money Laundering* dataset (Kaggle, HI-Small variant). We cite this as our benchmark, so it needs to actually be done.

**Demo slice:** 200–300 accounts. A 5M-row graph is unreadable and the ring disappears into noise.

## 6. The demo scenario (build to this)

Pre-generated and deterministic — the same ring must form identically on every run. No live randomness.

**Main scenario, rules firing in this order so the score visibly climbs:**

1. **S3** (+15) — elderly customer, new payee added within 48h
2. **S1** (+20) — first transfer to that payee is >5× his average
3. **M1** (+25) — receiving account pushes 80% out within 24h
4. **M2** (+20) — that account took money from 6 unrelated senders this week
5. **G2** (+20) — three mule accounts share a device fingerprint
6. **G3** (+35) — 11-account cluster with matching timing

The victim's own account lands around 35 (Enhanced Monitoring — he is a victim, not a suspect). The primary mule crosses 65. The ring node crosses **86 → Temporary Block / Freeze**. That crossing is the climax.

**Second scenario (~30s), to prove all four rule categories:** new device login → password reset → immediate transfer → A1 (+30) → Temporary Transaction Hold.

**The proof-point toggle:** a "rules-only view" switch that reverts the graph to what a conventional per-transaction system would have caught in the same window — one isolated alert, ring invisible. This is the single most persuasive element in the demo. Build it.

## 7. The UI

One screen, three zones:
- **Left (~320px):** live transaction feed, trading-terminal styled — timestamp, from, to, amount
- **Centre:** force-directed account graph. Grey noise, gold victim edge, red ring. Score chips pop above nodes as rules fire. Red halo + label when the ring is detected.
- **Right (~400px):** investigator copilot — empty until a node is selected, then score, case summary, triggered rules with point values, recommended action, Approve / Escalate buttons.

Clicking **Approve** locks the accounts, updates the header to "RING FROZEN", and shows a confirmation. That is the closing beat of the demo.

A working visual mockup exists (`finguard-fraud-room.html`) — scripted HTML with no backend. Use it as the design reference; it is what the real thing should look like.

**Palette:** ink `#0B2545`, panel `#0F2547`, teal `#17A398` (AI / positive), gold `#D9A441` (victim / accents), alert red `#C1121F` (ring / freeze), muted `#7E93B4`. Fonts: Inter for UI, IBM Plex Mono for data.

## 8. Stack

All open source — the hackathon grades on this.

- **Backend:** Python, FastAPI. Scores incoming transactions through the rule engine, streams updates over WebSocket.
- **Graph:** NetworkX (2-hop traversal for G1, Louvain community detection + centrality for G3). Neo4j only if there is spare time.
- **Case narrative:** template composer — sentence fragments per rule, filled with real case values, ordered by points contributed. No model call.
- **PDF:** ReportLab or WeasyPrint, generated server-side.
- **Frontend:** React + react-force-graph (or Cytoscape.js).
- **Data generation:** Faker.

## 9. Build order

See `DEMO-SPEC.md` for the authoritative build order. In summary:

1. Data generator producing all four tables with the ring pre-planted
2. Rule engine — all 10 rules, unit-tested against hand-built fixtures
3. Graph layer + the two graph rules (G1, G3)
4. FastAPI transaction endpoint streaming over WebSocket
5. React UI: canvas + dashboard, nodes appearing and scoring live
6. Template case-summary composer
7. Freeze / report actions, PDF report, preset trigger scripts

## 10. Working principles

- **Design the demo before the architecture.** Build only what the 3-minute story needs. Teams lose hackathons by building 80% of a system and demoing 20% of a story.
- **Determinism over realism.** Pre-generate everything. The ring must form the same way every run.
- **Make the action verb prominent in the UI, not the score.** The brief asks for recommendations, not flags.
- **Language:** say "mule network", not "money laundering". The pitch is about scam victims.
- **Honesty:** integrations to core banking are mocked and we say so. "The engine is real, the integrations are stubbed" is a stronger answer than implying more.

## 11. Competitive context (for judge questions)

RBI's **MuleHunter.ai** already exists — built by the Reserve Bank Innovation Hub on 19 mule behaviour patterns, live across 26 banks. If challenged: acknowledge it fully first, then pivot to the three gaps. It classifies accounts rather than networks, produces a flag rather than an auditable explanation, and sits outside the analyst's workflow. Global comparables: Quantexa (closest on graph), Featurespace and Feedzai (behavioural analytics), BioCatch (behavioural biometrics), NICE Actimize / SAS / Clari5 (incumbent monitoring).

Our claim is narrow and defensible: **detection exists, decisions don't — we ship the ring, the reason and the action together.**

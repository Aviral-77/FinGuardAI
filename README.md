# FinGuard AI

A fraud detection console for retail banking, built to the brief in
[`CLAUDE.md`](CLAUDE.md).

Banks score transactions one at a time. Every hop in a mule ring is
individually legitimate, so the ring never surfaces until the money is gone.
FinGuard AI adds the two things that are missing: a **graph layer**, so a ring
appears as a shape, and an **investigator copilot**, so an alert arrives as a
case file with a named next step instead of an account id and a rule number.

```
SEE      graph layer         no AI    live account-to-account graph
SCORE    rule engine         no AI    11 fraud rules score every account
CATCH    anomaly model       ML       Isolation Forest finds what no rule covers
ACT      investigator copilot LLM     writes the case file, recommends one action
```

**The non-negotiable:** the LLM never computes a score or chooses an action.
Rules compute, thresholds decide, AI explains. Every point in every score traces
back to a named rule, and a test asserts that arithmetic reconciles.

---

## Quick start

```bash
# backend
cd backend
pip install -r requirements.txt
python -m app.generator.generate      # optional: the CSVs are committed
uvicorn app.main:app --port 8000

# frontend, in a second shell
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

Then press **Play**. The 30-day window replays in about 25 seconds at 1×.

```bash
cd backend && pytest -q               # 58 tests
```

---

## The demo, in three acts

### Act 1 — the rules catch the ring

Rules fire in the order the brief specifies, and the score climbs visibly:

| When | Rule | | Account | Score |
|---|---|---|---|---|
| 23 May 19:30 | **S3** Elderly / vulnerable pattern | +15 | victim | 15 |
| 24 May 06:00 | **S1** New beneficiary, high value | +20 | victim | **35** → Enhanced monitoring |
| 24 May 18:00 | **M1** Rapid fund movement | +25 | primary mule | 25 |
| 25 May 09:00 | **M2** Multiple source accounts | +20 | primary mule | 45 |
| 25 May 12:00 | **G2** Shared identifiers | +20 | primary mule | **65** → Step-up authentication |
| 27 May 14:40 | **G3** Emerging ring | +35 | ring hub | **95** → Temporary block / freeze |

The victim settles at 35 — enhanced monitoring, because he is a victim, not a
suspect. The ring hub sits at 60 until G3 lands, and **G3 is the rule that
carries it across 86**. The ring being *seen* is what triggers the freeze, which
is the entire argument for the graph layer. `tests/test_scenario.py` asserts
exactly that, so the demo cannot drift.

### Act 2 — the rules-only toggle

One switch re-runs the engine without the network rules and without the model —
a genuine second run, not a filter over the same result.

|  | Full engine | Rules-only |
|---|---|---|
| Accounts frozen | **4** | **0** |
| Highest score | 95 | 75 |
| Rules available | 11 | 8 |
| Alerts raised | 16 | 4 |

The ring disappears. What a conventional per-transaction system sees in the same
window is one isolated alert about an unrelated account takeover.

### Act 3 — the model catches what no rule can

An eight-account ring is planted that sits deliberately under **every** rule
threshold: 68–74% forwarded rather than >80%, after 26–33 hours rather than
within 24, two unique senders rather than more than five, eight members rather
than more than ten, its own device and address per account, four hops from the
watchlist. Every evasion margin is documented in
`app/generator/typologies.py::STEALTH_EVASIONS`.

No rule fires on it. Not "scores below threshold" — **no rule fires at all**, and
all eight would have been allowed through.

The anomaly model finds it anyway, and finds it as a *network*:

```
MLN-02: 10 connected accounts, internal density 36%
  No rule escalated any of them -- the highest rule score in the cluster is 0.
  A per-transaction system sees nothing here.
  ACC-X001: regularity of that holding time is 5.9 standard deviations below
  the population; consistency of the fraction forwarded each time, 3.9 below.
```

For contrast the model also clusters the loud ring, and correctly reports it as
**already escalated** — so the demo can distinguish "the model found something
new" from "the model found everything".

Clicking **Approve** locks the accounts and the header flips to `RING FROZEN`.

---

## How the ML layer stays honest

Three design choices, because "our AI found a hidden network" is easy to claim
and easy to fake:

1. **The model shares no signal with the rules.** Its features are conduit
   behaviour — credit-to-debit pairing, the consistency of the forwarded
   fraction and the holding delay, counterparty shape. No unique-sender counts,
   no shared-identifier flags, no >80%-in-24h test. If it reused the rules'
   inputs it could only re-find what the rules already found.

2. **The features are generic, not reverse-engineered.** They are standard
   money-mule indicators and they score the loud ring, the takeover and ordinary
   busy businesses too. The stealth ring is separable on *shape*, not on volume
   — its transaction count sits within a standard deviation of the background,
   deliberately, so it cannot be found for a trivial reason.

3. **The anomaly score never touches a rule score.** It lives in its own column
   with its own action lane (`ML_REVIEW → Manual fraud review`). The audit chain
   survives intact, and `test_ml_findings_never_change_a_rule_score` proves it.

Everything is deterministic: one seed, `random_state` pinned, fixed feature
order, sorted iteration throughout, and `now` is the replay clock rather than
the wall clock. Two runs produce byte-identical output, which
`tests/test_determinism.py` asserts.

---

## Layout

```
backend/app/
  generator/   seeded Faker world: 4 tables, 3 planted structures
  engine/      11 rules, scoring, action policy
  graphlayer/  NetworkX graph, 2-hop traversal, Louvain communities
  ml/          features, Isolation Forest, explanations, network detection
  copilot/     deterministic case files, optional cached LLM narrative
  replay/      the event stream the UI plays back
  api/         REST + /ws/replay
frontend/src/
  layout.ts    seeded force-directed layout
  components/  feed (left) · graph (centre) · copilot (right)
```

## Data

Generated, not downloaded — no public AML dataset carries the device
fingerprints, login events, password resets or beneficiary timestamps that S1,
S2, A1, A2 and G2 need. 255 accounts and ~1,150 transactions over 30 days,
across the brief's four tables.

Background traffic is shaped to IBM's *Transactions for Anti Money Laundering*
(HI-Small variant; Altman et al., NeurIPS 2023) so the ring does not stand out
merely because the noise around it is unrealistic. **Honestly:** the constants
in `app/generator/calibration.py` encode HI-Small's published characteristics —
lognormal amounts, power-law degree, the payment-format mix, the ~0.1% illicit
rate — rather than being recomputed from the raw 5M-row file, which is
Kaggle-auth-gated. `recalibrate_from_hi_small()` recomputes them properly from
the real CSV, and running it is what would turn the citation from "shaped like"
into "measured from".

## Two places this departs from the brief

- **Section 4 says "implement all ten" and then lists eleven rules** (M1–M3,
  S1–S3, A1–A2, G1–G3). All eleven are implemented; the count in the prose is
  the typo, not the list.
- **Section 6 describes the takeover scenario as "A1 (+30) → Temporary
  Transaction Hold", but section 4's own table puts 30 points in the 0–30 "Allow
  transaction" band.** A1 alone cannot produce a hold. The scenario therefore
  plays out as a takeover realistically would — credential stuffing (A2), then
  the reset and transfer (A1), then a transfer off-pattern in both device and
  value (S2) — reaching 75 and a manual review posture.

## What is real and what is stubbed

The engine is real: the rules, the scoring, the graph traversal, the anomaly
model and the case files all run on the data. Integrations to core banking are
mocked — freezing an account updates state in this application and calls nothing
downstream. The LLM narrative is optional and off by default; without
`ANTHROPIC_API_KEY` the copilot serves its deterministic case file, which is what
the demo runs on.

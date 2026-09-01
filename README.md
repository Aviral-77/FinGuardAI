# FinGuard AI

A fraud detection console for retail banking, built to
[`CLAUDE.md`](CLAUDE.md) and [`DEMO-SPEC.md`](DEMO-SPEC.md).

Banks score transactions one at a time. Every hop in a mule ring is
individually legitimate, so the ring never surfaces until the money is gone.
FinGuard AI adds the two things that are missing: a **graph layer**, so a ring
appears as a shape, and an **investigator copilot**, so an alert arrives as a
case file with a named next step instead of an account id and a rule number.

```
SEE      graph layer          live account-to-account graph; rings appear as shapes
SCORE    rule engine          11 fraud rules score every account
ACT      investigator copilot composes the case file and recommends one named action
```

**The non-negotiable:** the score and the action are always computed by rules
and thresholds, never inferred. Every point in a score traces back to a named
rule — a test asserts the arithmetic reconciles. The case narrative is composed
from **templates** filled with the real case values, so it renders instantly and
cannot fail live.

---

## Quick start

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# frontend, in a second shell
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Config is optional — everything falls back to a safe default. Copy
`backend/.env.example` to `backend/.env` to change ports, CORS, or switch on an
LLM. Run the tests with `cd backend && pytest -q` (73 tests).

---

## The demo — three beats, presenter-driven

The demo is **API-driven, not auto-playing**: nothing is flagged until a trigger
is fired, so the story can be told in three beats with a pause for narration
between each. Drive it from the on-screen control strip, the number keys
`0/1/2/3`, or the `demo/*.sh` scripts.

### Beat 0 — a normal afternoon (`00-reset.sh`)
Ambient traffic between grey nodes. Nothing flagged. `POST /api/demo/reset`
returns to this state in one call, so the demo re-runs cleanly every time.

### Beat 1 — the victim transfer (`01-victim-transfer.sh`)
The victim's transfers land the account at **35 — Enhanced monitoring**, and the
dashboard says *"Insufficient evidence for action. Watching for onward
movement."* **The action controls stay disabled.** This is the most important
beat: one unusual transfer is not fraud, and the system does not cry wolf.

### Beat 2 — the fan-out (`02-fanout.sh`)
The money splits. Scores climb, nodes go amber → red, and the ring assembles
into a shape with a red boundary: **MULE RING DETECTED · 11 accounts · ₹X in
motion**. The hub crosses **86 → Temporary block / freeze**. Now, and only now,
the action controls unlock.

### Beat 3 — act (`03-freeze.sh`, `04-blocked-attempt.sh`)
**Freeze** locks the ring and the header flips to **RING CONTAINED**. A further
transfer into a frozen account is **rejected with HTTP 409** — the freeze is
real, not cosmetic. **Download report** produces a bank-grade PDF case file
(`05-download-report.sh`).

The rule firing order and the scores are pinned by `tests/test_live_demo.py`, so
the demo cannot silently drift: victim 35 (not actionable), hub ≥ 86, ring of 11,
freeze → 409, reset → clean.

---

## The rules (all eleven)

M1–M3 mule behaviour, S1–S3 scam indicators, A1–A2 account takeover, G1–G3
graph/network — each with the brief's exact point values, each mapping to a
named action across the five score bands (Allow / Enhanced monitoring / Step-up
auth / Manual review / Freeze). A score is the sum of the distinct rules that
fired, and no alert leaves the system without a next step.

> The brief says "implement all ten" and then lists eleven. All eleven are
> implemented; the count in the prose is the typo, not the list.

## Data

Generated, not downloaded — no public AML dataset carries the device
fingerprints, login events, password resets and beneficiary timestamps that S1,
S2, A1, A2 and G2 need. 255 accounts over a 30-day window, across the brief's
four tables, calibrated to IBM's HI-Small AML dataset (see
`backend/app/generator/calibration.py` for the honest note on that calibration).

The live demo draws its beats from the **same deterministic generator** that
produces the committed dataset, split by transaction tag into a benign baseline
and the two beats — so the live story and the batch dataset are the same numbers,
with no second hand-tuned copy to drift.

## Architecture

```
backend/app/
  config.py       env-driven config (.env); rule points + bands stay in code
  generator/      seeded Faker world: 4 tables, planted ring
  engine/         11 rules, scoring, action policy
  graphlayer/     NetworkX graph, 2-hop traversal, Louvain communities
  copilot/        composer.py (template narrative) + llm.py (optional provider)
  report/         server-side PDF case report (ReportLab)
  live/           mutable API-driven scoring state + demo scenario
  ml/             anomaly layer (behind FINGUARD_ML_ENABLED)
  api/            live.py (DEMO-SPEC API + /ws/live) and routes.py/ws.py (batch/replay)
frontend/src/     light-theme, three-beat room wired to /ws/live
demo/             preset trigger scripts
```

The **live API** (`POST /api/transaction`, `/transaction/batch`,
`/account/{id}/freeze`, `/report`, `/report.pdf`, `/api/demo/reset`, `/ws/live`)
is what the stage demo runs on. The earlier **batch/replay** analysis endpoints
remain alongside it.

## Optional layers (behind flags)

Two capabilities from earlier iterations are kept in the codebase but **off by
default**, because the DEMO-SPEC stage demo is deliberately deterministic and
rules-only:

- **LLM narrative** — `FINGUARD_LLM_PROVIDER=gemini|anthropic` layers a written
  narrative over the template composer. It is handed the finished facts and only
  rewrites them into prose; it never computes a score or picks an action, is
  cached to disk, and degrades to the template on any failure. Default `none`.
- **Anomaly (ML) layer** — `FINGUARD_ML_ENABLED=true` re-enables the Isolation
  Forest that finds a stealth mule ring the rules miss, in the batch/replay
  analysis. The live demo forces it off regardless. Its `MISSED_BY_RULES` proof
  test still runs in the suite.

## Two places this departs from the brief

- **Ten rules vs eleven** — see above; all eleven are implemented.
- **The takeover scenario** — the brief describes it as "A1 (+30) → Temporary
  Transaction Hold", but its own band table puts 30 points in the 0–30 "Allow"
  band. A1 alone cannot produce a hold, so that scenario plays as a takeover
  realistically would (A2 → A1 → S2, reaching 75 and manual review).

## What is real and what is stubbed

The engine is real: the rules, scoring, graph traversal, case files and PDF all
run on the data, and the freeze genuinely blocks further transactions. Integrations
to core banking are mocked — freezing updates state in this application and calls
nothing downstream — and the PDF footer says so.

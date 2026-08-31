"""REST surface.

Every endpoint reads from a cached :class:`~app.analysis.Analysis`. Nothing is
computed per request beyond assembling a view, so the UI stays responsive and
the numbers on one screen always agree with the numbers on another.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..analysis import Analysis, cached_analysis
from ..config import SCORE_BANDS
from ..copilot import llm
from ..copilot.templates import build_case, build_network_case, render_markdown
from ..engine.registry import ALL_RULES
from ..graphlayer.community import communities

router = APIRouter(prefix="/api")


def _analysis(graph_enabled: bool = True) -> Analysis:
    return cached_analysis(graph_enabled)


# --------------------------------------------------------------------------
# Health and dataset
# --------------------------------------------------------------------------


@router.get("/health")
def health() -> dict[str, Any]:
    analysis = _analysis()
    return {
        "status": "ok",
        "accounts": len(analysis.dataset.accounts),
        "transactions": len(analysis.dataset.transactions),
        "as_of": analysis.as_of.isoformat(),
    }


@router.get("/dataset/summary")
def dataset_summary() -> dict[str, Any]:
    analysis = _analysis()
    dataset = analysis.dataset
    bands: dict[str, int] = {}
    for score in analysis.scores.values():
        bands[score.band_code] = bands.get(score.band_code, 0) + 1
    allowed = len(dataset.accounts) - sum(bands.values())
    bands["ALLOW"] = bands.get("ALLOW", 0) + allowed

    fired: dict[str, int] = {}
    for hit in analysis.hits:
        fired[hit.rule_id] = fired.get(hit.rule_id, 0) + 1

    return {
        "accounts": len(dataset.accounts),
        "transactions": len(dataset.transactions),
        "device_sessions": len(dataset.device_sessions),
        "beneficiaries": len(dataset.beneficiaries),
        "window_start": analysis.ctx.window_start.isoformat(),
        "window_end": analysis.as_of.isoformat(),
        "total_value": round(sum(t.amount for t in dataset.transactions), 2),
        "bands": bands,
        "rules_fired": fired,
        "flagged_accounts": len(analysis.flagged_accounts),
        "ml_networks": len(analysis.networks),
        "missed_networks": len(analysis.missed_networks),
    }


@router.get("/transactions")
def transactions(
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    account: str | None = None,
) -> dict[str, Any]:
    analysis = _analysis()
    rows = analysis.ctx.transactions
    if account:
        rows = [t for t in rows if account in (t.from_account, t.to_account)]
    page = rows[offset : offset + limit]
    return {
        "total": len(rows),
        "offset": offset,
        "items": [
            {
                "txn_id": t.txn_id,
                "timestamp": t.timestamp.isoformat(),
                "from_account": t.from_account,
                "to_account": t.to_account,
                "amount": t.amount,
                "channel": t.channel,
            }
            for t in page
        ],
    }


@router.get("/accounts")
def accounts(flagged_only: bool = False) -> dict[str, Any]:
    analysis = _analysis()
    items = []
    for account in analysis.dataset.accounts:
        score = analysis.scores.get(account.account_id)
        if flagged_only and (score is None or score.band_code == "ALLOW"):
            continue
        finding = analysis.anomaly.findings.get(account.account_id)
        items.append(
            {
                "account_id": account.account_id,
                "name": account.name,
                "role": account.role,
                "age_band": account.age_band,
                "known_suspicious": account.known_suspicious,
                "score": score.score if score else 0,
                "band_code": score.band_code if score else "ALLOW",
                "band_label": score.band_label if score else "Allow transaction",
                "rule_ids": score.rule_ids if score else [],
                "anomaly_score": finding.anomaly_score if finding else 0.0,
                "anomaly_flagged": bool(finding and finding.is_anomalous),
            }
        )
    items.sort(key=lambda a: (-a["score"], -a["anomaly_score"], a["account_id"]))
    return {"total": len(items), "items": items}


@router.get("/accounts/{account_id}")
def account_detail(account_id: str) -> dict[str, Any]:
    try:
        return build_case(_analysis(), account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown account {account_id}")


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


@router.get("/rules")
def rules() -> dict[str, Any]:
    analysis = _analysis()
    counts: dict[str, int] = {}
    accounts_hit: dict[str, set[str]] = {}
    for hit in analysis.hits:
        counts[hit.rule_id] = counts.get(hit.rule_id, 0) + 1
        accounts_hit.setdefault(hit.rule_id, set()).add(hit.account_id)
    return {
        "items": [
            {
                **rule.as_dict(),
                "fired": counts.get(rule.rule_id, 0),
                "accounts": len(accounts_hit.get(rule.rule_id, ())),
            }
            for rule in ALL_RULES
        ],
        "bands": [
            {"code": code, "label": label, "lower": lower, "upper": upper}
            for lower, upper, code, label in SCORE_BANDS
        ],
    }


@router.get("/alerts")
def alerts() -> dict[str, Any]:
    """Every rule firing, newest first -- the analyst's queue."""
    analysis = _analysis()
    return {
        "items": [
            {
                "rule_id": hit.rule_id,
                "rule_name": hit.rule_name,
                "category": hit.category,
                "account_id": hit.account_id,
                "points": hit.points,
                "timestamp": hit.timestamp.isoformat(),
                "message": hit.message,
                "score": analysis.score_of(hit.account_id),
                "band_code": analysis.band_of(hit.account_id)[0],
                "evidence_txn_ids": hit.evidence_txn_ids,
            }
            for hit in sorted(analysis.hits, key=lambda h: h.timestamp, reverse=True)
        ]
    }


@router.get("/actions")
def actions() -> dict[str, Any]:
    analysis = _analysis()
    return {
        "items": [a.to_dict() for a in analysis.actions + analysis.ml_actions],
    }


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------


@router.get("/graph")
def graph(graph_enabled: bool = True) -> dict[str, Any]:
    """Nodes and edges for the force-directed view.

    ``graph_enabled=false`` returns the same topology scored by the rules-only
    engine, which is what drives the proof toggle: the ring is still there, but
    almost nothing on it is red.
    """
    analysis = _analysis(graph_enabled)
    ml_membership: dict[str, str] = {}
    for network in analysis.networks:
        for account_id in network.account_ids:
            ml_membership[account_id] = network.network_id

    nodes = []
    for account in analysis.dataset.accounts:
        score = analysis.scores.get(account.account_id)
        finding = analysis.anomaly.findings.get(account.account_id)
        nodes.append(
            {
                "id": account.account_id,
                "role": account.role,
                "score": score.score if score else 0,
                "band_code": score.band_code if score else "ALLOW",
                "rule_ids": score.rule_ids if score else [],
                "known_suspicious": account.known_suspicious,
                "anomaly_score": finding.anomaly_score if finding else 0.0,
                "anomaly_flagged": bool(finding and finding.is_anomalous),
                "ml_network": ml_membership.get(account.account_id),
                "degree": analysis.ctx.ugraph.degree(account.account_id)
                if account.account_id in analysis.ctx.ugraph
                else 0,
            }
        )

    edges = []
    for source, target, data in analysis.ctx.graph.edges(data=True):
        edges.append(
            {
                "source": source,
                "target": target,
                "count": data["count"],
                "total_amount": data["total_amount"],
                "first_seen": data["first_seen"].isoformat(),
            }
        )

    return {
        "graph_enabled": graph_enabled,
        "nodes": nodes,
        "edges": edges,
        "communities": [c for c in communities(analysis.ctx.ugraph) if len(c) >= 5],
    }


# --------------------------------------------------------------------------
# Anomaly model
# --------------------------------------------------------------------------


@router.get("/ml/findings")
def ml_findings(limit: int = Query(40, ge=1, le=400)) -> dict[str, Any]:
    analysis = _analysis()
    ranked = sorted(analysis.anomaly.findings.values(), key=lambda f: f.rank)[:limit]
    return {
        "items": [
            {
                "account_id": f.account_id,
                "anomaly_score": f.anomaly_score,
                "rank": f.rank,
                "flagged": f.is_anomalous,
                "elevated": f.is_elevated,
                "rule_score": analysis.score_of(f.account_id),
                "top_features": f.top_features,
            }
            for f in ranked
        ]
    }


@router.get("/ml/networks")
def ml_networks() -> dict[str, Any]:
    analysis = _analysis()
    return {
        "items": [build_network_case(analysis, n) for n in analysis.networks],
        "missed_count": len(analysis.missed_networks),
    }


@router.get("/ml/networks/{network_id}")
def ml_network_detail(network_id: str) -> dict[str, Any]:
    analysis = _analysis()
    for network in analysis.networks:
        if network.network_id == network_id:
            return build_network_case(analysis, network)
    raise HTTPException(status_code=404, detail=f"unknown network {network_id}")


# --------------------------------------------------------------------------
# Copilot
# --------------------------------------------------------------------------


@router.get("/copilot/{account_id}")
def copilot(account_id: str, narrate: bool = False) -> dict[str, Any]:
    try:
        case = build_case(_analysis(), account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown account {account_id}")
    if narrate:
        text, source = llm.narrate(case)
        case["narrative"] = text
        case["narrative_source"] = source
    return case


@router.get("/copilot/{account_id}/markdown", response_class=PlainTextResponse)
def copilot_markdown(account_id: str) -> str:
    try:
        return render_markdown(build_case(_analysis(), account_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown account {account_id}")


# --------------------------------------------------------------------------
# The proof toggle
# --------------------------------------------------------------------------


@router.get("/comparison")
def comparison() -> dict[str, Any]:
    """Full engine against rules-only, side by side.

    The single most persuasive element of the demo (CLAUDE.md section 6), and a
    genuine comparison: the rules-only figures come from re-running the engine
    without the network rules and without the model, not from filtering the
    full result.
    """
    full = _analysis(True)
    rules_only = _analysis(False)

    def snapshot(analysis: Analysis) -> dict[str, Any]:
        return {
            "flagged_accounts": len(analysis.flagged_accounts),
            "rules_fired": sorted({h.rule_id for h in analysis.hits}),
            "frozen": sorted(
                a for a, s in analysis.scores.items() if s.band_code == "FREEZE"
            ),
            "highest_score": max((s.score for s in analysis.scores.values()), default=0),
            "actions": len(analysis.actions) + len(analysis.ml_actions),
        }

    return {
        "full": snapshot(full),
        "rules_only": snapshot(rules_only),
        "ring_accounts_caught_by_full": sorted(
            a for a, s in full.scores.items() if s.band_code in {"FREEZE", "MANUAL_REVIEW"}
        ),
        "ring_accounts_caught_by_rules_only": sorted(
            a
            for a, s in rules_only.scores.items()
            if s.band_code in {"FREEZE", "MANUAL_REVIEW"}
        ),
        "missed_networks": [
            build_network_case(full, n) for n in full.missed_networks
        ],
    }

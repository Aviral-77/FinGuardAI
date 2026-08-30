"""Builds the case file an analyst reads.

The brief's second failure: an alert arrives as an account id, a score and a
rule number, and the analyst spends 30-45 minutes assembling the context by
hand. This module assembles it instead -- score breakdown, the rules that fired
with their evidence, the network around the account, and the one recommended
action.

Everything here is deterministic and assembled from structured facts. It needs
no API key, works offline, and cannot fail on stage. :mod:`app.copilot.llm` can
layer a written narrative on top when a key is present, but the case file is
complete without it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..analysis import Analysis
from ..engine.actions import action_for_account
from ..engine.scoring import score_breakdown
from ..graphlayer.traversal import within_hops
from ..ml.explain import describe
from ..models import MLNetwork


def build_case(analysis: Analysis, account_id: str) -> dict[str, Any]:
    """The full case file for one account."""
    account = analysis.ctx.accounts.get(account_id)
    if account is None:
        raise KeyError(account_id)

    score = analysis.scores.get(account_id)
    action = action_for_account(score) if score else None
    finding = analysis.anomaly.findings.get(account_id)
    networks = [n for n in analysis.networks if account_id in n.account_ids]

    credits = analysis.ctx.incoming.get(account_id, [])
    debits = analysis.ctx.outgoing.get(account_id, [])
    total_in = round(sum(t.amount for t in credits), 2)
    total_out = round(sum(t.amount for t in debits), 2)

    neighbours = (
        within_hops(analysis.ctx.ugraph, account_id, 1)
        if analysis.ctx.ugraph is not None
        else {}
    )
    linked = sorted(neighbours)

    return {
        "account_id": account_id,
        "generated_at": analysis.as_of.isoformat(),
        "profile": {
            "name": account.name,
            "age_band": account.age_band,
            "role": account.role,
            "open_date": account.open_date.isoformat(),
            "kyc_date": account.kyc_date.isoformat(),
            "dormant": account.dormancy_flag,
            "known_suspicious": account.known_suspicious,
            "phone": account.phone,
            "address": account.address,
        },
        "score": score.score if score else 0,
        "band_code": score.band_code if score else "ALLOW",
        "band_label": score.band_label if score else "Allow transaction",
        "recommended_action": action.to_dict() if action else None,
        "breakdown": score_breakdown(score) if score else [],
        "activity": {
            "credits": len(credits),
            "debits": len(debits),
            "total_in": total_in,
            "total_out": total_out,
            "first_seen": credits[0].timestamp.isoformat() if credits else None,
            "last_seen": (
                max(credits + debits, key=lambda t: t.timestamp).timestamp.isoformat()
                if (credits or debits)
                else None
            ),
        },
        "network": {
            "direct_counterparties": linked,
            "counterparty_count": len(linked),
            "ml_networks": [n.network_id for n in networks],
        },
        "anomaly": (
            {
                "score": finding.anomaly_score,
                "rank": finding.rank,
                "flagged": finding.is_anomalous,
                "elevated": finding.is_elevated,
                "top_features": finding.top_features,
                "explanation": describe(finding.top_features),
            }
            if finding
            else None
        ),
        "summary": _summary(analysis, account_id),
        "evidence": _evidence(analysis, account_id),
    }


def _summary(analysis: Analysis, account_id: str) -> str:
    """A plain-English paragraph, assembled from facts rather than written."""
    account = analysis.ctx.accounts[account_id]
    score = analysis.scores.get(account_id)
    finding = analysis.anomaly.findings.get(account_id)

    if score is None or not score.hits:
        base = (
            f"{account_id} triggered no detection rule during the window. "
            f"On the rule engine alone it would have been allowed through."
        )
        if finding is not None and (finding.is_anomalous or finding.is_elevated):
            networks = [
                n for n in analysis.networks if account_id in n.account_ids and n.missed_by_rules
            ]
            base += (
                f" The anomaly model ranks it {finding.rank} of "
                f"{len(analysis.anomaly.findings)} on behavioural outlier score. "
                + describe(finding.top_features)
            )
            if networks:
                base += (
                    f" It sits inside {networks[0].network_id}, a cluster of "
                    f"{len(networks[0].account_ids)} connected accounts that no rule escalated."
                )
        return base

    first = score.hits[0]
    last = score.hits[-1]
    rules = ", ".join(score.rule_ids)
    text = (
        f"{account_id} scored {score.score} across {len(score.rule_ids)} rules "
        f"({rules}) between {first.timestamp:%d %b %H:%M} and {last.timestamp:%d %b %H:%M}, "
        f"placing it in the {score.band_label.lower()} band."
    )
    if account.is_elderly and "S3" in score.rule_ids:
        text += (
            " The customer is in the 60+ age band and the pattern is consistent "
            "with a scam victim rather than a participant."
        )
    if finding is not None and finding.is_anomalous:
        text += (
            f" The anomaly model independently ranks it {finding.rank} of "
            f"{len(analysis.anomaly.findings)}."
        )
    return text


def _evidence(analysis: Analysis, account_id: str, limit: int = 12) -> list[dict[str, Any]]:
    """The transactions the rules actually cited, most recent first."""
    score = analysis.scores.get(account_id)
    if score is None:
        return []
    wanted: dict[str, list[str]] = {}
    for hit in score.hits:
        for txn_id in hit.evidence_txn_ids:
            wanted.setdefault(txn_id, []).append(hit.rule_id)

    rows = []
    for txn in analysis.ctx.transactions:
        if txn.txn_id not in wanted:
            continue
        rows.append(
            {
                "txn_id": txn.txn_id,
                "timestamp": txn.timestamp.isoformat(),
                "from_account": txn.from_account,
                "to_account": txn.to_account,
                "amount": txn.amount,
                "channel": txn.channel,
                "cited_by": sorted(set(wanted[txn.txn_id])),
            }
        )
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    return rows[:limit]


def build_network_case(analysis: Analysis, network: MLNetwork) -> dict[str, Any]:
    """The case file for an ML-detected network rather than one account."""
    members = []
    for account_id in network.account_ids:
        finding = analysis.anomaly.findings.get(account_id)
        members.append(
            {
                "account_id": account_id,
                "rule_score": analysis.score_of(account_id),
                "rule_ids": (
                    analysis.scores[account_id].rule_ids if account_id in analysis.scores else []
                ),
                "anomaly_score": finding.anomaly_score if finding else 0.0,
                "anomaly_rank": finding.rank if finding else None,
                "explanation": describe(finding.top_features) if finding else "",
            }
        )
    members.sort(key=lambda m: (-m["anomaly_score"], m["account_id"]))

    return {
        "network_id": network.network_id,
        "generated_at": analysis.as_of.isoformat(),
        "account_count": len(network.account_ids),
        "density": network.density,
        "mean_anomaly": network.mean_anomaly,
        "max_rule_score": network.max_rule_score,
        "missed_by_rules": network.missed_by_rules,
        "recommended_action": {
            "code": network.action_code,
            "label": network.action_label,
        },
        "rationale": network.rationale,
        "members": members,
        "headline": (
            f"Mule network of {len(network.account_ids)} connected accounts "
            f"detected by the anomaly model. No rule fired."
            if network.missed_by_rules
            else f"Network of {len(network.account_ids)} connected accounts, "
            f"already escalated by the rule engine at score {network.max_rule_score}."
        ),
    }


def render_markdown(case: dict[str, Any]) -> str:
    """The case file as Markdown, for export into a case management system."""
    lines = [
        f"# Case file: {case['account_id']}",
        "",
        f"**Score** {case['score']} — {case['band_label']}  ",
        f"**Recommended action** "
        f"{case['recommended_action']['label'] if case['recommended_action'] else 'None'}  ",
        f"**Generated** {case['generated_at']}",
        "",
        "## Summary",
        "",
        case["summary"],
        "",
        "## Score breakdown",
        "",
        "| Rule | Name | Points | Running | When |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in case["breakdown"]:
        lines.append(
            f"| {row['rule_id']} | {row['rule_name']} | "
            f"{'+' + str(row['points']) if row['counted'] else '0'} | "
            f"{row['running_score']} | {row['timestamp'][:16].replace('T', ' ')} |"
        )

    if case.get("anomaly"):
        anomaly = case["anomaly"]
        lines += [
            "",
            "## Anomaly model",
            "",
            f"Rank {anomaly['rank']}, score {anomaly['score']:.3f}"
            f"{' — flagged' if anomaly['flagged'] else ''}.",
            "",
            anomaly["explanation"],
        ]

    if case["evidence"]:
        lines += [
            "",
            "## Evidence",
            "",
            "| Transaction | When | From | To | Amount | Cited by |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
        for row in case["evidence"]:
            lines.append(
                f"| {row['txn_id']} | {row['timestamp'][:16].replace('T', ' ')} | "
                f"{row['from_account']} | {row['to_account']} | "
                f"{row['amount']:,.2f} | {', '.join(row['cited_by'])} |"
            )

    lines += [
        "",
        "---",
        "",
        "_Score computed by the FinGuard AI rule engine. Every point above "
        "traces to a named rule; the anomaly model does not contribute to it._",
    ]
    return "\n".join(lines)

"""Builds the account-to-account graph.

This is the "SEE" stage of the brief: the layer that makes a ring a *shape*
rather than a list of individually-legitimate transfers.
"""

from __future__ import annotations

import networkx as nx

from ..models import Dataset


def build_graph(dataset: Dataset) -> nx.DiGraph:
    """A directed multigraph collapsed to weighted edges.

    Parallel transfers between the same pair are aggregated: the UI needs one
    line per relationship, and the graph rules care about who is connected to
    whom, not how many times.

    Nodes are added in sorted order and edges in timestamp order, so the layout
    seed and every traversal below are reproducible.
    """
    graph = nx.DiGraph()
    for account in sorted(dataset.accounts, key=lambda a: a.account_id):
        graph.add_node(
            account.account_id,
            role=account.role,
            age_band=account.age_band,
            known_suspicious=account.known_suspicious,
            dormant=account.dormancy_flag,
        )

    for txn in sorted(dataset.transactions, key=lambda t: (t.timestamp, t.txn_id)):
        if graph.has_edge(txn.from_account, txn.to_account):
            edge = graph[txn.from_account][txn.to_account]
            edge["count"] += 1
            edge["total_amount"] = round(edge["total_amount"] + txn.amount, 2)
            edge["last_seen"] = txn.timestamp
            edge["txn_ids"].append(txn.txn_id)
        else:
            graph.add_edge(
                txn.from_account,
                txn.to_account,
                count=1,
                total_amount=round(txn.amount, 2),
                first_seen=txn.timestamp,
                last_seen=txn.timestamp,
                txn_ids=[txn.txn_id],
            )
    return graph


def undirected(graph: nx.DiGraph) -> nx.Graph:
    """Undirected projection, used for proximity and community detection.

    Direction does not matter for "who is this account connected to" -- money
    flowing towards a suspect links you to them just as much as money flowing
    away.
    """
    return graph.to_undirected(as_view=False)

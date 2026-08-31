"""Neighbourhood traversal -- the two-hop reach rule G1 is defined against."""

from __future__ import annotations

import networkx as nx


def within_hops(graph: nx.Graph, source: str, hops: int) -> dict[str, int]:
    """Every account reachable from ``source`` in at most ``hops`` steps.

    Returns ``{account_id: distance}``, excluding the source itself. A plain
    breadth-first walk: at 2 hops on a 250-account graph there is nothing to
    optimise, and keeping it obvious keeps it auditable.
    """
    if source not in graph:
        return {}
    distances: dict[str, int] = {}
    frontier = [source]
    seen = {source}
    for distance in range(1, hops + 1):
        nxt: list[str] = []
        for node in frontier:
            for neighbour in sorted(graph.neighbors(node)):
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                distances[neighbour] = distance
                nxt.append(neighbour)
        frontier = nxt
        if not frontier:
            break
    return distances


def shortest_path_between(graph: nx.Graph, source: str, target: str) -> list[str]:
    """The path linking two accounts, for the copilot's "why" narrative."""
    try:
        return list(nx.shortest_path(graph, source, target))
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []

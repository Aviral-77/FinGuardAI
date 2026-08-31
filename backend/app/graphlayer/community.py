"""Community detection and centrality.

Used twice: by rule G3 to find an emerging ring, and by the ML layer to decide
whether a set of anomalous accounts is a *network* or just a set of odd
accounts that happen to be odd separately.

NetworkX ships Louvain natively (``networkx.algorithms.community``), so there
is no ``python-louvain`` dependency. Seeded, so the partition is identical on
every run -- Louvain is otherwise order-sensitive and would make the demo
non-reproducible.
"""

from __future__ import annotations

import networkx as nx
from networkx.algorithms.community import louvain_communities

from ..config import SEED


def communities(graph: nx.Graph, resolution: float = 1.0) -> list[list[str]]:
    """Louvain partition, returned in a canonical order.

    Sorted by size then by first member, and each community internally sorted,
    so community indices are stable between runs.
    """
    if graph.number_of_nodes() == 0:
        return []
    partition = louvain_communities(
        graph, weight="count", resolution=resolution, seed=SEED
    )
    found = [sorted(group) for group in partition]
    found.sort(key=lambda group: (-len(group), group[0] if group else ""))
    return found


def density(graph: nx.Graph, members: list[str]) -> float:
    """Internal edge density of a member set, in ``[0, 1]``.

    ``edges / possible_edges``. Distinguishes a coordinated cluster from a set
    of accounts that merely landed in the same partition.
    """
    if len(members) < 2:
        return 0.0
    subgraph = graph.subgraph(members)
    possible = len(members) * (len(members) - 1) / 2
    return subgraph.number_of_edges() / possible if possible else 0.0


def centrality(graph: nx.Graph, members: list[str]) -> dict[str, float]:
    """Degree centrality within a community, for picking its hub."""
    if not members:
        return {}
    subgraph = graph.subgraph(members)
    return {node: float(value) for node, value in nx.degree_centrality(subgraph).items()}


def hub_of(graph: nx.Graph, members: list[str]) -> str:
    """The most connected member -- the node an analyst should look at first."""
    scores = centrality(graph, members)
    if not scores:
        return members[0] if members else ""
    # Sorted by score then id, so ties never resolve by dict order.
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

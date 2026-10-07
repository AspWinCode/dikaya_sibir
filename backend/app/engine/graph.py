"""
Rule dependency graph + Tarjan SCC cycle detection.

A rule depends on another if:
  - This rule's actions write to entity X / trigger event E
  - Another rule's trigger listens to entity X / event E

We model this as a directed graph: rule_id → [rule_ids that this rule could trigger].
Tarjan SCC identifies cycles (SCCs with size > 1, or self-loops).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RuleNode:
    rule_id: str
    entity_id: str
    trigger_event: str  # e.g. "record.created"
    trigger_fields: list[str]  # for "field.changed" events
    action_entity_ids: list[str]  # entities written by actions
    action_events: list[str]  # events emitted by actions


def build_dependency_graph(rules: list[RuleNode]) -> dict[str, list[str]]:
    """
    For each rule R, find all other rules Q such that R's actions
    could trigger Q's condition (same entity, compatible event).
    Returns adjacency list: {rule_id: [dependent_rule_ids]}.
    """
    graph: dict[str, list[str]] = {r.rule_id: [] for r in rules}

    for rule in rules:
        for action_entity in rule.action_entity_ids:
            for candidate in rules:
                if candidate.rule_id == rule.rule_id:
                    continue
                # Does the action affect the entity this candidate rule listens to?
                if candidate.entity_id == action_entity:
                    graph[rule.rule_id].append(candidate.rule_id)

    return graph


# ------------------------------------------------------------------
# Tarjan SCC — iterative (no Python recursion limit risk)
# ------------------------------------------------------------------


def tarjan_scc(graph: dict[str, list[str]]) -> list[list[str]]:
    """
    Tarjan's algorithm for finding all Strongly Connected Components.
    Iterative implementation to avoid Python's recursion limit.
    Returns list of SCCs (each is a list of node IDs).
    """
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    sccs: list[list[str]] = []
    counter = [0]

    # Iterative DFS using an explicit work stack
    # Each frame: (node, iterator_over_neighbors, already_visited)
    for start in graph:
        if start in index:
            continue

        work_stack: list[tuple[str, Any]] = [(start, iter(graph.get(start, [])))]
        index[start] = lowlink[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack[start] = True

        while work_stack:
            node, neighbors = work_stack[-1]
            try:
                neighbor = next(neighbors)
                if neighbor not in index:
                    index[neighbor] = lowlink[neighbor] = counter[0]
                    counter[0] += 1
                    stack.append(neighbor)
                    on_stack[neighbor] = True
                    work_stack.append((neighbor, iter(graph.get(neighbor, []))))
                elif on_stack.get(neighbor, False):
                    lowlink[node] = min(lowlink[node], index[neighbor])
            except StopIteration:
                work_stack.pop()
                if work_stack:
                    parent = work_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                # Root of SCC?
                if lowlink[node] == index[node]:
                    scc: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        scc.append(w)
                        if w == node:
                            break
                    sccs.append(scc)

    return sccs


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Return only SCCs that constitute a cycle (size > 1 or self-loop)."""
    return [
        scc
        for scc in tarjan_scc(graph)
        if len(scc) > 1 or (len(scc) == 1 and scc[0] in graph.get(scc[0], []))
    ]


def extract_rule_nodes(rules_raw: list[dict[str, Any]]) -> list[RuleNode]:
    """Convert raw rule dicts (from DB) into RuleNode objects for graph analysis."""
    nodes: list[RuleNode] = []
    for r in rules_raw:
        trigger = r.get("trigger", {})
        action_entity_ids = []
        action_events = []
        for action in r.get("actions", []):
            atype = action.get("type", "")
            if atype in ("create_record", "update_record", "delete_record"):
                if "entity_id" in action:
                    action_entity_ids.append(str(action["entity_id"]))
                else:
                    # Action on the same entity as trigger
                    action_entity_ids.append(str(r.get("entity_id", "")))
                action_events.append(
                    "record.created" if atype == "create_record" else "record.updated"
                )

        nodes.append(
            RuleNode(
                rule_id=str(r["id"]),
                entity_id=str(r.get("entity_id", "")),
                trigger_event=trigger.get("event", ""),
                trigger_fields=trigger.get("watch_fields", []),
                action_entity_ids=action_entity_ids,
                action_events=action_events,
            )
        )
    return nodes

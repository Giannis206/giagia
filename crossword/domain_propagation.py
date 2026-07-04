"""Node and arc consistency (AC-3) for crossword slot domains."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from crossword.slots import Slot, slots_by_cell


@dataclass(frozen=True)
class Arc:
    """Directed arc: tail slot letter at pos_a must match head slot at pos_b."""

    tail_id: int
    head_id: int
    pos_tail: int
    pos_head: int


def enforce_node_consistency(
    slots: list[Slot],
    dictionary: dict[int, set[str]],
) -> dict[int, set[str]]:
    """Initial domains: dictionary words matching each slot length."""
    domains: dict[int, set[str]] = {}
    for slot in slots:
        words = dictionary.get(slot.length)
        domains[slot.slot_id] = set(words) if words else set()
    return domains


def build_arcs(slots: list[Slot]) -> list[Arc]:
    """Build directed arcs for every across/down crossing."""
    cell_slots = slots_by_cell(slots)
    arcs: list[Arc] = []
    seen: set[tuple[int, int, tuple[int, int]]] = set()

    for cell, crossing in cell_slots.items():
        if len(crossing) != 2:
            continue
        a, b = crossing
        if a.direction == b.direction:
            continue
        pos_a = a.cells.index(cell)
        pos_b = b.cells.index(cell)
        for tail, head, pt, ph in ((a, b, pos_a, pos_b), (b, a, pos_b, pos_a)):
            key = (tail.slot_id, head.slot_id, cell)
            if key in seen:
                continue
            seen.add(key)
            arcs.append(Arc(tail.slot_id, head.slot_id, pt, ph))
    return arcs


def _revise(
    domains: dict[int, set[str]],
    arc: Arc,
) -> bool:
    """Remove tail values with no supporting head value (letter-set filter)."""
    tail_dom = domains.get(arc.tail_id, set())
    head_dom = domains.get(arc.head_id, set())
    if not tail_dom:
        return False

    head_letters = {word[arc.pos_head] for word in head_dom}
    if not head_letters:
        domains[arc.tail_id] = set()
        return True

    survivors = {word for word in tail_dom if word[arc.pos_tail] in head_letters}
    if len(survivors) != len(tail_dom):
        domains[arc.tail_id] = survivors
        return True
    return False


def enforce_arc_consistency(
    slots: list[Slot],
    dictionary: dict[int, set[str]],
    domains: dict[int, set[str]] | None = None,
) -> tuple[bool, dict[int, set[str]]]:
    """Run AC-3 until fixpoint. Returns (ok, domains)."""
    domains = dict(domains if domains is not None else enforce_node_consistency(slots, dictionary))
    arcs = build_arcs(slots)
    queue: deque[Arc] = deque(arcs)

    while queue:
        arc = queue.popleft()
        if _revise(domains, arc):
            if not domains.get(arc.tail_id):
                return False, domains
            for other in arcs:
                if other.head_id == arc.tail_id:
                    queue.append(other)

    return True, domains


def check_arc_consistency(
    slots: list[Slot],
    dictionary: dict[int, set[str]],
) -> tuple[bool, dict[int, set[str]], list[int]]:
    """AC-3 check; returns ok, domains, slot ids with empty domain."""
    ok, domains = enforce_arc_consistency(slots, dictionary)
    zero_slots = [sid for sid, dom in domains.items() if not dom]
    return ok and not zero_slots, domains, zero_slots


def bottleneck_slots(domains: dict[int, set[str]], *, limit: int = 5) -> list[int]:
    """Slot ids with the smallest non-empty domains (hardest to fill)."""
    ranked = sorted(
        ((sid, len(dom)) for sid, dom in domains.items() if dom),
        key=lambda item: item[1],
    )
    return [sid for sid, _ in ranked[:limit]]

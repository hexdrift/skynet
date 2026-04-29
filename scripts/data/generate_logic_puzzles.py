"""Generate Einstein/zebra-style logic puzzles with verified unique solutions.

Output: ``data/logic_puzzles.json`` (100 rows). Each row is a 4-position,
4-attribute constraint-satisfaction puzzle with a uniquely-determined
solution. Constructed forward (random valid assignment → overgenerate clues
from the assignment → greedy-minimize while preserving solvability), so
correctness is by construction and uniqueness is verified.

Schema per row:
    entities          list[str] — positional labels ("position_1" ... "position_4")
    attributes        dict[str, list[str]] — attribute name → sorted value pool
    clues             list[str] — natural-language constraints that uniquely identify the solution
    solution          dict[str, dict[str, str]] — entity → attribute → value

Solver is brute-force backtracking with constraint-driven pruning: each
attribute is assigned as a full permutation, and clues whose referenced
attributes are all bound are evaluated immediately so violating subtrees are
abandoned early. With 4 attributes × 4! permutations and aggressive pruning
the per-puzzle solve time is sub-millisecond, so the minimization loop
(which calls the solver O(|clues|) times) runs comfortably under a second
per puzzle.

Usage:
    python3 scripts/data/generate_logic_puzzles.py
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Callable

ROW_COUNT = 100
SEED = 42
N = 4
OUTPUT = Path(__file__).resolve().parents[2] / "data" / "logic_puzzles.json"

ATTRIBUTE_POOLS: dict[str, list[str]] = {
    "color": ["red", "blue", "green", "yellow", "purple", "orange"],
    "pet": ["cat", "dog", "fish", "bird", "rabbit", "hamster"],
    "drink": ["water", "juice", "milk", "tea", "coffee", "lemonade"],
    "hobby": ["chess", "painting", "reading", "dancing", "gardening", "cooking"],
    "fruit": ["apple", "banana", "cherry", "grape", "mango", "kiwi"],
    "instrument": ["piano", "guitar", "violin", "drums", "flute", "harp"],
}


@dataclass(frozen=True)
class Clue:
    """A single constraint with its natural-language phrasing and a satisfaction predicate."""

    text: str
    required_attrs: tuple[str, ...]
    check: Callable[[dict[str, list[str]]], bool]


def _at_position(attr: str, val: str, pos: int) -> Clue:
    """Constraint: ``attr`` at ``pos`` (1-indexed) is exactly ``val``."""
    return Clue(
        text=f"In position {pos}, the {attr} is {val}.",
        required_attrs=(attr,),
        check=lambda a: a[attr][pos - 1] == val,
    )


def _same_position(attr1: str, val1: str, attr2: str, val2: str) -> Clue:
    """Constraint: the position whose ``attr1`` is ``val1`` also has ``attr2`` = ``val2``."""
    return Clue(
        text=f"The person with {attr1} {val1} also has {attr2} {val2}.",
        required_attrs=(attr1, attr2),
        check=lambda a: a[attr1].index(val1) == a[attr2].index(val2),
    )


def _left_of(attr1: str, val1: str, attr2: str, val2: str) -> Clue:
    """Constraint: the position with ``attr1=val1`` is strictly left of ``attr2=val2``."""
    return Clue(
        text=f"The person with {attr1} {val1} is in a lower-numbered position than the person with {attr2} {val2}.",
        required_attrs=(attr1, attr2),
        check=lambda a: a[attr1].index(val1) < a[attr2].index(val2),
    )


def _adjacent(attr1: str, val1: str, attr2: str, val2: str) -> Clue:
    """Constraint: the positions are adjacent (differ by exactly 1)."""
    return Clue(
        text=f"The person with {attr1} {val1} is in a position adjacent to the person with {attr2} {val2}.",
        required_attrs=(attr1, attr2),
        check=lambda a: abs(a[attr1].index(val1) - a[attr2].index(val2)) == 1,
    )


def _at_end(attr: str, val: str) -> Clue:
    """Constraint: ``attr=val`` is at one of the two end positions."""
    return Clue(
        text=f"The person with {attr} {val} is at one of the two end positions.",
        required_attrs=(attr,),
        check=lambda a: a[attr].index(val) in (0, N - 1),
    )


def random_solution(rng: random.Random) -> dict[str, list[str]]:
    """Pick 4 attribute categories, each with a random N-permutation of its pool."""
    categories = rng.sample(list(ATTRIBUTE_POOLS), 4)
    return {cat: rng.sample(ATTRIBUTE_POOLS[cat], N) for cat in categories}


def overgenerate_clues(rng: random.Random, solution: dict[str, list[str]]) -> list[Clue]:
    """Build a varied pool of true clues from a solved puzzle."""
    attr_names = list(solution)
    clues: list[Clue] = []

    for attr in attr_names:
        for pos in range(1, N + 1):
            clues.append(_at_position(attr, solution[attr][pos - 1], pos))

    for i, a1 in enumerate(attr_names):
        for a2 in attr_names[i + 1 :]:
            for pos in range(N):
                clues.append(_same_position(a1, solution[a1][pos], a2, solution[a2][pos]))

    for a1 in attr_names:
        for a2 in attr_names:
            for p1 in range(N):
                for p2 in range(N):
                    if p1 < p2 and (a1, solution[a1][p1]) != (a2, solution[a2][p2]):
                        clues.append(_left_of(a1, solution[a1][p1], a2, solution[a2][p2]))

    for i, a1 in enumerate(attr_names):
        for a2 in attr_names[i + 1 :]:
            for p in range(N - 1):
                clues.append(_adjacent(a1, solution[a1][p], a2, solution[a2][p + 1]))
                clues.append(_adjacent(a1, solution[a1][p + 1], a2, solution[a2][p]))

    for attr in attr_names:
        clues.append(_at_end(attr, solution[attr][0]))
        clues.append(_at_end(attr, solution[attr][-1]))

    rng.shuffle(clues)
    return clues


def count_solutions(attrs: dict[str, list[str]], clues: list[Clue], max_count: int = 2) -> int:
    """Count assignments satisfying every clue, bounded by ``max_count``."""
    attr_names = list(attrs)
    state = {"count": 0}
    partial: dict[str, list[str]] = {}

    def search(idx: int) -> None:
        """Backtracking with eager clue-violation pruning over fully-bound attribute sets."""
        if state["count"] >= max_count:
            return
        if idx == len(attr_names):
            state["count"] += 1
            return
        name = attr_names[idx]
        for perm in permutations(attrs[name]):
            partial[name] = list(perm)
            ok = True
            for c in clues:
                if all(a in partial for a in c.required_attrs) and not c.check(partial):
                    ok = False
                    break
            if ok:
                search(idx + 1)
                if state["count"] >= max_count:
                    return
        partial.pop(name, None)

    search(0)
    return state["count"]


def minimize_clues(rng: random.Random, clues: list[Clue], attrs: dict[str, list[str]]) -> list[Clue]:
    """Greedy clue minimization: drop a clue if the puzzle still has a unique solution."""
    minimal = list(clues)
    rng.shuffle(minimal)
    i = 0
    while i < len(minimal):
        trial = minimal[:i] + minimal[i + 1 :]
        if count_solutions(attrs, trial, max_count=2) == 1:
            minimal = trial
        else:
            i += 1
    return minimal


def build_puzzle(rng: random.Random) -> dict:
    """Construct one puzzle row with verified-unique solution and minimal clue set."""
    solution = random_solution(rng)
    candidates = overgenerate_clues(rng, solution)
    minimal = minimize_clues(rng, candidates, solution)
    assert count_solutions(solution, minimal, max_count=2) == 1, "minimization broke uniqueness"
    return {
        "entities": [f"position_{i + 1}" for i in range(N)],
        "attributes": {k: sorted(v) for k, v in solution.items()},
        "clues": [c.text for c in minimal],
        "solution": {
            f"position_{i + 1}": {attr: solution[attr][i] for attr in solution}
            for i in range(N)
        },
    }


def build_dataset() -> list[dict]:
    """Produce ROW_COUNT distinct puzzles deterministically from ``SEED``."""
    rng = random.Random(SEED)
    return [build_puzzle(rng) for _ in range(ROW_COUNT)]


def main() -> None:
    """Write the generated puzzles to ``data/logic_puzzles.json``."""
    rows = build_dataset()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parents[2])} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

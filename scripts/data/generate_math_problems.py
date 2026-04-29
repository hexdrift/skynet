"""Generate synthetic math word problems with deterministic ground-truth answers.

Output: ``data/math_problems.json`` (100 rows, schema ``{question, answer}``).

The data is fully self-generated — no third-party content, no licensing
concerns. Each problem is produced from a typed template that performs the
arithmetic in Python so the answer is exact by construction. Seed is fixed
for reproducibility; re-running the script produces a byte-identical file.

Usage:
    python3 scripts/data/generate_math_problems.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Callable

ROW_COUNT = 100
SEED = 42
OUTPUT = Path(__file__).resolve().parents[2] / "data" / "math_problems.json"

NAMES = [
    "Sarah", "Tom", "Maria", "James", "Li", "Ana", "Carlos", "Priya",
    "Aisha", "Yuki", "Diego", "Olivia", "Marcus", "Fatima", "Noah",
    "Zara", "Ravi", "Elena", "Kenji", "Amara",
]
ITEMS_PLURAL = [
    "apples", "books", "marbles", "stickers", "cards", "coins",
    "pens", "oranges", "candies", "ribbons", "stamps", "magnets",
]
CONTAINER_PLURALS = {
    "box": "boxes",
    "basket": "baskets",
    "drawer": "drawers",
    "bag": "bags",
    "shelf": "shelves",
    "jar": "jars",
}
CONTAINERS = list(CONTAINER_PLURALS)


def _pick(rng: random.Random, choices: list[str]) -> str:
    """Return one element from ``choices`` using the given RNG."""
    return choices[rng.randrange(len(choices))]


def _two_distinct(rng: random.Random, choices: list[str]) -> tuple[str, str]:
    """Return two distinct elements from ``choices``."""
    a, b = rng.sample(choices, 2)
    return a, b


def addition(rng: random.Random) -> tuple[str, str]:
    """Two-person addition word problem."""
    a, b = _two_distinct(rng, NAMES)
    item = _pick(rng, ITEMS_PLURAL)
    n = rng.randint(8, 99)
    m = rng.randint(8, 99)
    q = f"{a} has {n} {item}. {b} has {m} {item}. How many {item} do they have altogether?"
    return q, str(n + m)


def subtraction_give_away(rng: random.Random) -> tuple[str, str]:
    """One-person subtraction (start with N, give away M)."""
    a, b = _two_distinct(rng, NAMES)
    item = _pick(rng, ITEMS_PLURAL)
    n = rng.randint(40, 200)
    m = rng.randint(5, n - 5)
    q = f"{a} had {n} {item}. {a} gave {m} {item} to {b}. How many {item} does {a} have left?"
    return q, str(n - m)


def multiplication_groups(rng: random.Random) -> tuple[str, str]:
    """Equal-groups multiplication."""
    a = _pick(rng, NAMES)
    item = _pick(rng, ITEMS_PLURAL)
    container = _pick(rng, CONTAINERS)
    groups = rng.randint(3, 12)
    per = rng.randint(4, 25)
    q = (
        f"{a} has {groups} {CONTAINER_PLURALS[container]} of {item}. "
        f"Each {container} contains {per} {item}. How many {item} does {a} have in total?"
    )
    return q, str(groups * per)


def division_equal_share(rng: random.Random) -> tuple[str, str]:
    """Exact-division equal-share."""
    a = _pick(rng, NAMES)
    item = _pick(rng, ITEMS_PLURAL)
    people = rng.randint(3, 9)
    per = rng.randint(4, 20)
    total = people * per
    q = (
        f"{a} has {total} {item} to divide equally among {people} friends. "
        f"How many {item} does each friend receive?"
    )
    return q, str(per)


def two_step(rng: random.Random) -> tuple[str, str]:
    """Two-step problem: collect then distribute."""
    a, b = _two_distinct(rng, NAMES)
    item = _pick(rng, ITEMS_PLURAL)
    n = rng.randint(20, 80)
    times = rng.randint(2, 5)
    given = rng.randint(3, 10)
    friends = rng.randint(2, 6)
    answer = n * times - given * friends
    q = (
        f"{a} has {n} {item}. {b} has {times} times as many {item} as {a}. "
        f"{b} gives {given} {item} to each of {friends} friends. "
        f"How many {item} does {b} have left?"
    )
    return q, str(answer)


def money_change(rng: random.Random) -> tuple[str, str]:
    """Buy items, compute change."""
    a = _pick(rng, NAMES)
    item = _pick(rng, ITEMS_PLURAL)
    n = rng.randint(2, 12)
    cost = rng.randint(2, 9)
    paid = ((n * cost // 5) + 1) * 5 + rng.randint(0, 4)
    change = paid - n * cost
    q = (
        f"{a} buys {n} {item} at ${cost} each and pays with ${paid}. "
        f"How much change does {a} receive?"
    )
    return q, str(change)


def distance_time(rng: random.Random) -> tuple[str, str]:
    """Constant-speed distance."""
    speed = rng.choice([35, 40, 45, 50, 55, 60, 65, 70, 75])
    hours = rng.randint(2, 9)
    q = f"A train travels at {speed} miles per hour for {hours} hours. How many miles does it travel?"
    return q, str(speed * hours)


def rate_production(rng: random.Random) -> tuple[str, str]:
    """Items produced per hour over a duration."""
    a = _pick(rng, NAMES)
    item = _pick(rng, ITEMS_PLURAL)
    rate = rng.randint(3, 18)
    hours = rng.randint(2, 8)
    q = f"{a} makes {rate} {item} every hour. How many {item} does {a} make in {hours} hours?"
    return q, str(rate * hours)


def percentage_remaining(rng: random.Random) -> tuple[str, str]:
    """Give away a clean percentage, compute remainder."""
    a, b = _two_distinct(rng, NAMES)
    item = _pick(rng, ITEMS_PLURAL)
    pct = rng.choice([10, 20, 25, 40, 50, 60, 75, 80])
    base = rng.choice([20, 40, 50, 60, 80, 100, 120, 150, 200])
    while base * pct % 100 != 0:
        base = rng.choice([20, 40, 50, 60, 80, 100, 120, 150, 200])
    given = base * pct // 100
    q = (
        f"{a} has {base} {item} and gives {pct}% of them to {b}. "
        f"How many {item} does {a} have left?"
    )
    return q, str(base - given)


def three_step(rng: random.Random) -> tuple[str, str]:
    """Three-step problem combining purchase, share, and remainder."""
    a, b = _two_distinct(rng, NAMES)
    item = _pick(rng, ITEMS_PLURAL)
    packs = rng.randint(3, 8)
    per_pack = rng.randint(6, 12)
    given_each = rng.randint(2, 5)
    friends = rng.randint(2, 5)
    total = packs * per_pack
    given = given_each * friends
    q = (
        f"{a} buys {packs} packs of {item}, with {per_pack} {item} in each pack. "
        f"{a} gives {given_each} {item} to each of {friends} friends, and {b} gives {a} an extra "
        f"{rng.randint(2, 8)} {item}. How many {item} does {a} have after sharing but before {b}'s gift?"
    )
    return q, str(total - given)


GENERATORS: list[Callable[[random.Random], tuple[str, str]]] = [
    addition,
    subtraction_give_away,
    multiplication_groups,
    division_equal_share,
    two_step,
    money_change,
    distance_time,
    rate_production,
    percentage_remaining,
    three_step,
]


def build_dataset() -> list[dict[str, str]]:
    """Generate ROW_COUNT rows by cycling through templates with a fixed seed."""
    rng = random.Random(SEED)
    rows: list[dict[str, str]] = []
    while len(rows) < ROW_COUNT:
        gen = GENERATORS[len(rows) % len(GENERATORS)]
        q, a = gen(rng)
        rows.append({"question": q, "answer": a})
    return rows


def main() -> None:
    """Write the dataset to ``data/math_problems.json``."""
    rows = build_dataset()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parents[2])} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

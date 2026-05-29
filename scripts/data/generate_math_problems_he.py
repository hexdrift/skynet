"""Generate Hebrew math word problems mirroring ``math_problems.json``.

Output: ``data/math_problems.he.json`` (100 rows, schema ``{question, answer}``).

This module is a sibling of ``generate_math_problems.py``. It uses the same
seed (42), same RNG call order, same template ordering, and parallel name /
item / container lists so the seeded RNG picks the same indices — meaning
every row in the Hebrew file is the natural translation of the English row
at the same position, with the *exact same numerical answer*.

Usage:
    python3 scripts/data/generate_math_problems_he.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Callable

ROW_COUNT = 100
SEED = 42
OUTPUT = Path(__file__).resolve().parents[2] / "data" / "math_problems.he.json"

# Order MUST match NAMES in generate_math_problems.py so rng.sample / randrange
# pick the same indices. Second tuple field is grammatical gender, used purely
# for verb conjugation in Hebrew templates.
NAMES_HE: list[tuple[str, str]] = [
    ("שרה", "f"),
    ("תום", "m"),
    ("מריה", "f"),
    ("ג'יימס", "m"),
    ("לי", "m"),
    ("אנה", "f"),
    ("קרלוס", "m"),
    ("פריה", "f"),
    ("עאישה", "f"),
    ("יוקי", "f"),
    ("דייגו", "m"),
    ("אוליביה", "f"),
    ("מרקוס", "m"),
    ("פטימה", "f"),
    ("נח", "m"),
    ("זארה", "f"),
    ("רביב", "m"),
    ("אלנה", "f"),
    ("קנג'י", "m"),
    ("אמרה", "f"),
]
# Order MUST match ITEMS_PLURAL in generate_math_problems.py.
ITEMS_PLURAL_HE: list[str] = [
    "תפוחים", "ספרים", "גולות", "מדבקות", "קלפים", "מטבעות",
    "עטים", "תפוזים", "סוכריות", "סרטים", "בולים", "מגנטים",
]
# Order MUST match CONTAINER_PLURALS keys in generate_math_problems.py:
# box, basket, drawer, bag, shelf, jar.
CONTAINER_PLURALS_HE: dict[str, str] = {
    "קופסה": "קופסאות",
    "סל": "סלים",
    "מגירה": "מגירות",
    "שקית": "שקיות",
    "מדף": "מדפים",
    "צנצנת": "צנצנות",
}
CONTAINERS_HE: list[str] = list(CONTAINER_PLURALS_HE)


def _pick(rng: random.Random, choices: list) -> object:
    """Return one element from ``choices`` using the given RNG."""
    return choices[rng.randrange(len(choices))]


def _two_distinct(rng: random.Random, choices: list) -> tuple:
    """Return two distinct elements from ``choices``."""
    a, b = rng.sample(choices, 2)
    return a, b


def _gave(g: str) -> str:
    """Past-tense 'gave' conjugated by grammatical gender."""
    return "נתנה" if g == "f" else "נתן"


def _gives(g: str) -> str:
    """Present-tense 'gives' conjugated by grammatical gender."""
    return "נותנת" if g == "f" else "נותן"


def _makes(g: str) -> str:
    """Present-tense 'makes/produces' conjugated by grammatical gender."""
    return "מייצרת" if g == "f" else "מייצר"


def _pays(g: str) -> str:
    """Present-tense 'pays' conjugated by grammatical gender."""
    return "משלמת" if g == "f" else "משלם"


def _receives(g: str) -> str:
    """Present-tense 'receives' conjugated by grammatical gender."""
    return "מקבלת" if g == "f" else "מקבל"


def addition(rng: random.Random) -> tuple[str, str]:
    """Two-person addition word problem."""
    (a, _), (b, _) = _two_distinct(rng, NAMES_HE)
    item = _pick(rng, ITEMS_PLURAL_HE)
    n = rng.randint(8, 99)
    m = rng.randint(8, 99)
    q = f"ל-{a} יש {n} {item}. ל-{b} יש {m} {item}. כמה {item} יש להם ביחד?"
    return q, str(n + m)


def subtraction_give_away(rng: random.Random) -> tuple[str, str]:
    """One-person subtraction (start with N, give away M)."""
    (a, ga), (b, _) = _two_distinct(rng, NAMES_HE)
    item = _pick(rng, ITEMS_PLURAL_HE)
    n = rng.randint(40, 200)
    m = rng.randint(5, n - 5)
    q = (
        f"ל-{a} היו {n} {item}. {a} {_gave(ga)} {m} {item} ל-{b}. "
        f"כמה {item} נשארו ל-{a}?"
    )
    return q, str(n - m)


def multiplication_groups(rng: random.Random) -> tuple[str, str]:
    """Equal-groups multiplication."""
    a, _ = _pick(rng, NAMES_HE)
    item = _pick(rng, ITEMS_PLURAL_HE)
    container = _pick(rng, CONTAINERS_HE)
    groups = rng.randint(3, 12)
    per = rng.randint(4, 25)
    q = (
        f"ל-{a} יש {groups} {CONTAINER_PLURALS_HE[container]} של {item}. "
        f"בכל {container} יש {per} {item}. כמה {item} יש ל-{a} בסך הכל?"
    )
    return q, str(groups * per)


def division_equal_share(rng: random.Random) -> tuple[str, str]:
    """Exact-division equal-share."""
    a, _ = _pick(rng, NAMES_HE)
    item = _pick(rng, ITEMS_PLURAL_HE)
    people = rng.randint(3, 9)
    per = rng.randint(4, 20)
    total = people * per
    q = (
        f"ל-{a} יש {total} {item} לחלוקה שווה בין {people} חברים. "
        f"כמה {item} מקבל כל חבר?"
    )
    return q, str(per)


def two_step(rng: random.Random) -> tuple[str, str]:
    """Two-step problem: collect then distribute."""
    (a, _), (b, gb) = _two_distinct(rng, NAMES_HE)
    item = _pick(rng, ITEMS_PLURAL_HE)
    n = rng.randint(20, 80)
    times = rng.randint(2, 5)
    given = rng.randint(3, 10)
    friends = rng.randint(2, 6)
    answer = n * times - given * friends
    q = (
        f"ל-{a} יש {n} {item}. ל-{b} יש פי {times} {item} מאשר ל-{a}. "
        f"{b} {_gives(gb)} {given} {item} לכל אחד מ-{friends} חברים. "
        f"כמה {item} נשארו ל-{b}?"
    )
    return q, str(answer)


def money_change(rng: random.Random) -> tuple[str, str]:
    """Buy items, compute change."""
    a, ga = _pick(rng, NAMES_HE)
    item = _pick(rng, ITEMS_PLURAL_HE)
    n = rng.randint(2, 12)
    cost = rng.randint(2, 9)
    paid = ((n * cost // 5) + 1) * 5 + rng.randint(0, 4)
    change = paid - n * cost
    q = (
        f"{a} קונה {n} {item} במחיר {cost} ש\"ח ליחידה ו{_pays(ga)} {paid} ש\"ח. "
        f"כמה עודף {_receives(ga)} {a}?"
    )
    return q, str(change)


def distance_time(rng: random.Random) -> tuple[str, str]:
    """Constant-speed distance."""
    speed = rng.choice([35, 40, 45, 50, 55, 60, 65, 70, 75])
    hours = rng.randint(2, 9)
    q = (
        f"רכבת נוסעת במהירות {speed} מייל לשעה במשך {hours} שעות. "
        f"כמה מיילים היא נוסעת?"
    )
    return q, str(speed * hours)


def rate_production(rng: random.Random) -> tuple[str, str]:
    """Items produced per hour over a duration."""
    a, ga = _pick(rng, NAMES_HE)
    item = _pick(rng, ITEMS_PLURAL_HE)
    rate = rng.randint(3, 18)
    hours = rng.randint(2, 8)
    q = (
        f"{a} {_makes(ga)} {rate} {item} בכל שעה. "
        f"כמה {item} {_makes(ga)} {a} ב-{hours} שעות?"
    )
    return q, str(rate * hours)


def percentage_remaining(rng: random.Random) -> tuple[str, str]:
    """Give away a clean percentage, compute remainder."""
    (a, ga), (b, _) = _two_distinct(rng, NAMES_HE)
    item = _pick(rng, ITEMS_PLURAL_HE)
    pct = rng.choice([10, 20, 25, 40, 50, 60, 75, 80])
    base = rng.choice([20, 40, 50, 60, 80, 100, 120, 150, 200])
    while base * pct % 100 != 0:
        base = rng.choice([20, 40, 50, 60, 80, 100, 120, 150, 200])
    given = base * pct // 100
    q = (
        f"ל-{a} יש {base} {item}, ו-{a} {_gives(ga)} {pct}% מהם ל-{b}. "
        f"כמה {item} נשארו ל-{a}?"
    )
    return q, str(base - given)


def three_step(rng: random.Random) -> tuple[str, str]:
    """Three-step problem combining purchase, share, and remainder."""
    (a, ga), (b, gb) = _two_distinct(rng, NAMES_HE)
    item = _pick(rng, ITEMS_PLURAL_HE)
    packs = rng.randint(3, 8)
    per_pack = rng.randint(6, 12)
    given_each = rng.randint(2, 5)
    friends = rng.randint(2, 5)
    total = packs * per_pack
    given = given_each * friends
    extra = rng.randint(2, 8)
    q = (
        f"{a} קונה {packs} חבילות של {item}, כשבכל חבילה יש {per_pack} {item}. "
        f"{a} {_gives(ga)} {given_each} {item} לכל אחד מ-{friends} חברים, "
        f"ו-{b} {_gives(gb)} ל-{a} עוד {extra} {item}. "
        f"כמה {item} יש ל-{a} אחרי החלוקה אבל לפני המתנה מ-{b}?"
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
    """Write the dataset to ``data/math_problems.he.json``."""
    rows = build_dataset()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parents[2])} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

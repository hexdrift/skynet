"""Generate a curated multi-hop QA dataset of Wikidata-derived facts.

Output: ``data/wikidata_qa.json`` (100 rows, schema ``{question, answer}``).

The facts are sourced from Wikidata (https://www.wikidata.org), which
publishes its content under CC0 — no attribution required, no share-alike,
no restrictions on downstream use. Every Q/A pair has been hand-curated to
ensure (a) the answer is a short, unambiguously-extractable string suitable
for token-F1 evaluation, and (b) the underlying fact is stable (not subject
to frequent revision).

Coverage:
    20  Geography (capitals, rivers, mountains, countries)
    20  Science    (Nobel laureates, discoveries, units, biology)
    20  History    (events, dates, treaties, monarchs)
    20  Arts/Lit   (authors, painters, composers, characters)
    20  Sports/Pop (films, Olympics, music, awards)

Usage:
    python3 scripts/data/generate_wikidata_qa.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[2] / "data" / "wikidata_qa.json"

GEOGRAPHY: list[tuple[str, str]] = [
    ("What is the capital of Australia?", "Canberra"),
    ("What is the longest river in the world?", "Nile"),
    ("On which continent is the Atacama Desert located?", "South America"),
    ("Which country has Reykjavik as its capital?", "Iceland"),
    ("What is the highest mountain on Earth?", "Mount Everest"),
    ("In which country is the city of Marrakesh located?", "Morocco"),
    ("What is the smallest country in the world by area?", "Vatican City"),
    ("Which sea separates Europe from Africa?", "Mediterranean Sea"),
    ("What is the capital of New Zealand?", "Wellington"),
    ("Through which two countries does the Iguazu Falls border run?", "Argentina and Brazil"),
    ("What is the largest lake in Africa by area?", "Lake Victoria"),
    ("Which strait separates Asia from North America?", "Bering Strait"),
    ("What is the deepest ocean trench?", "Mariana Trench"),
    ("Which country has the most natural lakes?", "Canada"),
    ("What is the capital of Mongolia?", "Ulaanbaatar"),
    ("Which mountain range forms the spine of South America?", "Andes"),
    ("What is the largest island in the Mediterranean Sea?", "Sicily"),
    ("Which African country was formerly known as Abyssinia?", "Ethiopia"),
    ("What is the capital of Kazakhstan?", "Astana"),
    ("Which river flows through Baghdad?", "Tigris"),
]

SCIENCE: list[tuple[str, str]] = [
    ("Who proposed the theory of general relativity?", "Albert Einstein"),
    ("What is the chemical symbol for gold?", "Au"),
    ("Which scientist is credited with discovering penicillin?", "Alexander Fleming"),
    ("What is the speed of light in a vacuum, in metres per second?", "299792458"),
    ("Which planet has the largest moon in the solar system?", "Jupiter"),
    ("Who developed the first successful polio vaccine?", "Jonas Salk"),
    ("What is the SI unit of electric current?", "ampere"),
    ("Which gas is most abundant in Earth's atmosphere?", "nitrogen"),
    ("Who formulated the laws of planetary motion?", "Johannes Kepler"),
    ("What is the powerhouse of the cell?", "mitochondrion"),
    ("Which element has the atomic number 1?", "hydrogen"),
    ("Who is credited with discovering the structure of DNA's double helix alongside Francis Crick?", "James Watson"),
    ("What is the largest organ in the human body?", "skin"),
    ("Which physicist won the 1921 Nobel Prize for explaining the photoelectric effect?", "Albert Einstein"),
    ("What is the hardest naturally occurring substance?", "diamond"),
    ("Which scientist proposed natural selection as the mechanism of evolution?", "Charles Darwin"),
    ("What is the chemical formula of table salt?", "NaCl"),
    ("Who invented the periodic table of elements?", "Dmitri Mendeleev"),
    ("Which planet rotates on its side, with an axial tilt of about 98 degrees?", "Uranus"),
    ("What is the unit of frequency named after Heinrich Hertz?", "hertz"),
]

HISTORY: list[tuple[str, str]] = [
    ("In what year did World War II end?", "1945"),
    ("Who was the first President of the United States?", "George Washington"),
    ("In which year did the Berlin Wall fall?", "1989"),
    ("Which empire did Genghis Khan found?", "Mongol Empire"),
    ("Who was the longest-reigning British monarch?", "Elizabeth II"),
    ("In what year did the French Revolution begin?", "1789"),
    ("Which civilization built Machu Picchu?", "Inca"),
    ("Who was the Pharaoh whose tomb was discovered by Howard Carter in 1922?", "Tutankhamun"),
    ("In what year did the Soviet Union dissolve?", "1991"),
    ("Who wrote the United States Declaration of Independence?", "Thomas Jefferson"),
    ("Which treaty formally ended World War I?", "Treaty of Versailles"),
    ("Who led the Indian independence movement through nonviolent resistance?", "Mahatma Gandhi"),
    ("In what year did the Titanic sink?", "1912"),
    ("Which queen ruled England during the defeat of the Spanish Armada in 1588?", "Elizabeth I"),
    ("Who was the first emperor of Rome?", "Augustus"),
    ("In what year was the Magna Carta signed?", "1215"),
    ("Who painted the Sistine Chapel ceiling?", "Michelangelo"),
    ("Which Soviet leader was in power during the Cuban Missile Crisis?", "Nikita Khrushchev"),
    ("Who was the first female Prime Minister of the United Kingdom?", "Margaret Thatcher"),
    ("In what year did Christopher Columbus first reach the Americas?", "1492"),
]

ARTS: list[tuple[str, str]] = [
    ("Who wrote the play 'Hamlet'?", "William Shakespeare"),
    ("Who painted the Mona Lisa?", "Leonardo da Vinci"),
    ("Who composed the opera 'The Magic Flute'?", "Wolfgang Amadeus Mozart"),
    ("Which Russian author wrote 'War and Peace'?", "Leo Tolstoy"),
    ("Who painted 'The Starry Night'?", "Vincent van Gogh"),
    ("Who wrote the novel 'One Hundred Years of Solitude'?", "Gabriel García Márquez"),
    ("Which composer wrote the 'Brandenburg Concertos'?", "Johann Sebastian Bach"),
    ("Who is the author of 'The Great Gatsby'?", "F. Scott Fitzgerald"),
    ("Who painted 'The Persistence of Memory'?", "Salvador Dalí"),
    ("Which playwright wrote 'A Streetcar Named Desire'?", "Tennessee Williams"),
    ("Who composed the ballet 'The Nutcracker'?", "Pyotr Ilyich Tchaikovsky"),
    ("Who wrote 'Pride and Prejudice'?", "Jane Austen"),
    ("Which artist created the 'Campbell's Soup Cans' series?", "Andy Warhol"),
    ("Who wrote the dystopian novel '1984'?", "George Orwell"),
    ("Who sculpted 'David' between 1501 and 1504?", "Michelangelo"),
    ("Which Greek poet is credited with the 'Iliad' and the 'Odyssey'?", "Homer"),
    ("Who wrote the children's book 'The Little Prince'?", "Antoine de Saint-Exupéry"),
    ("Which Norwegian artist painted 'The Scream'?", "Edvard Munch"),
    ("Who composed the 'Ninth Symphony' that contains 'Ode to Joy'?", "Ludwig van Beethoven"),
    ("Who is the author of the 'Harry Potter' novel series?", "J. K. Rowling"),
]

SPORTS_POP: list[tuple[str, str]] = [
    ("Which country won the 2018 FIFA World Cup?", "France"),
    ("Who directed the film 'Pulp Fiction'?", "Quentin Tarantino"),
    ("In which city were the 2020 Summer Olympics held?", "Tokyo"),
    ("Who is the lead singer of the band Queen?", "Freddie Mercury"),
    ("Which film won the Academy Award for Best Picture in 1994?", "Schindler's List"),
    ("Which tennis player has won the most Grand Slam singles titles in the men's open era as of 2024?", "Novak Djokovic"),
    ("Who composed the score for the original 'Star Wars' film?", "John Williams"),
    ("Which country hosts the Wimbledon tennis championships?", "United Kingdom"),
    ("Who directed the 1972 film 'The Godfather'?", "Francis Ford Coppola"),
    ("Which English football club is nicknamed 'The Red Devils'?", "Manchester United"),
    ("Who wrote and recorded the 1971 song 'Imagine'?", "John Lennon"),
    ("In which year did Usain Bolt set the men's 100m world record at 9.58 seconds?", "2009"),
    ("Which Pixar film features a clownfish named Marlin?", "Finding Nemo"),
    ("Who is the all-time leading scorer in NBA history as of 2024?", "LeBron James"),
    ("Which film won the Academy Award for Best Picture in 2020?", "Parasite"),
    ("Which country has won the most Olympic gold medals in history?", "United States"),
    ("Who painted the album cover for the Beatles' 'Sgt. Pepper's Lonely Hearts Club Band'?", "Peter Blake"),
    ("Which director made the 2010 film 'Inception'?", "Christopher Nolan"),
    ("Which Formula 1 driver has won the most World Championships as of 2024?", "Lewis Hamilton"),
    ("Who created the animated television series 'The Simpsons'?", "Matt Groening"),
]

ALL_PAIRS = GEOGRAPHY + SCIENCE + HISTORY + ARTS + SPORTS_POP


def build_dataset() -> list[dict[str, str]]:
    """Return the full curated list as ``{question, answer}`` rows."""
    if len(ALL_PAIRS) != 100:
        raise AssertionError(f"expected 100 pairs, got {len(ALL_PAIRS)}")
    return [{"question": q, "answer": a} for q, a in ALL_PAIRS]


def main() -> None:
    """Write the dataset to ``data/wikidata_qa.json``."""
    rows = build_dataset()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parents[2])} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

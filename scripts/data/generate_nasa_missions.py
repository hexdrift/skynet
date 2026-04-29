"""Generate a curated catalog of NASA missions for multi-output prediction.

Output: ``data/nasa_missions.json`` (100 rows, multi-input + multi-output schema).

Schema per row:
    name           str — common mission name (e.g. "Apollo 11")
    description    str — one-sentence summary of the mission's purpose
    launch_year    int — year of launch (exact)
    mission_type   str — "crewed" | "uncrewed"
    destination    str — primary target body / orbit
    status         str — "success" | "partial_success" | "failure" | "active"

Source: every fact below is drawn from public NASA mission descriptions, which
are released under 17 USC §105 (US-Government works enter the public domain
upon publication). No attribution is required; redistribution and modification
are unrestricted.

Use cases this dataset is designed for:
    - Multi-field structured prediction (4 distinct outputs).
    - Per-field accuracy + macro-accuracy as a non-trivial composite metric.
    - Mixed numeric (year), categorical (type), and high-cardinality
      destination labels.

Usage:
    python3 scripts/data/generate_nasa_missions.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[2] / "data" / "nasa_missions.json"

# Each row: (name, description, launch_year, mission_type, destination, status)
# Status legend:
#   success         — primary objectives fully achieved
#   partial_success — major problems but core objective recovered
#   failure         — primary objectives not achieved (incl. loss of crew/vehicle)
#   active          — still operational at time of curation
MISSIONS: list[tuple[str, str, int, str, str, str]] = [
    ("Mercury-Redstone 3", "First American crewed spaceflight, a suborbital flight piloted by Alan Shepard.", 1961, "crewed", "low_earth_orbit", "success"),
    ("Mercury-Atlas 6", "First American crewed orbital flight, piloted by John Glenn for three orbits.", 1962, "crewed", "low_earth_orbit", "success"),

    ("Gemini 4", "First American spacewalk, performed by Ed White during a four-day flight.", 1965, "crewed", "low_earth_orbit", "success"),
    ("Gemini 7", "14-day endurance flight that served as rendezvous target for Gemini 6A.", 1965, "crewed", "low_earth_orbit", "success"),
    ("Gemini 8", "First docking of two spacecraft in orbit, cut short by a stuck thruster.", 1966, "crewed", "low_earth_orbit", "partial_success"),
    ("Gemini 12", "Final Gemini mission, demonstrating sustained EVA work by Buzz Aldrin.", 1966, "crewed", "low_earth_orbit", "success"),

    ("Apollo 1", "Pre-flight test ended in a launchpad cabin fire that killed all three crew members.", 1967, "crewed", "low_earth_orbit", "failure"),
    ("Apollo 7", "First crewed Apollo flight, an 11-day Earth-orbital shakedown of the Command Module.", 1968, "crewed", "low_earth_orbit", "success"),
    ("Apollo 8", "First crewed mission to leave Earth orbit and orbit the Moon.", 1968, "crewed", "moon", "success"),
    ("Apollo 9", "Earth-orbit test of the Lunar Module rendezvous and docking procedures.", 1969, "crewed", "low_earth_orbit", "success"),
    ("Apollo 10", "Lunar-orbit dress rehearsal that descended to within 15 km of the Moon's surface.", 1969, "crewed", "moon", "success"),
    ("Apollo 11", "First crewed mission to land humans on the Moon, with Armstrong and Aldrin on the surface.", 1969, "crewed", "moon", "success"),
    ("Apollo 12", "Second crewed Moon landing, touching down near the Surveyor 3 robotic lander.", 1969, "crewed", "moon", "success"),
    ("Apollo 13", "Aborted lunar landing after an oxygen tank explosion; the crew returned safely using the LM as a lifeboat.", 1970, "crewed", "moon", "partial_success"),
    ("Apollo 14", "Third crewed Moon landing, exploring the Fra Mauro highlands.", 1971, "crewed", "moon", "success"),
    ("Apollo 15", "First mission to use the Lunar Roving Vehicle, exploring Hadley-Apennine.", 1971, "crewed", "moon", "success"),
    ("Apollo 16", "Crewed landing in the Descartes Highlands with extensive geology traverses.", 1972, "crewed", "moon", "success"),
    ("Apollo 17", "Final and longest crewed Moon landing, including the only geologist astronaut.", 1972, "crewed", "moon", "success"),

    ("Skylab 2", "First crewed mission to Skylab; repaired thermal damage sustained during launch.", 1973, "crewed", "low_earth_orbit", "success"),
    ("Skylab 4", "84-day record-setting Skylab mission and final visit to the station.", 1973, "crewed", "low_earth_orbit", "success"),
    ("Apollo-Soyuz Test Project", "First crewed international docking, between an Apollo capsule and a Soviet Soyuz.", 1975, "crewed", "low_earth_orbit", "success"),

    ("Mariner 2", "First spacecraft to fly past another planet, returning Venus atmospheric data.", 1962, "uncrewed", "venus", "success"),
    ("Mariner 4", "First successful Mars flyby, returning the first close-up images of another planet.", 1964, "uncrewed", "mars", "success"),
    ("Mariner 9", "First spacecraft to enter orbit around another planet, mapping Mars from above.", 1971, "uncrewed", "mars", "success"),
    ("Mariner 10", "First spacecraft to use a gravity assist and to visit Mercury, with three flybys.", 1973, "uncrewed", "mercury", "success"),

    ("Pioneer 10", "First spacecraft to traverse the asteroid belt and to fly past Jupiter.", 1972, "uncrewed", "jupiter", "success"),
    ("Pioneer 11", "Second spacecraft to fly past Jupiter and the first to visit Saturn.", 1973, "uncrewed", "saturn", "success"),

    ("Viking 1", "First successful Mars lander, returning images and biological experiment data.", 1975, "uncrewed", "mars", "success"),
    ("Viking 2", "Second Mars lander, paired with an orbiter studying the planet's surface.", 1975, "uncrewed", "mars", "success"),

    ("Voyager 1", "Outer-planets probe that reached interstellar space and remains operational.", 1977, "uncrewed", "deep_space", "active"),
    ("Voyager 2", "Only spacecraft to visit all four outer planets, now in interstellar space.", 1977, "uncrewed", "deep_space", "active"),

    ("STS-1", "First Space Shuttle flight, an orbital test of Columbia piloted by Young and Crippen.", 1981, "crewed", "low_earth_orbit", "success"),
    ("STS-7", "First American woman in space, Sally Ride, aboard Challenger.", 1983, "crewed", "low_earth_orbit", "success"),
    ("STS-51-L", "Challenger broke apart 73 seconds after launch, killing all seven crew members.", 1986, "crewed", "low_earth_orbit", "failure"),
    ("STS-31", "Deployed the Hubble Space Telescope into low Earth orbit.", 1990, "crewed", "low_earth_orbit", "success"),
    ("STS-61", "First Hubble servicing mission, correcting the telescope's spherical aberration.", 1993, "crewed", "low_earth_orbit", "success"),
    ("STS-71", "First docking of a Space Shuttle with the Russian space station Mir.", 1995, "crewed", "low_earth_orbit", "success"),
    ("STS-88", "First Shuttle mission to assemble the International Space Station.", 1998, "crewed", "iss", "success"),
    ("STS-107", "Columbia broke apart on re-entry, killing all seven crew members.", 2003, "crewed", "low_earth_orbit", "failure"),
    ("STS-125", "Final Hubble servicing mission, extending the telescope's lifetime.", 2009, "crewed", "low_earth_orbit", "success"),
    ("STS-135", "Final flight of the Space Shuttle program.", 2011, "crewed", "iss", "success"),

    ("Magellan", "Venus orbiter that radar-mapped 98 percent of the planet's surface.", 1989, "uncrewed", "venus", "success"),
    ("Galileo", "First spacecraft to orbit Jupiter and the first to drop a probe into its atmosphere.", 1989, "uncrewed", "jupiter", "success"),
    ("Cassini-Huygens", "Saturn orbiter that delivered the Huygens probe to the surface of Titan.", 1997, "uncrewed", "saturn", "success"),
    ("Juno", "Jupiter polar orbiter studying the planet's gravity field, magnetosphere, and origin.", 2011, "uncrewed", "jupiter", "active"),

    ("Mars Pathfinder", "Mars lander that delivered the small Sojourner rover, the first wheels on Mars.", 1996, "uncrewed", "mars", "success"),
    ("Mars Global Surveyor", "Long-running Mars orbiter that mapped the planet at high resolution for nine years.", 1996, "uncrewed", "mars", "success"),
    ("Mars Climate Orbiter", "Lost on Mars arrival due to a unit-conversion error between metric and imperial.", 1998, "uncrewed", "mars", "failure"),
    ("Mars Polar Lander", "Crashed during landing on Mars due to a premature engine shutdown.", 1999, "uncrewed", "mars", "failure"),
    ("2001 Mars Odyssey", "Mars orbiter still operational and the longest-running spacecraft at Mars.", 2001, "uncrewed", "mars", "active"),
    ("Spirit", "Mars Exploration Rover that operated for over six years before becoming stuck in soft soil.", 2003, "uncrewed", "mars", "success"),
    ("Opportunity", "Mars Exploration Rover that traveled over 45 km and lasted nearly 15 years on Mars.", 2003, "uncrewed", "mars", "success"),
    ("Mars Reconnaissance Orbiter", "High-resolution Mars orbiter providing imaging and communications relay.", 2005, "uncrewed", "mars", "active"),
    ("Phoenix", "Mars polar lander that confirmed the presence of water ice in the regolith.", 2007, "uncrewed", "mars", "success"),
    ("Curiosity", "Car-sized Mars rover studying habitability in Gale Crater, still active.", 2011, "uncrewed", "mars", "active"),
    ("MAVEN", "Mars orbiter studying the upper atmosphere and the loss of the planet's air to space.", 2013, "uncrewed", "mars", "active"),
    ("InSight", "Mars stationary lander that studied seismic activity and the planet's interior.", 2018, "uncrewed", "mars", "success"),
    ("Mars 2020 Perseverance", "Mars rover collecting rock samples for future return and supporting the Ingenuity helicopter.", 2020, "uncrewed", "mars", "active"),

    ("Clementine", "Joint NASA-DoD lunar orbiter that produced the first global topographic map of the Moon.", 1994, "uncrewed", "moon", "success"),
    ("Lunar Prospector", "Polar lunar orbiter that detected hydrogen, suggesting water ice in permanently shadowed craters.", 1998, "uncrewed", "moon", "success"),
    ("LCROSS", "Lunar impactor that confirmed water in a permanently shadowed crater near the south pole.", 2009, "uncrewed", "moon", "success"),
    ("Lunar Reconnaissance Orbiter", "High-resolution lunar mapping orbiter, still active.", 2009, "uncrewed", "moon", "active"),
    ("GRAIL", "Twin lunar orbiters that produced a high-resolution gravity map of the Moon.", 2011, "uncrewed", "moon", "success"),

    ("NEAR Shoemaker", "First spacecraft to orbit and then land on an asteroid (Eros).", 1996, "uncrewed", "asteroid", "success"),
    ("Stardust", "Comet sample-return mission that captured dust from comet Wild 2.", 1999, "uncrewed", "comet", "success"),
    ("Genesis", "Solar wind sample-return mission whose capsule crashed on landing but yielded usable samples.", 2001, "uncrewed", "sun", "partial_success"),
    ("Deep Impact", "Comet mission that fired a copper impactor into comet Tempel 1 to study its interior.", 2005, "uncrewed", "comet", "success"),
    ("Dawn", "Ion-propulsion mission that orbited the asteroid Vesta and the dwarf planet Ceres.", 2007, "uncrewed", "asteroid", "success"),
    ("OSIRIS-REx", "Asteroid sample-return mission that delivered material from Bennu to Earth in 2023.", 2016, "uncrewed", "asteroid", "success"),
    ("Lucy", "Multi-target mission to visit several Jupiter Trojan asteroids.", 2021, "uncrewed", "asteroid", "active"),
    ("DART", "Kinetic-impactor planetary-defense test that altered the orbit of asteroid Dimorphos.", 2021, "uncrewed", "asteroid", "success"),

    ("New Horizons", "First spacecraft to fly past Pluto and the Kuiper Belt object Arrokoth.", 2006, "uncrewed", "pluto", "active"),

    ("SOHO", "Joint NASA-ESA solar observatory at the L1 Lagrange point.", 1995, "uncrewed", "sun", "active"),
    ("STEREO", "Twin spacecraft providing stereoscopic views of solar activity.", 2006, "uncrewed", "sun", "active"),
    ("Solar Dynamics Observatory", "Geostationary observatory imaging the Sun in multiple wavelengths.", 2010, "uncrewed", "sun", "active"),
    ("Parker Solar Probe", "Closest-ever solar approach, designed to fly through the Sun's corona.", 2018, "uncrewed", "sun", "active"),

    ("Hubble Space Telescope", "Long-running optical space telescope launched by Shuttle and serviced five times.", 1990, "uncrewed", "low_earth_orbit", "active"),
    ("Compton Gamma Ray Observatory", "Gamma-ray space telescope that operated for nine years before controlled deorbit.", 1991, "uncrewed", "low_earth_orbit", "success"),
    ("Chandra X-ray Observatory", "X-ray space telescope in a highly elliptical Earth orbit.", 1999, "uncrewed", "deep_space", "active"),
    ("Spitzer Space Telescope", "Infrared space telescope in an Earth-trailing solar orbit.", 2003, "uncrewed", "deep_space", "success"),
    ("Kepler", "Exoplanet-hunting space telescope that monitored the same field for transits.", 2009, "uncrewed", "deep_space", "success"),
    ("TESS", "Transiting Exoplanet Survey Satellite scanning the whole sky for nearby exoplanets.", 2018, "uncrewed", "deep_space", "active"),
    ("James Webb Space Telescope", "Large infrared observatory at the Sun-Earth L2 Lagrange point.", 2021, "uncrewed", "deep_space", "active"),

    ("Terra", "Flagship Earth-observing satellite carrying five remote-sensing instruments.", 1999, "uncrewed", "low_earth_orbit", "active"),
    ("Aqua", "Earth-observing satellite focused on the planet's water cycle.", 2002, "uncrewed", "low_earth_orbit", "active"),
    ("Aura", "Earth-observing satellite measuring atmospheric chemistry and ozone.", 2004, "uncrewed", "low_earth_orbit", "active"),
    ("OCO-2", "Orbiting Carbon Observatory measuring atmospheric carbon dioxide.", 2014, "uncrewed", "low_earth_orbit", "active"),
    ("ICESat-2", "Earth-orbiting altimeter measuring ice-sheet mass changes with a laser.", 2018, "uncrewed", "low_earth_orbit", "active"),
    ("Landsat 9", "Land-imaging satellite continuing the longest-running Earth-observation program.", 2021, "uncrewed", "low_earth_orbit", "active"),

    ("Expedition 1", "First long-duration crew aboard the International Space Station.", 2000, "crewed", "iss", "success"),

    ("SpaceX Demo-2", "First crewed flight of the Crew Dragon and first US commercial-crew mission to the ISS.", 2020, "crewed", "iss", "success"),
    ("Crew-1", "First operational SpaceX Crew Dragon rotation mission to the ISS.", 2020, "crewed", "iss", "success"),
    ("Boeing CFT", "First crewed flight test of Boeing's Starliner capsule to the ISS.", 2024, "crewed", "iss", "partial_success"),

    ("Artemis I", "Uncrewed test flight of the Space Launch System rocket and Orion capsule around the Moon.", 2022, "uncrewed", "moon", "success"),

    ("Pioneer Venus 1", "Venus orbiter that radar-mapped the planet at low resolution.", 1978, "uncrewed", "venus", "success"),
    ("Pioneer Venus 2", "Venus multiprobe mission that delivered four atmospheric probes.", 1978, "uncrewed", "venus", "success"),
    ("Ulysses", "Joint NASA-ESA mission that flew over the Sun's poles via a Jupiter gravity assist.", 1990, "uncrewed", "sun", "success"),
    ("MESSENGER", "First spacecraft to orbit Mercury, mapping its surface and composition.", 2004, "uncrewed", "mercury", "success"),
    ("Mars Observer", "Mars orbiter lost just before orbit insertion due to a propulsion failure.", 1992, "uncrewed", "mars", "failure"),
    ("CONTOUR", "Comet flyby mission lost shortly after a solid-rocket-motor burn.", 2002, "uncrewed", "comet", "failure"),
]


def build_dataset() -> list[dict[str, object]]:
    """Return the curated list of NASA mission rows."""
    if len(MISSIONS) != 100:
        raise AssertionError(f"expected 100 missions, got {len(MISSIONS)}")
    return [
        {
            "name": name,
            "description": description,
            "launch_year": year,
            "mission_type": mtype,
            "destination": destination,
            "status": status,
        }
        for (name, description, year, mtype, destination, status) in MISSIONS
    ]


def main() -> None:
    """Write the dataset to ``data/nasa_missions.json``."""
    rows = build_dataset()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parents[2])} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

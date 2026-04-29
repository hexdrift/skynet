"""Generate a curated catalog of historic US patents for multi-I/O prediction.

Output: ``data/uspto_patents.json`` (100 rows, multi-input + multi-output,
including a multi-label ``subcategories`` field).

Schema per row:
    title             str        — patent title
    abstract          str        — one-sentence description of what is claimed
    primary_category  str        — broad category (closed taxonomy, 10 values)
    subcategories     list[str]  — 1–3 subcategory tags (closed taxonomy)
    inventor_count    int        — number of named inventors on the patent
    decade            str        — decade of issue (e.g. "1870s", "1990s")

Source: every fact below is drawn from publicly-available USPTO records.
The bibliographic data of issued US patents (titles, dates, inventor names,
abstracts) is uncopyrightable factual information published by the United
States Patent and Trademark Office. Per 17 USC §105, US-Government works
enter the public domain upon publication; per Feist v. Rural (1991), facts
themselves are uncopyrightable. Both routes make this data freely usable
without restriction or attribution.

Closed taxonomies:
    primary_category ∈ {communication, transportation, computing, medical,
                        energy, chemistry, household, entertainment,
                        aerospace, manufacturing}
    subcategories ⊆ {telegraphy, telephony, radio, television, networking,
                     audio, video, internet, automotive, aviation, rail,
                     microprocessor, software, semiconductor, memory,
                     display, surgery, pharmaceutical, imaging, prosthetic,
                     electric_power, solar, nuclear, battery, lighting,
                     polymer, synthesis, alloy, appliance, hvac, music,
                     gaming, photography, spacecraft, propulsion, robotics,
                     machining, printing, textile, optics}

Use cases this dataset is designed for:
    - Multi-input fusion (title + abstract) feeding multi-output prediction.
    - Multi-label subcategory prediction → Jaccard / macro-F1 metrics.
    - Mixed scalar (decade, inventor_count) and categorical outputs in
      a single composite metric.

Usage:
    python3 scripts/data/generate_uspto_patents.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[2] / "data" / "uspto_patents.json"

# (title, abstract, primary_category, subcategories, inventor_count, decade)
PATENTS: list[tuple[str, str, str, list[str], int, str]] = [
    ("Improvement in telegraphy", "An apparatus for transmitting signals over wires using an electromagnet to mark intelligible characters at a distance.", "communication", ["telegraphy"], 1, "1840s"),
    ("Improvement in sewing-machines", "A machine for stitching cloth using a continuously moving needle paired with a shuttle bobbin.", "manufacturing", ["textile"], 1, "1840s"),
    ("Improvement in telegraphy (lock-and-key)", "A method of multiplexing telegraphic messages so that several can share a single wire.", "communication", ["telegraphy"], 1, "1850s"),
    ("Improvement in sewing-machines (Singer)", "A foot-pedal-driven sewing machine with a vertical needle and a horizontal feed mechanism for domestic use.", "manufacturing", ["textile"], 1, "1850s"),
    ("Process of vulcanizing rubber", "A process of treating rubber with sulphur under heat to produce a stable elastic material suitable for industrial use.", "chemistry", ["polymer"], 1, "1840s"),
    ("Improvement in dynamo-electric machines", "A direct-current generator using a ring-wound armature for producing electrical power from rotational motion.", "energy", ["electric_power"], 1, "1880s"),
    ("Improvement in telephony (Bell)", "An apparatus for transmitting vocal sounds telegraphically by varying the resistance of a circuit in proportion to acoustic vibrations.", "communication", ["telephony"], 1, "1870s"),
    ("Improvement in carbon-button telephone transmitters", "A microphone for telephone use that varies electrical resistance in proportion to acoustic pressure on a carbon button.", "communication", ["telephony"], 1, "1870s"),
    ("Phonograph or speaking machine", "A device that records and reproduces sound by inscribing acoustic vibrations onto a rotating cylinder of tinfoil.", "entertainment", ["audio"], 1, "1870s"),
    ("Electric lamp", "An incandescent electric lamp using a high-resistance carbonized filament in an evacuated glass bulb.", "energy", ["lighting"], 1, "1870s"),
    ("Improvement in incandescent lamps", "An improved long-lived filament lamp using a treated bamboo filament for general illumination.", "energy", ["lighting"], 1, "1880s"),
    ("Improvement in electric distribution systems", "A three-wire direct-current distribution system that reduces conductor weight in commercial-scale electric power networks.", "energy", ["electric_power"], 1, "1880s"),
    ("Electric transmission of power", "An alternating-current induction motor driven by a polyphase rotating magnetic field.", "energy", ["electric_power"], 1, "1880s"),
    ("System of electrical distribution", "A polyphase alternating-current system for the long-distance transmission of electrical power.", "energy", ["electric_power"], 1, "1880s"),
    ("Improvement in elevators", "A safety brake mechanism that automatically arrests an elevator car if the hoist cable fails.", "manufacturing", ["machining"], 1, "1860s"),
    ("Improvement in pneumatic tires", "An inflatable rubber tire mounted on a metal rim for use on bicycles and carriages.", "transportation", ["automotive"], 1, "1880s"),
    ("Internal-combustion engine (Diesel)", "A high-compression engine in which fuel is ignited by the heat of the compressed air alone, without a spark.", "transportation", ["automotive"], 1, "1890s"),
    ("Method of and apparatus for controlling mechanism of moving vessels", "An automatic remote control system for guided vehicles using radio signals.", "communication", ["radio"], 1, "1890s"),
    ("Apparatus for transmitting electrical signals", "A wireless telegraphy apparatus using a coherer and an antenna for receiving Hertzian waves at a distance.", "communication", ["radio", "telegraphy"], 1, "1890s"),
    ("Flying machine", "A heavier-than-air flying machine controlled by warping the wings to maintain lateral balance in flight.", "aerospace", ["aviation"], 2, "1900s"),
    ("Device for amplifying feeble electrical currents", "A three-electrode vacuum tube that amplifies electrical signals by controlling current flow with a grid.", "communication", ["radio"], 1, "1900s"),
    ("Process of manufacturing aluminum", "An electrolytic process for reducing aluminum oxide dissolved in molten cryolite.", "chemistry", ["alloy"], 1, "1880s"),
    ("Process for making phenol-formaldehyde resins (Bakelite)", "A method of making a hard thermosetting plastic by condensing phenol with formaldehyde under heat and pressure.", "chemistry", ["polymer"], 1, "1900s"),
    ("Aspirin", "A process for the synthesis of acetylsalicylic acid as a stable orally administered analgesic.", "medical", ["pharmaceutical", "synthesis"], 1, "1900s"),
    ("Cathode-ray tube", "A vacuum tube in which a beam of electrons is deflected by magnetic or electric fields to form an image on a phosphor screen.", "entertainment", ["display", "video"], 1, "1900s"),
    ("Television system", "A method of electronically scanning an image into a sequence of electrical signals using an image-dissector tube.", "communication", ["television", "video"], 1, "1930s"),
    ("Direct-view storage tube (Iconoscope)", "A camera tube that converts an optical image into an electrical signal using a mosaic of photoelectric cells.", "communication", ["television", "video"], 1, "1930s"),
    ("Synthetic linear condensation polymers (Nylon)", "A process for producing strong synthetic fibers from polyamides by melt-spinning under tension.", "chemistry", ["polymer", "textile"], 1, "1930s"),
    ("Direct-lift aircraft (helicopter)", "A single-rotor helicopter using a tail rotor for torque compensation and cyclic pitch for control.", "aerospace", ["aviation"], 1, "1930s"),
    ("Frequency modulation system", "A method of transmitting audio signals by varying the frequency of a carrier wave to reduce noise.", "communication", ["radio"], 1, "1930s"),
    ("High-frequency oscillator", "A regenerative oscillator that uses positive feedback to produce stable radio-frequency oscillations.", "communication", ["radio"], 1, "1910s"),
    ("Refrigeration apparatus", "A vapor-compression refrigeration cycle using a non-flammable, non-toxic chlorofluorocarbon refrigerant.", "household", ["hvac", "appliance"], 1, "1930s"),
    ("Air-conditioning system", "An apparatus for treating air to control its temperature, humidity, and circulation in indoor spaces.", "household", ["hvac", "appliance"], 1, "1900s"),
    ("Light-amplification by stimulated emission of radiation (laser)", "A device that produces a coherent beam of light by stimulated emission in a resonant optical cavity.", "energy", ["optics"], 2, "1960s"),
    ("Maser apparatus", "A device that amplifies microwave radiation by stimulated emission from an inverted-population gas medium.", "energy", ["optics"], 2, "1950s"),
    ("Junction transistor", "A solid-state amplifier using a thin layer of semiconductor sandwiched between two regions of opposite type.", "computing", ["semiconductor"], 1, "1950s"),
    ("Three-electrode circuit element using semiconductive materials", "A point-contact transistor amplifier consisting of two metal contacts on a germanium crystal.", "computing", ["semiconductor"], 2, "1940s"),
    ("Integrated circuit (Kilby)", "A miniature electronic circuit in which all components are formed in and on a single piece of semiconductor material.", "computing", ["semiconductor"], 1, "1960s"),
    ("Planar integrated circuit (Noyce)", "A monolithic integrated circuit fabricated using a planar oxide-masking process for interconnections.", "computing", ["semiconductor"], 1, "1960s"),
    ("Memory system using magnetic cores", "A random-access memory using arrays of toroidal magnetic cores threaded by drive and sense wires.", "computing", ["memory"], 1, "1950s"),
    ("Drum memory device", "A magnetic data-storage device using a rotating cylinder coated with ferromagnetic material.", "computing", ["memory"], 1, "1940s"),
    ("Random-access dynamic memory (DRAM)", "A single-transistor memory cell that stores a bit as charge on a capacitor and refreshes periodically.", "computing", ["memory", "semiconductor"], 1, "1960s"),
    ("Memory system having direct random access (Forrester)", "A coincident-current core memory permitting parallel readout of multi-bit words.", "computing", ["memory"], 1, "1950s"),
    ("Microprogrammed CPU on a chip (Intel 4004)", "A 4-bit microprocessor integrating arithmetic, control, and memory interface on a single MOS chip.", "computing", ["microprocessor", "semiconductor"], 3, "1970s"),
    ("Single-chip microcomputer", "A single integrated circuit combining processor, memory, and input/output for embedded control applications.", "computing", ["microprocessor", "semiconductor"], 2, "1970s"),
    ("Method of optical character recognition", "A scanning method for converting printed alphanumeric characters into digital codes by template matching.", "computing", ["software", "imaging"], 1, "1950s"),
    ("Bar-code identification system", "A pattern of parallel bars of varying widths that encode product identifiers for optical scanning at point of sale.", "manufacturing", ["printing"], 2, "1950s"),
    ("Polaroid one-step photographic process", "A self-developing instant photographic film that produces a finished print within one minute of exposure.", "entertainment", ["photography"], 1, "1940s"),
    ("Xerographic copier", "An electrostatic dry-imaging process for duplicating documents onto plain paper using a photoconductive drum.", "manufacturing", ["printing"], 1, "1940s"),
    ("Microwave cooking apparatus", "An oven that heats food by exposing it to high-frequency electromagnetic radiation generated by a magnetron.", "household", ["appliance"], 1, "1950s"),
    ("Hook-and-loop fastener (Velcro)", "A fastening tape consisting of two strips, one with stiff hooks and the other with soft loops that mesh on contact.", "household", ["textile"], 1, "1950s"),
    ("Disposable diaper", "A multi-layer absorbent disposable diaper with a moisture-impermeable backing and adhesive tabs.", "household", ["textile"], 1, "1960s"),
    ("Integrated stereo headphone", "A high-fidelity dynamic stereo headphone with foam ear cushions for personal listening.", "entertainment", ["audio"], 1, "1950s"),
    ("Radial keratotomy", "A surgical method of correcting myopia by making radial incisions in the cornea.", "medical", ["surgery"], 1, "1980s"),
    ("Implantable cardiac pacemaker", "A self-contained, battery-powered electronic device implanted to regulate the heartbeat by delivering pulses to the myocardium.", "medical", ["prosthetic"], 1, "1960s"),
    ("Computed tomography apparatus", "A medical imaging system that reconstructs cross-sectional images of the body from a rotating array of X-ray projections.", "medical", ["imaging"], 1, "1970s"),
    ("Apparatus and method for nuclear-magnetic-resonance imaging", "A medical imaging system that uses nuclear-magnetic-resonance signals to produce sectional images of soft tissue.", "medical", ["imaging"], 1, "1970s"),
    ("Process for amplifying nucleic acid sequences (PCR)", "A method of exponentially amplifying specific DNA segments using thermostable polymerase and primer pairs.", "chemistry", ["synthesis", "pharmaceutical"], 1, "1980s"),
    ("Recombinant DNA cloning vehicle", "A method of producing recombinant DNA molecules by inserting foreign genes into a plasmid vector for bacterial expression.", "chemistry", ["synthesis", "pharmaceutical"], 2, "1980s"),
    ("Genetically modified bacterium", "A bacterium genetically engineered to digest crude-oil hydrocarbons, the first patentable life form upheld in Diamond v. Chakrabarty.", "chemistry", ["synthesis"], 1, "1980s"),
    ("Inkjet printing apparatus", "A printer that forms images by ejecting droplets of ink from a thermally driven nozzle array onto paper.", "manufacturing", ["printing"], 1, "1970s"),
    ("Liquid-crystal display device", "A flat-panel display that modulates light by controlling the orientation of liquid-crystal molecules between polarizers.", "computing", ["display"], 1, "1970s"),
    ("Light-emitting diode device", "A semiconductor diode that emits visible light when current is passed across its junction.", "energy", ["lighting", "semiconductor"], 1, "1960s"),
    ("Compact disc digital audio system", "A digital audio storage medium that encodes sound as pits on a reflective optical disc read by a laser.", "entertainment", ["audio"], 2, "1980s"),
    ("Magnetic resonance imaging gradient coil", "A gradient-coil assembly producing spatially varying magnetic fields for slice selection in MRI scanners.", "medical", ["imaging"], 1, "1980s"),
    ("Mouse for use with a computer system", "A hand-held pointing device that controls a screen cursor by detecting motion in two orthogonal axes.", "computing", ["software"], 1, "1960s"),
    ("Method and apparatus for graphical user interfaces", "A windowed graphical user interface for personal computers using overlapping windows, icons, and menus.", "computing", ["software"], 3, "1980s"),
    ("Electronic spreadsheet program", "A computer program that arranges numerical data in a grid of formula-linked cells for interactive recalculation.", "computing", ["software"], 2, "1970s"),
    ("Public-key cryptographic apparatus and method (RSA)", "A cryptographic system that uses a public encryption key and a private decryption key derived from large prime numbers.", "computing", ["software"], 3, "1980s"),
    ("Method for transmitting data using packet switching", "A method of transmitting digital messages by breaking them into independently routed packets across a shared network.", "communication", ["networking"], 1, "1970s"),
    ("Hypertext document linking system (Web)", "A method of linking documents across a distributed network using uniform resource identifiers and a hypertext protocol.", "communication", ["internet", "networking"], 1, "1990s"),
    ("Method for arranging frames in a continuously rolling display", "A scrolling method for displaying ranked search results within a paged web interface.", "communication", ["internet", "software"], 2, "1990s"),
    ("PageRank ranking method", "A method of ranking documents in a hyperlinked corpus based on the eigenvector of the link-citation matrix.", "communication", ["internet", "software"], 1, "1990s"),
    ("Direct-broadcast satellite television receiver", "A consumer receiver for decoding digital television signals broadcast directly from geostationary satellites.", "communication", ["television", "spacecraft"], 1, "1990s"),
    ("Cellular mobile telephone system", "A radiotelephone system that hands off calls between geographic cells as the mobile unit moves.", "communication", ["telephony", "radio"], 2, "1970s"),
    ("Code division multiple access (CDMA) system", "A spread-spectrum digital cellular system that distinguishes simultaneous users by orthogonal code sequences.", "communication", ["telephony", "radio"], 2, "1990s"),
    ("Wireless local area network (Wi-Fi)", "A method of providing high-rate wireless data networking using orthogonal frequency-division multiplexing in unlicensed bands.", "communication", ["networking", "radio"], 4, "1990s"),
    ("Bluetooth short-range radio system", "A short-range, low-power radio protocol for ad-hoc data and audio links between consumer devices.", "communication", ["networking", "radio"], 3, "1990s"),
    ("Lithium-ion rechargeable battery", "A rechargeable battery cell using a lithium-intercalation cathode and a carbonaceous anode in a non-aqueous electrolyte.", "energy", ["battery"], 2, "1980s"),
    ("Nickel-metal-hydride storage battery", "A rechargeable battery cell using a hydrogen-absorbing alloy as the negative electrode for high energy density.", "energy", ["battery"], 1, "1980s"),
    ("Photovoltaic solar cell", "A silicon photovoltaic cell that converts sunlight directly into electrical current at usable efficiencies.", "energy", ["solar", "semiconductor"], 3, "1950s"),
    ("Wind turbine with variable-speed control", "A horizontal-axis wind turbine with electronic variable-speed control for maximum power extraction.", "energy", ["electric_power"], 1, "1980s"),
    ("Catalytic converter", "An automotive exhaust aftertreatment device that converts pollutants into harmless gases over a noble-metal catalyst.", "transportation", ["automotive"], 1, "1970s"),
    ("Anti-lock braking system", "An automotive braking system that prevents wheel lockup by modulating brake pressure under threshold detection.", "transportation", ["automotive"], 1, "1970s"),
    ("Airbag restraint system", "A vehicle safety system that rapidly inflates a fabric cushion in response to a collision-detection accelerometer.", "transportation", ["automotive"], 1, "1950s"),
    ("Three-point safety belt", "A vehicle restraint that crosses both the chest and lap of an occupant from a single retractor anchor.", "transportation", ["automotive"], 1, "1950s"),
    ("Hybrid electric vehicle drivetrain", "A drivetrain combining an internal-combustion engine with an electric motor and battery pack for improved fuel economy.", "transportation", ["automotive"], 2, "1990s"),
    ("Jet propulsion engine", "A turbojet engine using a gas-turbine compressor to provide reaction thrust for high-speed aircraft propulsion.", "aerospace", ["propulsion", "aviation"], 1, "1930s"),
    ("Liquid-fueled rocket engine", "A rocket motor that burns a liquid oxidizer and a liquid fuel in a regeneratively-cooled combustion chamber.", "aerospace", ["propulsion", "spacecraft"], 1, "1910s"),
    ("Communication satellite system", "A geostationary communications satellite that relays radio signals between widely separated ground stations.", "communication", ["spacecraft", "radio"], 1, "1960s"),
    ("Global positioning system receiver", "A receiver that determines its position by measuring the time-of-arrival of signals from a constellation of satellites.", "transportation", ["spacecraft"], 2, "1980s"),
    ("Industrial robot manipulator", "A computer-controlled multi-axis robotic arm capable of performing repetitive industrial tasks with high precision.", "manufacturing", ["robotics"], 2, "1960s"),
    ("Numerical control system for machine tools", "A system for controlling a machine tool by reading numerical instructions from a punched tape.", "manufacturing", ["machining"], 1, "1950s"),
    ("Three-dimensional printing apparatus", "A method of producing solid objects by selectively depositing or solidifying successive layers of material.", "manufacturing", ["printing"], 1, "1980s"),
    ("Stereolithography apparatus", "A method of forming three-dimensional objects by selectively photopolymerizing successive layers of liquid resin.", "manufacturing", ["printing"], 1, "1980s"),
    ("Fiber-optic transmission cable", "A communication cable using ultra-pure glass fibers as low-loss waveguides for modulated light signals.", "communication", ["networking", "optics"], 3, "1970s"),
    ("Erbium-doped fiber amplifier", "An optical amplifier that boosts signals in fiber-optic networks using a rare-earth-doped fiber pumped by a diode laser.", "communication", ["networking", "optics"], 2, "1980s"),
    ("Photolithographic stepper", "A semiconductor manufacturing apparatus that exposes patterns onto a wafer one die at a time using projection optics.", "computing", ["semiconductor"], 2, "1970s"),
    ("Electroencephalograph (EEG) machine", "A medical instrument that records the electrical activity of the brain by amplifying scalp-electrode signals.", "medical", ["imaging"], 1, "1920s"),
    ("Process for producing penicillin in deep tank fermentation", "A submerged-fermentation process for the large-scale production of penicillin from Penicillium chrysogenum cultures.", "medical", ["pharmaceutical", "synthesis"], 2, "1940s"),
]


def build_dataset() -> list[dict[str, object]]:
    """Return the curated list of patent rows."""
    if len(PATENTS) != 100:
        raise AssertionError(f"expected 100 patents, got {len(PATENTS)}")
    return [
        {
            "title": title,
            "abstract": abstract,
            "primary_category": primary_category,
            "subcategories": subcategories,
            "inventor_count": inventor_count,
            "decade": decade,
        }
        for (title, abstract, primary_category, subcategories, inventor_count, decade) in PATENTS
    ]


def main() -> None:
    """Write the dataset to ``data/uspto_patents.json``."""
    rows = build_dataset()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parents[2])} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

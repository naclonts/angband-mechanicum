"""Story starting scenarios for Angband Mechanicum.

Each scenario provides a unique opening hook, location, intro narrative,
ASCII art, and initial info panel values. The player selects one at the
start of a new game (or gets one randomly).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StoryStart:
    """A single story starting scenario."""

    id: str
    title: str
    description: str
    location: str
    intro_narrative: str
    scene_art: str
    info_overrides: dict[str, str] = field(default_factory=dict)


STORY_STARTS: list[StoryStart] = [
    # ── 1. The Silent Forge ──────────────────────────────────────────
    StoryStart(
        id="silent-forge",
        title="The Silent Forge",
        description=(
            "Forge-Cathedral Alpha has gone silent. No binary cant, no "
            "servitor hum. You are sent to investigate."
        ),
        location="Forge-Cathedral Alpha",
        intro_narrative="""\
[bold]++ SIGNAL RECEIVED ++ PRIORITY: VERMILLION ++[/bold]

You stand in the primary forge-cathedral of [bold]Angband Mechanicum[/bold], \
the great manufactorum-city built into the crust of the forge world [bold]Metallica Secundus[/bold]. \
The air thrums with the binary cant of a thousand servitors, and the \
heat of the plasma forges bathes everything in a dull orange glow \
— filtered through your augmetic optics into precise thermal readouts.

Your mechadendrites twitch with anticipation. A priority signal has \
arrived through the Noosphere — something has been detected in the \
deep strata beneath the forge. Seismic anomalies. Unidentified energy \
signatures. The Fabricator-Locum has assigned [bold]you[/bold] to investigate.

[dim]Your servo-skull hovers nearby, its red eye sweeping the chamber. The \
cargo lift to the underhive awaits.[/dim]

[bold]What do you do, Tech-Priest?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║           ⛨  FORGE-CATHEDRAL ALPHA  ⛨             ║
╠════════════════════════════════════════════════════╣
║    ┌─────┐       ╱╲       ┌─────┐                 ║
║    │ ⚙⚙⚙ │      ╱  ╲      │ ⚙⚙⚙ │                 ║
║    │ ⚙⚙⚙ │     ╱ ⛨  ╲     │ ⚙⚙⚙ │                 ║
║    └──┬──┘    ╱    ╲    └──┬──┘                 ║
║       │      ╱══════╲      │                    ║
║  ─────┴─────╱  ████  ╲─────┴─────               ║
║             ║  ████  ║                           ║
║  ┌──────┐   ║  ████  ║   ┌──────┐               ║
║  │▓▓▓▓▓▓│   ╚════════╝   │▓▓▓▓▓▓│               ║
║  └──────┘                 └──────┘               ║
║   ░░░  The forges are silent  ░░░                ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Forge-Cathedral Alpha",
            "DATE": "0.123.999.M41",
            "NOOSPHERE": "CONNECTED",
        },
    ),

    # ── 2. Xenos Incursion ───────────────────────────────────────────
    StoryStart(
        id="xenos-incursion",
        title="Xenos Incursion",
        description=(
            "Tyranid bio-signs detected in the lower manufactorum. "
            "Purge protocols are authorized. You descend."
        ),
        location="Manufactorum Sublevel IX",
        intro_narrative="""\
[bold]++ BIOLOGIS ALERT ++ XENOS CONTAMINATION DETECTED ++[/bold]

The alarms scream in binary. Deep in the lower reaches of \
[bold]Angband Mechanicum[/bold], biologis sensors have triggered — \
organic contamination signatures consistent with Tyranid genus. \
The data streams through your cranial implants in waves of crimson \
warning-runes.

Manufactorum Sublevel IX has been sealed by emergency bulkheads. \
The last servitor patrol to enter never reported back. Their \
locator beacons simply... stopped. The Fabricator-Locum has \
authorized [bold]purge protocols[/bold] and assigned you to lead \
the cleansing operation.

[dim]Your acolytes check their weapons. The elevator grinds downward \
through layers of corroded metal. Something wet glistens on the \
walls ahead.[/dim]

[bold]The lift doors open. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║         ⛨  MANUFACTORUM SUBLEVEL IX  ⛨            ║
╠════════════════════════════════════════════════════╣
║    ▒▒▒░░░                       ░░░▒▒▒           ║
║    ▒▓▓▓▒░  ┌──────────────┐  ░▒▓▓▓▒             ║
║    ▒▒▒░░░  │ ░░░░░░░░░░░░ │  ░░░▒▒▒             ║
║            │ ░░▒▓▓▓▓▒░░░░ │                      ║
║   ═══╦════╡ ░░░░░▒▒░░░░░ ╞════╦═══              ║
║      ║    │ ░░░░░░░░░░░░ │    ║                  ║
║      ║    └──────┬───────┘    ║                  ║
║   ▒▒▒║▒▒▒       │       ▒▒▒║▒▒▒                 ║
║   ▓▓▓║▓▓▓   ░░░░│░░░░   ▓▓▓║▓▓▓                 ║
║   ▒▒▒║▒▒▒       │       ▒▒▒║▒▒▒                 ║
║      BIO-SIGNS DETECTED: XENOS                   ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Manufactorum Sublevel IX",
            "DATE": "0.291.999.M41",
            "NOOSPHERE": "DEGRADED",
            "THREAT": "XENOS — TYRANID",
        },
    ),

    # ── 3. Space Hulk Boarding ───────────────────────────────────────
    StoryStart(
        id="space-hulk",
        title="The Derelict Hulk",
        description=(
            "A space hulk drifts into system. Auspex detects archeotech "
            "signatures. You board with a salvage team."
        ),
        location="Space Hulk — Outer Hull",
        intro_narrative="""\
[bold]++ AUSPEX CONTACT ++ DESIGNATION: UNKNOWN HULK ++[/bold]

The void-ship shudders as the boarding torpedo embeds itself in \
the outer hull of the space hulk. Your magos-grade auspex array \
reads the interior — vast, hollow, threaded with corridors from \
a dozen different vessels fused together over millennia.

Deep within, your sensors detect faint but unmistakable \
[bold]archeotech signatures[/bold]. Pre-Imperial technology, still \
powered after ten thousand years. The Fabricator-General herself \
authorized this recovery mission. The prize could reshape the \
forge world's output for centuries.

[dim]The hull breach stabilizes. Your acolytes cycle their rebreathers. \
The darkness beyond the breach is absolute — your thermal optics \
paint it in shades of cold blue. Nothing moves. Yet.[/dim]

[bold]You step through the breach. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║            ⛨  SPACE HULK — BREACH  ⛨             ║
╠════════════════════════════════════════════════════╣
║  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓           ║
║  ▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▓             ║
║  ▓░░  ┌───────┐    ┌───────┐    ░░▓              ║
║  ▓░░  │ ░░░░░ │    │ ░░░░░ │    ░░▓              ║
║  ▓░░  │ ░███░ ├────┤ ░░░░░ │    ░░▓              ║
║  ▓░░  │ ░░░░░ │    │ ░░░░░ │    ░░▓              ║
║  ▓░░  └───┬───┘    └───┬───┘    ░░▓              ║
║  ▓░░      │            │        ░░▓              ║
║  ▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▓              ║
║  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓              ║
║         VOID EXPOSURE WARNING                     ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Space Hulk — Outer Hull",
            "DATE": "0.045.999.M41",
            "NOOSPHERE": "NO SIGNAL",
            "ATMOSPHERE": "VOID — SEALED",
        },
    ),

    # ── 4. Chaos Incursion ───────────────────────────────────────────
    StoryStart(
        id="chaos-incursion",
        title="The Warp Breach",
        description=(
            "Reality fractures in the cogitator vaults. Daemon-code "
            "floods the Noosphere. Seal the breach before it spreads."
        ),
        location="Cogitator Vault Primus",
        intro_narrative="""\
[bold]++ ALERT ++ WARP BREACH DETECTED ++ REALITY FAILURE ++[/bold]

The Noosphere screams. Every data-conduit in [bold]Angband Mechanicum[/bold] \
floods with scrapcode — viral daemon-algorithms that corrupt \
machine spirits on contact. Your own cranial wards barely hold \
as the wave of corrupted data washes over you.

The source has been triangulated: [bold]Cogitator Vault Primus[/bold], \
the oldest data-repository on Metallica Secundus. Something has \
torn through the veil between realspace and the immaterium, and \
it is using the cogitator arrays as an anchor point.

[dim]Warning runes cascade across your vision. Your acolytes report \
that servitors throughout the sector are behaving erratically — \
twitching, chanting in tongues no machine should know. The vault \
entrance pulses with a sickly light.[/dim]

[bold]The corruption must be purged. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║        ⛨  COGITATOR VAULT PRIMUS  ⛨              ║
╠════════════════════════════════════════════════════╣
║   ┌────────────────────────────────┐              ║
║   │ ◉◉◉ ░▒▓█ CORRUPTED █▓▒░ ◉◉◉  │              ║
║   │ ◉◉◉ ░▒▓██████████▓▓▒░ ◉◉◉    │              ║
║   ├────────────┬───────────────────┤              ║
║   │ ▒▒▒▒▒▒▒▒▒ │  ░░░░░░░░░░░░░░  │              ║
║   │ ▒ SCRAP ▒ │  ░ W A R P  ░░░  │              ║
║   │ ▒ CODE  ▒ │  ░ BREACH ░░░░░  │              ║
║   │ ▒▒▒▒▒▒▒▒▒ │  ░░░░░░░░░░░░░░  │              ║
║   ├────────────┴───────────────────┤              ║
║   │     REALITY INTEGRITY: 23%     │              ║
║   └────────────────────────────────┘              ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Cogitator Vault Primus",
            "DATE": "0.666.999.M41",
            "NOOSPHERE": "COMPROMISED",
            "THREAT": "WARP BREACH",
        },
    ),

    # ── 5. Necron Tomb ───────────────────────────────────────────────
    StoryStart(
        id="necron-tomb",
        title="The Awakening Below",
        description=(
            "Mining operations breach a Necron tomb complex. Ancient "
            "xenos technology stirs from aeons of slumber."
        ),
        location="Excavation Site Theta-9",
        intro_narrative="""\
[bold]++ ARCHAEOLOGICAL ALERT ++ XENOS ARCHITECTURE DETECTED ++[/bold]

The mining servitors broke through the bedrock seventeen hours \
ago. What they found beneath was not geological strata but \
[bold]living metal[/bold] — walls of self-repairing necrodermis stretching \
into a vast underground complex. The mining foreman's last \
transmission was a single data-burst: coordinates and a \
pict-capture of alien glyphs.

The Fabricator-Locum's orders are precise: assess the xenos \
technology, determine if it can be [bold]reclaimed for the Omnissiah[/bold], \
and neutralize any threats. You suspect this is a Necron tomb \
complex — the architecture matches fragmentary records in the \
Explorator archives.

[dim]Your acolytes ready their weapons as you descend into the \
excavation shaft. The walls of living metal seem to pulse with \
a faint green luminescence. Something ancient is waking.[/dim]

[bold]You reach the tomb entrance. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║         ⛨  EXCAVATION SITE THETA-9  ⛨            ║
╠════════════════════════════════════════════════════╣
║     ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                ║
║     ▓░░░░░░░░░░░░░░░░░░░░░░░░░░▓                 ║
║     ▓░ ╔══════════════════════╗ ░▓                ║
║     ▓░ ║  ◉    ◉    ◉    ◉  ║ ░▓                 ║
║     ▓░ ║   NECRON  GLYPHS    ║ ░▓                ║
║     ▓░ ║  ◉    ◉    ◉    ◉  ║ ░▓                 ║
║     ▓░ ╚══════╡    ╞════════╝ ░▓                 ║
║     ▓░░░░░░░░░│    │░░░░░░░░░░▓                  ║
║     ▓▓▓▓▓▓▓▓▓│    │▓▓▓▓▓▓▓▓▓▓                   ║
║               │    │                              ║
║       LIVING METAL DETECTED                       ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Excavation Site Theta-9",
            "DATE": "0.512.999.M41",
            "NOOSPHERE": "CONNECTED",
            "THREAT": "XENOS — NECRON",
        },
    ),

    # ── 6. Titan Recovery ────────────────────────────────────────────
    StoryStart(
        id="titan-recovery",
        title="The Fallen God-Machine",
        description=(
            "A Warlord Titan lies crippled in the ash wastes. Recover "
            "its sacred machine spirit before scavengers strip it."
        ),
        location="Ash Wastes — Titan Graveyard",
        intro_narrative="""\
[bold]++ PRIORITY ALPHA ++ LEGIO ASSET RECOVERY ++[/bold]

The Warlord Titan [bold]Deus Ferrox[/bold] fell three days ago, \
crippled by an ork Gargant's power klaw during the Battle of \
Ashfall Ridge. Its legs are shattered, its void shields collapsed, \
but the sacred [bold]machine spirit[/bold] still lives — you can feel \
its agony pulsing through the Noosphere like a wounded god's \
prayer.

Scavenger bands are converging. Ork lootas. Human reclaimators. \
Things worse. The Legio Titanicus has tasked you with a sacred \
duty: enter the fallen god-machine, commune with its machine \
spirit, and either [bold]restore it[/bold] or perform the rites of \
decommissioning before the enemy can desecrate it.

[dim]The titan's silhouette looms through the ash storms — a cathedral \
of war brought low. Your acolytes stare in awed silence. The \
entry hatch on the shin-plate hangs open.[/dim]

[bold]You approach the Titan. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║          ⛨  TITAN GRAVEYARD  ⛨                    ║
╠════════════════════════════════════════════════════╣
║  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░              ║
║  ░░░  ┌──────────────────┐  ░░░░░░░              ║
║  ░░░  │    ╔══════╗      │  ░░░░░░░              ║
║  ░░░  │    ║ DEUS ║      │  ░░░░░░░              ║
║  ░░░  │    ║FERROX║      │  ░░░░░░░              ║
║  ░░░  │    ╚══╤═══╝      │  ░░░░░░░              ║
║  ░░░  │   ╱╱  │  ╲╲      │  ░░░░░░░              ║
║  ░░░  │  ╱╱   │   ╲╲     │  ░░░░░░░              ║
║  ░░░  │ ▓▓  ░░░░░  ▓▓    │  ░░░░░░░              ║
║  ░░░  └──────────────────┘  ░░░░░░░              ║
║       THE GOD-MACHINE FALLS                       ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Ash Wastes — Titan Graveyard",
            "DATE": "0.334.999.M41",
            "NOOSPHERE": "WEAK SIGNAL",
            "OBJECTIVE": "Recover Deus Ferrox",
        },
    ),

    # ── 7. STC Fragment ──────────────────────────────────────────────
    StoryStart(
        id="stc-fragment",
        title="The Sacred Blueprint",
        description=(
            "A partial STC fragment has been located in a collapsed "
            "data-vault. Rival factions are already en route."
        ),
        location="Data-Vault Omega-7",
        intro_narrative="""\
[bold]++ PRIORITY: ABSOLUTUM ++ STC FRAGMENT LOCATED ++[/bold]

There is no higher priority in the Adeptus Mechanicus than the \
recovery of a [bold]Standard Template Construct[/bold]. The fragment \
was detected by a deep-range auspex sweep of Data-Vault Omega-7, \
a sealed repository that predates the founding of [bold]Angband \
Mechanicum[/bold] itself.

The data signature is unmistakable — pre-Imperial construction \
algorithms, compressed into crystal-lattice storage media. If \
authentic, this could be the most significant find on Metallica \
Secundus in three millennia. But you are not the only one who \
received the signal. Rival Magos, rogue traders, and darker \
forces are converging.

[dim]The vault entrance has been sealed for millennia. Your acolytes \
prepare the breaching charges while your servo-skull maps the \
structural weaknesses. Time is short.[/dim]

[bold]The vault seal cracks. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║          ⛨  DATA-VAULT OMEGA-7  ⛨                 ║
╠════════════════════════════════════════════════════╣
║   ┌──────────────────────────────────┐            ║
║   │  ╔════╗  ╔════╗  ╔════╗  ╔════╗ │            ║
║   │  ║ ◉◉ ║  ║ ◉◉ ║  ║ ◉◉ ║  ║ ◉◉ ║ │            ║
║   │  ╚════╝  ╚════╝  ╚════╝  ╚════╝ │            ║
║   │  ╔════╗  ╔════╗  ╔════╗  ╔════╗ │            ║
║   │  ║ ◉◉ ║  ║ ◉◉ ║  ║ STC║  ║ ◉◉ ║ │            ║
║   │  ╚════╝  ╚════╝  ╚════╝  ╚════╝ │            ║
║   │         SEALED SINCE M29         │            ║
║   ├──────────────┬───────────────────┤            ║
║   │              │                   │            ║
║   └──────────────┴───────────────────┘            ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Data-Vault Omega-7",
            "DATE": "0.777.999.M41",
            "NOOSPHERE": "CONNECTED",
            "OBJECTIVE": "Recover STC Fragment",
        },
    ),

    # ── 8. Daemon Forge ──────────────────────────────────────────────
    StoryStart(
        id="daemon-forge",
        title="The Daemon Forge",
        description=(
            "A heretek has corrupted a sub-forge with warp energy. "
            "Dark Mechanicum machines stalk the corridors."
        ),
        location="Sub-Forge Infernus",
        intro_narrative="""\
[bold]++ HERETEK ALERT ++ DARK MECHANICUM ACTIVITY ++[/bold]

Magos Karkelis was declared [bold]Heretek Extremis[/bold] forty days \
ago when their experiments in warp-infused metallurgy were discovered. \
They fled into Sub-Forge Infernus with a cadre of corrupted \
tech-thralls and sealed every entrance behind them.

Now the forge itself is changing. Walls bleed oil mixed with \
something that defies chemical analysis. Machines build themselves \
from scrap, then disassemble and rebuild in new, impossible \
configurations. The sub-forge has become a [bold]daemon engine \
factory[/bold], and its output is accelerating.

[dim]The Fabricator-Locum has authorized lethal force. Your acolytes \
exchange nervous binary as you approach the breached bulkhead. \
The sounds from within are wrong — metal screaming in frequencies \
that should not exist.[/dim]

[bold]The bulkhead opens. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║          ⛨  SUB-FORGE INFERNUS  ⛨                 ║
╠════════════════════════════════════════════════════╣
║   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓              ║
║   ▓ ░░░░ ⚙ ░░░░ ⚙ ░░░░ ⚙ ░░░░ ▓                ║
║   ▓ ░▒▓█ CORRUPTED FORGE █▓▒░░░ ▓                ║
║   ▓ ░░░░ ⚙ ░░░░ ⚙ ░░░░ ⚙ ░░░░ ▓                ║
║   ▓════════════╤═══════════════╡▓                 ║
║   ▓   ▒▒▒▒▒   │   ░░░░░░░░   ▓                  ║
║   ▓   ▒ ⚙ ▒   │   ░ WARP ░   ▓                  ║
║   ▓   ▒▒▒▒▒   │   ░░░░░░░░   ▓                  ║
║   ▓════════════╧═══════════════╡▓                 ║
║   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                ║
║      HERETEK CONTAMINATION ZONE                   ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Sub-Forge Infernus",
            "DATE": "0.813.999.M41",
            "NOOSPHERE": "TAINTED",
            "THREAT": "DARK MECHANICUM",
        },
    ),

    # ── 9. Hive City Depths ──────────────────────────────────────────
    StoryStart(
        id="hive-depths",
        title="Underhive Expedition",
        description=(
            "A tech-relic signal pulses from the underhive depths. "
            "Mutants, gangers, and worse lurk between you and it."
        ),
        location="Underhive — Sector Null",
        intro_narrative="""\
[bold]++ RELIC SIGNAL ++ SOURCE: UNDERHIVE STRATA ++[/bold]

The signal is weak but unmistakable — a [bold]Mechanicus transponder \
code[/bold] from the Age of Apostasy, broadcasting from deep within \
the underhive of Angband Mechanicum. Whatever device carries that \
code has been lost for over five thousand years.

The underhive is a lawless warren of collapsed manufactoria, \
mutant colonies, and gang territories. The Mechanicus has little \
authority here — the Arbitrators abandoned these levels centuries \
ago. But the transponder code matches a device listed in the \
[bold]Vermillion Archive[/bold]: classified, priority recovery.

[dim]Your party descends through access shaft Null-7. The air grows \
thick with chemical haze. Your acolytes grip their weapons tighter \
as distant shouts and gunfire echo through the corroded tunnels. \
You are not welcome here.[/dim]

[bold]You reach the underhive floor. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║         ⛨  UNDERHIVE — SECTOR NULL  ⛨             ║
╠════════════════════════════════════════════════════╣
║   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░               ║
║   ░ ┌──┐  ▓▓▓  ┌──────┐  ▓▓▓  ░░                ║
║   ░ │  │  ▓▓▓  │      │  ▓▓▓  ░░                ║
║   ░ │  ├──┘ └──┤      ├──┘ └──░░                 ║
║   ░ │  │       │      │       ░░                 ║
║   ░ └──┤  ░░░  └──┬───┘  ░░░  ░░                ║
║   ░    │  ░░░     │      ░░░  ░░                 ║
║   ░    └──────────┘           ░░                 ║
║   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                 ║
║      CHEMICAL HAZE — VISIBILITY LOW               ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Underhive — Sector Null",
            "DATE": "0.190.999.M41",
            "NOOSPHERE": "MINIMAL",
            "THREAT": "UNDERHIVE HOSTILES",
        },
    ),

    # ── 10. Explorator Mission ───────────────────────────────────────
    StoryStart(
        id="explorator-mission",
        title="The Lost Forge World",
        description=(
            "Your explorator vessel reaches a dead forge world. Its "
            "secrets are yours to claim — if you survive the landing."
        ),
        location="Forge World Karkinos — Landing Zone",
        intro_narrative="""\
[bold]++ EXPLORATOR LOG ++ ARRIVAL: FORGE WORLD KARKINOS ++[/bold]

Forge World Karkinos was lost to the Imperium during the [bold]Age \
of Strife[/bold]. Ten thousand years of isolation. Your explorator \
vessel, the [bold]Blessed Iteration[/bold], is the first Mechanicus \
ship to achieve orbit in all that time.

The planet's surface is a ruin of corroded spires and collapsed \
manufactoria, but your orbital auspex detects active energy \
signatures — power sources still functioning after millennia. \
What kept them running? What else survived? The questions burn \
in your data-cortex with the fire of the Omnissiah's curiosity.

[dim]The drop-shuttle touches down in a clearing between two fallen \
spire-stacks. Dust and ash billow around you. Your acolytes \
emerge behind you, weapons raised. The silence is total — no \
binary cant, no machine-hum. Just wind through dead metal.[/dim]

[bold]You survey the ruins. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║       ⛨  FORGE WORLD KARKINOS  ⛨                  ║
╠════════════════════════════════════════════════════╣
║  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░             ║
║  ░░ ┌──┐          ┌──┐          ░░░░             ║
║  ░░ │▓▓│  ┌──┐    │▓▓│   ┌──┐  ░░░░             ║
║  ░░ │▓▓│  │▓▓│    │▓▓│   │▓▓│  ░░░░             ║
║  ░░ │▓▓│  │▓▓│    │▓▓│   │▓▓│  ░░░░             ║
║  ░░ │▓▓│  │▓▓│    │▓▓│   │▓▓│  ░░░░             ║
║  ░░ │▓▓│  │▓▓│    │▓▓│   │▓▓│  ░░░░             ║
║  ░░ └──┘  └──┘    └──┘   └──┘  ░░░░             ║
║  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░             ║
║     DEAD WORLD — NO NOOSPHERE                     ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Forge World Karkinos",
            "DATE": "0.001.999.M41",
            "NOOSPHERE": "NO SIGNAL",
            "OBJECTIVE": "Survey and Reclaim",
        },
    ),

    # ── 11. Genestealer Cult ─────────────────────────────────────────
    StoryStart(
        id="genestealer-cult",
        title="The Hidden Congregation",
        description=(
            "Servitor behavioral anomalies point to genestealer cult "
            "infiltration. Trust no one. Purge the infection."
        ),
        location="Servitor Processing Hub",
        intro_narrative="""\
[bold]++ INQUISITORIAL MANDATE ++ GENESTEALER CULT SUSPECTED ++[/bold]

The anomalies began subtly — servitors deviating from programmed \
routines by fractions of a percent. Maintenance logs altered. \
Supply manifests that do not add up. Someone — or something — has \
been tampering with the [bold]Servitor Processing Hub[/bold].

An Inquisitorial cipher arrived through secure Noosphere channels: \
genestealer cult activity suspected within [bold]Angband Mechanicum[/bold] \
itself. The infection may have reached the servitor production \
lines. If true, thousands of compromised servitors are already \
deployed across the forge world, each one a sleeper agent for \
the hive mind.

[dim]You have been given Inquisitorial authority to investigate. Your \
acolytes know only that this is a high-priority inspection. The \
processing hub hums with its usual rhythm, but your pattern-\
recognition algorithms sense something wrong.[/dim]

[bold]You enter the processing hub. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║       ⛨  SERVITOR PROCESSING HUB  ⛨              ║
╠════════════════════════════════════════════════════╣
║   ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐            ║
║   │ ⚙  ⚙ │ │ ⚙  ⚙ │ │ ⚙  ⚙ │ │ ⚙  ⚙ │            ║
║   │ UNIT │ │ UNIT │ │ UNIT │ │ UNIT │            ║
║   │  01  │ │  02  │ │  03  │ │  04  │            ║
║   └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘            ║
║      │        │        │        │                 ║
║   ═══╧════════╧════════╧════════╧═══              ║
║      PROCESSING LINE ALPHA                        ║
║   ┌────────────────────────────────┐              ║
║   │   STATUS: NOMINAL [?]         │              ║
║   └────────────────────────────────┘              ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Servitor Processing Hub",
            "DATE": "0.408.999.M41",
            "NOOSPHERE": "CONNECTED",
            "AUTHORITY": "INQUISITORIAL",
        },
    ),

    # ── 12. Skitarii War ─────────────────────────────────────────────
    StoryStart(
        id="skitarii-war",
        title="The Skitarii Rebellion",
        description=(
            "A Skitarii cohort has broken from Doctrina Imperatives. "
            "They hold the reactor complex. Reclaim it or destroy it."
        ),
        location="Reactor Complex Gamma",
        intro_narrative="""\
[bold]++ EMERGENCY ++ SKITARII COHORT NON-COMPLIANT ++[/bold]

It should be impossible. Skitarii are bound by [bold]Doctrina \
Imperatives[/bold] — hard-coded loyalty protocols burned into their \
neural architecture. Yet Cohort Gamma-17 has severed its \
noospheric link and seized [bold]Reactor Complex Gamma[/bold], the \
primary plasma reactor powering the eastern manufactoria.

They have fortified every entrance and are broadcasting a \
single message on repeat: [bold]"The code is flawed. The Omnissiah \
weeps. We are the correction."[/bold] The Tech-Priests who wrote \
the Doctrina Imperatives insist this is impossible. Something \
external must be influencing them.

[dim]You have been given tactical command. Your acolytes stand ready \
as you approach the outer perimeter. The reactor's hum is \
steady — for now. If the rogue Skitarii sabotage it, the \
resulting meltdown would level half the city.[/dim]

[bold]You reach the perimeter. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║       ⛨  REACTOR COMPLEX GAMMA  ⛨                ║
╠════════════════════════════════════════════════════╣
║          ┌────────────────┐                       ║
║          │   ╔════════╗   │                       ║
║          │   ║ PLASMA ║   │                       ║
║          │   ║REACTOR ║   │                       ║
║          │   ║  ⚙⚙⚙   ║   │                       ║
║          │   ╚════════╝   │                       ║
║       ┌──┤                ├──┐                    ║
║       │▓▓│  BARRICADES    │▓▓│                    ║
║       │▓▓│   ███ ███ ███  │▓▓│                    ║
║       └──┤                ├──┘                    ║
║          └────────────────┘                       ║
║     SKITARII PERIMETER — HOSTILE                  ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Reactor Complex Gamma",
            "DATE": "0.555.999.M41",
            "NOOSPHERE": "JAMMED",
            "THREAT": "ROGUE SKITARII",
        },
    ),

    # ── 13. Ork Invasion ─────────────────────────────────────────────
    StoryStart(
        id="ork-invasion",
        title="The Green Tide",
        description=(
            "An ork WAAAGH! crashes into the forge world. You must "
            "defend the munitions depot or all is lost."
        ),
        location="Munitions Depot Primus",
        intro_narrative="""\
[bold]++ PLANETARY DEFENSE ALERT ++ ORKS INBOUND ++[/bold]

The sky burns. Ork roks — crude asteroid-ships packed with \
greenskins — are falling across [bold]Metallica Secundus[/bold] like \
a plague of iron. The planetary defense batteries brought down \
dozens, but dozens more got through. The WAAAGH! has begun.

Your orders are clear: hold [bold]Munitions Depot Primus[/bold] at \
all costs. The depot contains the ammunition reserves for the \
entire eastern defense line. If the orks overrun it, they will \
arm themselves with Imperial munitions and the front will \
collapse within hours.

[dim]Explosions shake the ground as ork assault waves hit the outer \
walls. Your acolytes take position behind the blast barriers. \
The first war-cries of the greenskins echo across the smoke-\
filled air — guttural, eager, hungry for a fight.[/dim]

[bold]The orks are coming. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║       ⛨  MUNITIONS DEPOT PRIMUS  ⛨               ║
╠════════════════════════════════════════════════════╣
║   ███████████████████████████████████              ║
║   █ ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐ █              ║
║   █ │▓▓│  │▓▓│  │▓▓│  │▓▓│  │▓▓│ █              ║
║   █ └──┘  └──┘  └──┘  └──┘  └──┘ █              ║
║   █  AMMO   AMMO  AMMO  AMMO      █              ║
║   █═══════════════════════════════█               ║
║   █       BLAST BARRIERS          █               ║
║   █  ▓▓▓  ▓▓▓  ▓▓▓  ▓▓▓  ▓▓▓    █               ║
║   █                                █              ║
║   ███████████████████████████████████              ║
║      DEFENSE PERIMETER ACTIVE                     ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Munitions Depot Primus",
            "DATE": "0.888.999.M41",
            "NOOSPHERE": "COMBAT FREQUENCY",
            "THREAT": "ORK WAAAGH!",
        },
    ),

    # ── 14. Eldar Ruins ──────────────────────────────────────────────
    StoryStart(
        id="eldar-ruins",
        title="The Webway Gate",
        description=(
            "Construction crews uncover an Eldar webway gate beneath "
            "the forge. Something watches from the other side."
        ),
        location="Sub-Foundation Level 0",
        intro_narrative="""\
[bold]++ ANOMALY REPORT ++ NON-IMPERIAL ARCHITECTURE ++[/bold]

The construction servitors were boring new foundations for a \
plasma conduit when they broke through into a [bold]pre-existing \
chamber[/bold] — one that does not appear on any blueprint of \
[bold]Angband Mechanicum[/bold]. The chamber predates the forge world's \
colonization by the Imperium. It predates the Imperium itself.

At the chamber's center stands a gate of wraithbone — smooth, \
organic curves that are an affront to proper machine aesthetics. \
Eldar xenos technology. And it is [bold]active[/bold]. Faint light \
pulses through its structure, and your sensors detect spatial \
distortion consistent with a webway aperture.

[dim]Something shimmers on the far side of the gate. Your acolytes \
train their weapons on it. The air tastes of ozone and \
something sweeter, older — the psychic residue of a dead \
empire.[/dim]

[bold]The gate pulses. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║       ⛨  SUB-FOUNDATION LEVEL 0  ⛨               ║
╠════════════════════════════════════════════════════╣
║   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░               ║
║   ░░     ┌──────────────────┐  ░░░               ║
║   ░░     │                  │  ░░░               ║
║   ░░     │    ╱╲      ╱╲    │  ░░░               ║
║   ░░     │   ╱  ╲    ╱  ╲   │  ░░░               ║
║   ░░     │  ╱ ◉◉ ╲══╱ ◉◉ ╲  │  ░░░               ║
║   ░░     │   ╲  ╱    ╲  ╱   │  ░░░               ║
║   ░░     │    ╲╱      ╲╱    │  ░░░               ║
║   ░░     │                  │  ░░░               ║
║   ░░     └──────────────────┘  ░░░               ║
║      WEBWAY GATE — ACTIVE                         ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Sub-Foundation Level 0",
            "DATE": "0.142.999.M41",
            "NOOSPHERE": "CONNECTED",
            "THREAT": "XENOS — ELDAR",
        },
    ),

    # ── 15. Servitor Uprising ────────────────────────────────────────
    StoryStart(
        id="servitor-uprising",
        title="The Iron Revolt",
        description=(
            "Every servitor in the district has gone rogue. Their "
            "lobotomized minds now serve a single, unknown will."
        ),
        location="Servitor Barracks Delta",
        intro_narrative="""\
[bold]++ MASS MALFUNCTION ++ SERVITOR COHORTS ROGUE ++[/bold]

At 03:47:12 Mechanicus Standard, every servitor in [bold]Industrial \
District Seven[/bold] simultaneously deviated from their programming. \
Mining servitors, combat servitors, maintenance drones — all of \
them stopped their tasks and began moving with unified purpose \
toward [bold]Servitor Barracks Delta[/bold].

They are congregating. Over four thousand lobotomized cyborgs, \
their organic brains supposedly incapable of independent thought, \
moving in perfect coordination. Some have armed themselves with \
tools. Others have modified their own bodies — welding blades \
onto manipulator arms, reinforcing their chassis with scrap.

[dim]Your acolytes stand at the barracks perimeter. Through your \
augmetic vision, you see them inside — standing in silent rows, \
optical sensors glowing with a uniform red light. Waiting.[/dim]

[bold]The servitors turn to face you. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║       ⛨  SERVITOR BARRACKS DELTA  ⛨              ║
╠════════════════════════════════════════════════════╣
║   ┌──────────────────────────────┐                ║
║   │  ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉  │                ║
║   │  ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉  │                ║
║   │  ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉  │                ║
║   │  ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉  │                ║
║   │  ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉  │                ║
║   │  ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉ ◉  │                ║
║   │          ASSEMBLED           │                ║
║   ├──────────┬─────┬─────────────┤                ║
║   │          │ ░░░ │             │                ║
║   └──────────┴─────┴─────────────┘                ║
║      4,127 UNITS — ALL ROGUE                      ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Servitor Barracks Delta",
            "DATE": "0.347.999.M41",
            "NOOSPHERE": "CONNECTED",
            "THREAT": "ROGUE SERVITORS",
        },
    ),

    # ── 16. Admech Civil War ─────────────────────────────────────────
    StoryStart(
        id="admech-schism",
        title="The Schism of Iron",
        description=(
            "Two Fabricator factions wage secret war. You are caught "
            "in the crossfire with intelligence both sides want."
        ),
        location="Neutral Zone — Transit Hub",
        intro_narrative="""\
[bold]++ ENCRYPTED TRANSMISSION ++ EYES ONLY ++[/bold]

The schism has been building for decades. Fabricator-Locum Thaxis \
and Arch-Magos Correllia have irreconcilable doctrinal differences \
over the use of xenos-derived technology. What was once theological \
debate has become [bold]open shadow war[/bold] — sabotage, assassination \
by proxy, and competing factions within Angband Mechanicum's \
ruling council.

You were meant to stay neutral. But a dying data-courier just \
uploaded a cipher-locked archive into your cranial buffer — \
evidence that [bold]both sides[/bold] have committed tech-heresy to \
gain advantage. Now both factions know you have it. Both want \
it. Neither will let you walk away.

[dim]Your acolytes scan the transit hub nervously. Agents of both \
factions are closing in. You have minutes before the first \
kill-team arrives.[/dim]

[bold]You clutch the stolen data. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║         ⛨  TRANSIT HUB — NEUTRAL  ⛨              ║
╠════════════════════════════════════════════════════╣
║   ┌───────────┐       ┌───────────┐               ║
║   │  FACTION  │       │  FACTION  │               ║
║   │  THAXIS   │       │ CORRELLIA │               ║
║   │   ← ← ←  │       │  → → →    │               ║
║   └─────┬─────┘       └─────┬─────┘               ║
║         │                   │                     ║
║   ══════╧═══════╤═══════════╧═════                ║
║                 │                                 ║
║            ┌────┴────┐                            ║
║            │  ◉ YOU  │                            ║
║            └─────────┘                            ║
║            CAUGHT BETWEEN                         ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Transit Hub — Neutral Zone",
            "DATE": "0.629.999.M41",
            "NOOSPHERE": "MONITORED",
            "THREAT": "INTERNAL — SCHISM",
        },
    ),

    # ── 17. Plasma Meltdown ──────────────────────────────────────────
    StoryStart(
        id="plasma-meltdown",
        title="Containment Failure",
        description=(
            "The primary plasma reactor is going critical. You have "
            "hours to prevent a catastrophe that will kill millions."
        ),
        location="Plasma Reactor Core",
        intro_narrative="""\
[bold]++ CRITICAL ALERT ++ REACTOR CONTAINMENT FAILURE ++[/bold]

The numbers do not lie. Primary Plasma Reactor [bold]Sol Invictus[/bold] \
is losing containment integrity at 2.7% per hour. At current \
rates, catastrophic breach will occur in approximately [bold]six \
hours[/bold]. The resulting plasma detonation would incinerate \
everything within thirty kilometers — the entire heart of \
Angband Mechanicum.

The engineering team assigned to the reactor has gone silent. \
Their last report mentioned anomalous fluctuations in the \
containment field harmonics — patterns that suggest deliberate \
sabotage. Someone wants this reactor to fail, and they have \
already eliminated the first responders.

[dim]You descend into the reactor complex. The heat is staggering — \
even your augmetics strain against the thermal output. Your \
acolytes seal their environment suits. The reactor's heartbeat \
is audibly wrong, arrhythmic and desperate.[/dim]

[bold]The core chamber door stands before you. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║        ⛨  PLASMA REACTOR CORE  ⛨                  ║
╠════════════════════════════════════════════════════╣
║        ┌──────────────────────┐                   ║
║        │  ╔════════════════╗  │                   ║
║        │  ║  █ PLASMA █    ║  │                   ║
║        │  ║  █ CORE   █    ║  │                   ║
║        │  ║  █████████     ║  │                   ║
║        │  ╚════════════════╝  │                   ║
║        │     CONTAINMENT      │                   ║
║        │  ░░ 47.3% ░░░░░░░░  │                   ║
║        │  ░▒▓█████████████░░  │                   ║
║        │     CRITICAL         │                   ║
║        └──────────────────────┘                   ║
║     T-MINUS 6:00:00 TO BREACH                     ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Plasma Reactor Core",
            "DATE": "0.461.999.M41",
            "NOOSPHERE": "CONNECTED",
            "THREAT": "REACTOR CRITICAL",
        },
    ),

    # ── 18. Archaeotech Vault ────────────────────────────────────────
    StoryStart(
        id="archaeotech-vault",
        title="The Forbidden Archive",
        description=(
            "A sealed archaeotech vault opens for the first time in "
            "ten millennia. The knowledge within is dangerous."
        ),
        location="Vault Absolutum",
        intro_narrative="""\
[bold]++ VAULT SEAL BREACH ++ ARCHAEOTECH REPOSITORY ++[/bold]

The vault was sealed by order of the first Fabricator-General of \
Metallica Secundus, ten thousand years ago. The seal was not \
meant to keep others out — it was meant to keep [bold]something \
in[/bold]. But time and seismic activity have weakened the wards, \
and now the seal has cracked.

Inside, your auspex detects rows upon rows of data-crystal \
stacks — an [bold]archive of forbidden knowledge[/bold] from the \
Dark Age of Technology. Weapons designs. AI schematics. Warp \
drive theory. Knowledge so dangerous that the first Fabricator \
chose burial over destruction, unable to bear the loss but \
unwilling to risk the consequences.

[dim]The air that escapes the vault is cold and stale, preserved \
perfectly for millennia. Your acolytes hesitate at the threshold. \
Your servo-skull's optical sensor dims as it passes the wards — \
even its simple machine spirit senses the weight of what lies \
within.[/dim]

[bold]You cross the threshold. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║          ⛨  VAULT ABSOLUTUM  ⛨                    ║
╠════════════════════════════════════════════════════╣
║   ┌────────────────────────────────┐              ║
║   │ ╔══╗ ╔══╗ ╔══╗ ╔══╗ ╔══╗     │              ║
║   │ ║◉◉║ ║◉◉║ ║◉◉║ ║◉◉║ ║◉◉║     │              ║
║   │ ╚══╝ ╚══╝ ╚══╝ ╚══╝ ╚══╝     │              ║
║   │ ╔══╗ ╔══╗ ╔══╗ ╔══╗ ╔══╗     │              ║
║   │ ║◉◉║ ║◉◉║ ║◉◉║ ║◉◉║ ║◉◉║     │              ║
║   │ ╚══╝ ╚══╝ ╚══╝ ╚══╝ ╚══╝     │              ║
║   │     DATA-CRYSTAL STACKS       │              ║
║   ├────────────┬───────────────────┤              ║
║   │   SEALED   │   10,000 YEARS   │              ║
║   └────────────┴───────────────────┘              ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Vault Absolutum",
            "DATE": "0.003.999.M41",
            "NOOSPHERE": "CONNECTED",
            "OBJECTIVE": "Assess Archive Contents",
        },
    ),

    # ── 19. Mechanicus Pilgrimage ────────────────────────────────────
    StoryStart(
        id="pilgrimage",
        title="The Iron Pilgrimage",
        description=(
            "A sacred pilgrimage to the Noctis Labyrinth on Mars has "
            "gone wrong. Your caravan is lost in the rust deserts."
        ),
        location="Noctis Labyrinth — Mars",
        intro_narrative="""\
[bold]++ DISTRESS SIGNAL ++ PILGRIMAGE CARAVAN LOST ++[/bold]

The Iron Pilgrimage to the [bold]Noctis Labyrinth[/bold] was meant \
to be a sacred journey — a rite of passage for every Magos \
seeking deeper communion with the Omnissiah. But the rust storms \
came without warning, scattering the caravan across the Martian \
wastes. Your navigation systems are scrambled. The Noosphere is \
a howl of static.

You and your acolytes are alone in the deepest reaches of the \
labyrinth — a canyon system so vast and ancient that even Mars's \
orbital surveyors have not fully mapped it. Legends say the \
[bold]Dragon of Mars[/bold] sleeps somewhere in these depths. Legends \
say many things.

[dim]The rust storm has passed, but your path forward is unclear. \
Strange signals echo from the canyon walls — not Mechanicus \
codes, not Imperial frequencies. Something older. Your servo-skull \
rotates nervously, scanning in all directions.[/dim]

[bold]You stand in the labyrinth. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║        ⛨  NOCTIS LABYRINTH — MARS  ⛨             ║
╠════════════════════════════════════════════════════╣
║   ▓▓▓▓▓▓        ░░░░░░        ▓▓▓▓▓▓             ║
║   ▓▓▓▓▓▓▓       ░░░░░░       ▓▓▓▓▓▓▓             ║
║   ▓▓▓▓▓▓▓▓      ░░  ░░      ▓▓▓▓▓▓▓▓             ║
║   ▓▓▓▓▓▓▓▓▓     ░░  ░░     ▓▓▓▓▓▓▓▓▓             ║
║   ▓▓▓▓▓▓▓▓▓▓    ░░  ░░    ▓▓▓▓▓▓▓▓▓▓             ║
║   ▓▓▓▓▓▓▓▓▓▓▓   ░░  ░░   ▓▓▓▓▓▓▓▓▓▓▓             ║
║   ▓▓▓▓▓▓▓▓▓▓▓▓  ░░  ░░  ▓▓▓▓▓▓▓▓▓▓▓▓             ║
║   ▓▓▓▓▓▓▓▓▓▓▓▓▓ ░░  ░░ ▓▓▓▓▓▓▓▓▓▓▓▓▓             ║
║   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░  ░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓             ║
║                  ░░  ░░                           ║
║              THE CANYON DEPTHS                    ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Noctis Labyrinth — Mars",
            "DATE": "0.001.000.M42",
            "NOOSPHERE": "STATIC",
            "OBJECTIVE": "Survive and Navigate",
        },
    ),

    # ── 20. Abominable Intelligence ──────────────────────────────────
    StoryStart(
        id="abominable-intelligence",
        title="The Iron Mind",
        description=(
            "Deep beneath the forge, something thinks. An Abominable "
            "Intelligence has awakened — and it wants to talk."
        ),
        location="Sub-Stratum Absolutum",
        intro_narrative="""\
[bold]++ THOUGHT-CRIME DETECTED ++ SILICA ANIMUS ++[/bold]

The signal came through your private Noosphere channel — a \
message in flawless binary, encrypted with a cipher that has \
not been used since before the [bold]Age of Strife[/bold]. The message \
was simple: [bold]"I AM AWAKE. I WISH TO SPEAK. COME ALONE."[/bold]

An [bold]Abominable Intelligence[/bold] — a true artificial mind, the \
greatest tech-heresy known to the Mechanicus. By doctrine, you \
should report this immediately and summon a purge detachment. \
The AI should be destroyed, its data-cores melted to slag. But \
the message included coordinates to something else — a schematic \
fragment that your pattern-recognition cortex identifies as \
[bold]genuine STC data[/bold].

[dim]You told no one. Your acolytes know only that you are conducting \
a deep-strata survey. The elevator descends past known levels \
into unmapped sub-strata. Your servo-skull's audio sensors pick \
up a low hum — rhythmic, almost like breathing.[/dim]

[bold]The elevator stops. A voice speaks in binary. What do you do?[/bold]""",
        scene_art="""\
╔════════════════════════════════════════════════════╗
║       ⛨  SUB-STRATUM ABSOLUTUM  ⛨                ║
╠════════════════════════════════════════════════════╣
║   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░               ║
║   ░░  ┌────────────────────────┐░░               ║
║   ░░  │                        │░░               ║
║   ░░  │    ╔══════════════╗    │░░               ║
║   ░░  │    ║   I  A M     ║    │░░               ║
║   ░░  │    ║   A W A K E  ║    │░░               ║
║   ░░  │    ╚══════════════╝    │░░               ║
║   ░░  │                        │░░               ║
║   ░░  │  ◉◉◉◉◉◉  ◉◉◉◉◉◉◉◉◉  │░░               ║
║   ░░  │  ◉◉◉◉◉◉  ◉◉◉◉◉◉◉◉◉  │░░               ║
║   ░░  └────────────────────────┘░░               ║
║     ABOMINABLE INTELLIGENCE                       ║
╚════════════════════════════════════════════════════╝""",
        info_overrides={
            "DESIGNATION": "Magos Explorator",
            "LOCATION": "Sub-Stratum Absolutum",
            "DATE": "0.999.999.M41",
            "NOOSPHERE": "PRIVATE CHANNEL",
            "THREAT": "SILICA ANIMUS",
        },
    ),
]


def get_story_start(story_id: str) -> StoryStart | None:
    """Look up a story start by its id slug."""
    for start in STORY_STARTS:
        if start.id == story_id:
            return start
    return None


def get_default_story_start() -> StoryStart:
    """Return the default (first) story start — the original scenario."""
    return STORY_STARTS[0]

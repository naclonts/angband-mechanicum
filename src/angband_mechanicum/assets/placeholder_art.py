"""Placeholder ASCII art for the game UI."""

from __future__ import annotations

FORGE_SCENE: str = """\
        ╔══════════════════════════════════════════════════╗
        ║            ⛨  FORGE-CATHEDRAL ALPHA  ⛨           ║
        ╠══════════════════════════════════════════════════╣
        ║     ┌─────┐       ╱╲       ┌─────┐              ║
        ║     │ ⚙⚙⚙ │      ╱  ╲      │ ⚙⚙⚙ │              ║
        ║     │ ⚙⚙⚙ │     ╱ ⛨  ╲     │ ⚙⚙⚙ │              ║
        ║     └──┬──┘    ╱    ╲    └──┬──┘              ║
        ║        │      ╱══════╲      │                 ║
        ║   ─────┴─────╱  ████  ╲─────┴─────            ║
        ║              ║  ████  ║                        ║
        ║   ┌──────┐   ║  ████  ║   ┌──────┐            ║
        ║   │▓▓▓▓▓▓│   ║  ████  ║   │▓▓▓▓▓▓│            ║
        ║   │▓ANVL▓│   ╚════════╝   │▓FORG▓│            ║
        ║   │▓▓▓▓▓▓│                │▓▓▓▓▓▓│            ║
        ║   └──────┘   ┌──┐  ┌──┐   └──────┘            ║
        ║              │░░│  │░░│                        ║
        ║   ═══════════╧══╧══╧══╧═══════════            ║
        ║                                                ║
        ║    ░░░   Molten metal flows below   ░░░        ║
        ║   ░░░░░  ═══════════════════════  ░░░░░       ║
        ║    ░░░        The Omnissiah        ░░░         ║
        ║              Protects                          ║
        ╚══════════════════════════════════════════════════╝"""

TECHPRIEST_PORTRAIT: str = """\
      ┌───────────┐
      │  ╔═════╗  │
      │  ║ ◉ ▫ ║  │
      │  ║  ▬  ║  │
      │  ╚══╤══╝  │
      │  ┌──┴──┐  │
      │ ╱│ ╬╬╬ │╲ │
      │╱ │ ╬╬╬ │ ╲│
      ├──┤     ├──┤
      │▒▒│ ┌─┐ │▒▒│
      │▒▒│ │⚙│ │▒▒│
      │  │ └─┘ │  │
      │ ╿│     │╿ │
      │╱╱│     │╲╲│
      └──┴─────┴──┘
    MAGOS EXPLORATOR"""

INTRO_NARRATIVE: str = """\
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

[dim]Two acolytes have been assigned to your expedition. Your servo-skull \
hovers nearby, its red eye sweeping the chamber. The cargo lift to the \
underhive awaits.[/dim]

[bold]What do you do, Tech-Priest?[/bold]"""

CANNED_RESPONSES: list[str] = [
    (
        "You extend your mechadendrites and interface with the nearest "
        "data-terminal. Streams of binary cascade through your consciousness. "
        "The seismic readings are... unusual. Pattern analysis suggests artificial "
        "origin. Something is moving down there.\n\n"
        "[dim]Your servo-skull chirps a warning bleat.[/dim]"
    ),
    (
        "You recite the Litany of Activation and your augmetic systems "
        "hum to full power. The forge-cathedral echoes with the sound of "
        "your footsteps — half flesh, half adamantium — as you move toward "
        "the cargo lift.\n\n"
        "The lift shaft descends into darkness. Your thermal optics detect "
        "heat signatures far below — too many, and too irregular to be "
        "standard servitor patrols.\n\n"
        "[bold]++ WARNING: ANOMALOUS READINGS DETECTED ++[/bold]"
    ),
    (
        "You turn to survey your assigned acolytes. Two figures stand at "
        "attention:\n\n"
        "  [bold]Skitarius Alpha-7[/bold] — A battle-scarred ranger, galvanic "
        "rifle mag-locked to their back.\n"
        "  [bold]Enginseer Volta[/bold] — Young, eager, still more flesh than "
        "machine. Carries a power axe.\n\n"
        "[dim]They await your command.[/dim]"
    ),
    (
        "You kneel and press your palm to the forge floor. Through your "
        "haptic sensors, you feel it — a rhythmic vibration, almost like "
        "a heartbeat, pulsing from deep beneath the manufactorum.\n\n"
        "This is not geological. This is not mechanical. The pattern matches "
        "nothing in your extensive data-archives.\n\n"
        "[bold]The Omnissiah provides, but the unknown demands caution.[/bold]"
    ),
]

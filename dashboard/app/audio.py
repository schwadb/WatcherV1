"""Pick where sound comes out (TV over HDMI, the headphone jack...) and play a test tone.

Talks to the login user's PipeWire through `pactl` / `wpctl` / `pw-play`. From the
dashboard's system service that needs XDG_RUNTIME_DIR pointed at the user; userservice.user_env does that.
"""
from __future__ import annotations

import math
import re
import struct
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

from .userservice import user_env

FRIENDLY = (
    ("hdmi", "TV / monitor over HDMI"),
    ("analog", "Headphone / line-out jack"),
    ("speaker", "Built-in speaker"),
    ("usb", "USB audio"),
)


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=user_env())
        return proc.returncode, proc.stdout + proc.stderr
    except FileNotFoundError:
        return 127, f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def parse_cards(text: str) -> list[dict[str, Any]]:
    """`pactl list cards` -> [{name, description, active, profiles: [{id, description, available}]}]."""
    cards: list[dict[str, Any]] = []
    card: dict[str, Any] | None = None
    in_profiles = False
    for raw in text.splitlines():
        line = raw.strip()
        if raw.startswith("Card #"):
            card = {"name": "", "description": "", "active": "", "profiles": []}
            cards.append(card)
            in_profiles = False
            continue
        if card is None:
            continue
        if line.startswith("Name:"):
            card["name"] = line[5:].strip()
        elif line.startswith("Active Profile:"):
            card["active"] = line[15:].strip()
            in_profiles = False
        elif line.startswith("Profiles:"):
            in_profiles = True
        elif line.startswith("Ports:") or line.startswith("Properties:"):
            in_profiles = False
        elif line.startswith("device.description") or line.startswith("alsa.card_name"):
            if not card["description"]:
                card["description"] = line.split("=", 1)[1].strip().strip('"')
        elif in_profiles and ": " in line and line.split(": ", 1)[0].startswith(("output", "input", "off", "pro-audio", "a2dp", "headset")):
            pid, rest = line.split(": ", 1)  # "output:hdmi-stereo: Digital Stereo (HDMI) Output (sinks: 1, ..., available: yes)"
            m = re.search(r"available:\s*(yes|no|unknown)", rest)
            desc = rest.split("(sinks:")[0].strip()
            card["profiles"].append({"id": pid.strip(), "description": desc, "available": (m.group(1) if m else "unknown") != "no"})
    return cards


def parse_sinks(text: str) -> list[dict[str, Any]]:
    """`pactl list sinks` -> [{name, card, active_port, ports: [{id, description, type, available}]}]."""
    sinks: list[dict[str, Any]] = []
    sink: dict[str, Any] | None = None
    in_ports = False
    for raw in text.splitlines():
        line = raw.strip()
        if raw.startswith("Sink #"):
            sink = {"name": "", "card": "", "active_port": "", "ports": []}
            sinks.append(sink)
            in_ports = False
            continue
        if sink is None:
            continue
        if line.startswith("Name:"):
            sink["name"] = line[5:].strip()
        elif line.startswith("Active Port:"):
            sink["active_port"] = line[12:].strip()
            in_ports = False
        elif line.startswith("Ports:"):
            in_ports = True
        elif line.startswith("Formats:") or line.startswith("Properties:"):
            in_ports = False
        elif line.startswith("alsa.card_name") or line.startswith("device.name"):
            pass
        elif line.startswith("alsa.card ") or line.startswith("alsa.card="):
            pass
        elif in_ports and ": " in line:
            pid, rest = line.split(": ", 1)
            m_type = re.search(r"type:\s*([A-Za-z-]+)", rest)
            m_av = re.search(r"availability\s*(unknown|not available)|(available)\)?$", rest)
            desc = rest.split("(type:")[0].strip()
            avail = "not available" not in rest
            sink["ports"].append({"id": pid.strip(), "description": desc, "type": (m_type.group(1) if m_type else "").lower(), "available": avail})
        if sink and not sink["card"] and sink["name"].startswith("alsa_output."):
            sink["card"] = "alsa_card." + sink["name"].split(".", 1)[1].rsplit(".", 1)[0]  # alsa_output.X.analog-stereo -> alsa_card.X
    return sinks


PORT_LABELS = (("headphone", "Headphone jack"), ("lineout", "Line out"), ("line-out", "Line out"), ("line", "Line out"), ("speaker", "Internal speaker"), ("hdmi", "TV / monitor over HDMI"))


def port_label(port: dict[str, Any]) -> str:
    text = f"{port['id']} {port['description']} {port['type']}".lower()
    for key, label in PORT_LABELS:
        if key in text:
            return label
    return port["description"] or port["id"]


def friendly_name(profile_id: str, description: str, card_description: str) -> str:
    text = f"{profile_id} {description} {card_description}".lower()
    for key, label in FRIENDLY:
        if key in text:
            if key == "hdmi":
                m = re.search(r"extra(\d)", profile_id)
                return f"{label} (port {int(m.group(1)) + 1})" if m else label
            return label
    return description or profile_id


def outputs_from(cards: list[dict[str, Any]], sinks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Every selectable output: HDMI ports, and for the analog device one entry per jack/speaker port."""
    sinks = sinks or []
    out = []
    for card in cards:
        for p in card["profiles"]:
            if not p["id"].startswith("output:"):
                continue
            if "input" in p["id"].split("+")[0]:
                continue
            base = p["id"].split("+")[0]
            if any(o["profile"].split("+")[0] == base and o["card"] == card["name"] for o in out):
                continue  # output:analog-stereo and output:analog-stereo+input:... are the same speaker
            profile_active = card["active"].split("+")[0] == base
            sink = next((sk for sk in sinks if sk["card"] == card["name"] and base.split(":", 1)[1] in sk["name"]), None)
            if sink and len(sink["ports"]) > 1 and "hdmi" not in base:
                for port in sink["ports"]:  # the Mac Pro's analog device: internal speaker, headphone jack, line out
                    out.append({"card": card["name"], "profile": p["id"], "port": port["id"], "available": p["available"] and port["available"],
                                "label": port_label(port), "active": profile_active and sink["active_port"] == port["id"]})
                continue
            out.append({"card": card["name"], "profile": p["id"], "port": "", "available": p["available"],
                        "label": friendly_name(p["id"], p["description"], card["description"]), "active": profile_active})
    out.sort(key=lambda o: (not o["available"], 0 if "hdmi" in o["profile"] else 1, o["label"]))
    return out


def list_outputs() -> dict[str, Any]:
    code, text = _run(["pactl", "list", "cards"])
    if code != 0:
        return {"outputs": [], "error": text.strip()[:200] or "could not talk to the sound system"}
    code2, text2 = _run(["pactl", "list", "sinks"])
    return {"outputs": outputs_from(parse_cards(text), parse_sinks(text2) if code2 == 0 else []), "error": ""}


def _default_sink_for(card: str) -> str | None:
    """Sink name belonging to a card (sinks are named alsa_output.<card suffix>.<profile>)."""
    code, text = _run(["pactl", "list", "short", "sinks"])
    if code != 0:
        return None
    suffix = card.replace("alsa_card.", "")
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) > 1 and suffix in parts[1]:
            return parts[1]
    return None


def select_output(card: str, profile: str, port: str = "") -> str:
    """Switch the card to the profile, make its sink the default, and (for jacks) pick the port. Returns the sink name."""
    code, text = _run(["pactl", "set-card-profile", card, profile])
    if code != 0:
        raise RuntimeError(f"could not switch the output: {text.strip()[:200]}")
    sink = None
    for _ in range(10):  # the sink appears a moment after the profile switches
        sink = _default_sink_for(card)
        if sink:
            break
        time.sleep(0.3)
    if not sink:
        raise RuntimeError("the output switched on but no sound device appeared; is the cable connected?")
    code, text = _run(["pactl", "set-default-sink", sink])
    if code != 0:
        raise RuntimeError(f"could not make it the default: {text.strip()[:200]}")
    if port:
        code, text = _run(["pactl", "set-sink-port", sink, port])
        if code != 0:
            raise RuntimeError(f"could not switch to that jack: {text.strip()[:200]}")
    return sink


def apply_saved(choice: dict[str, Any] | None) -> str:
    """Re-apply the remembered output (dashboard start-up); jack sensing on some machines flips it back."""
    if not choice or not choice.get("card") or not choice.get("profile"):
        return "no saved output"
    return select_output(str(choice["card"]), str(choice["profile"]), str(choice.get("port") or ""))


def tone_file(cache_dir: Path, seconds: float = 1.2, hz: float = 440.0) -> Path:
    path = cache_dir / "test-tone.wav"
    if not path.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        rate = 48000
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(rate)
            frames = bytearray()
            n = int(rate * seconds)
            for i in range(n):
                env = min(1.0, i / 2000, (n - i) / 2000)  # soft start and end
                v = int(12000 * env * math.sin(2 * math.pi * hz * i / rate))
                frames += struct.pack("<hh", v, v)
            w.writeframes(bytes(frames))
    return path


def test_tone(cache_dir: Path) -> str:
    path = tone_file(cache_dir)
    for cmd in (["pw-play", str(path)], ["paplay", str(path)], ["aplay", "-q", str(path)]):
        code, text = _run(cmd, timeout=20)
        if code == 0:
            return f"played a tone through {cmd[0]}"
        if code != 127:
            last = text.strip()[:200]
            break
    else:
        last = "no audio player found (pipewire's pw-play)"
    raise RuntimeError(f"could not play the test tone: {last}")

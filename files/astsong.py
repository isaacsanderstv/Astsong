#!/usr/bin/env python3
"""astsong - hear your code.

Walks the abstract syntax tree of a Python file and turns it into music.
Same code in, same song out. Zero dependencies (standard library only).

    python astsong.py my_script.py -o song.mid --wav song.wav
"""
from __future__ import annotations

import argparse
import array
import ast
import math
import sys
import wave
import zlib
from dataclasses import dataclass
from pathlib import Path

__version__ = "0.1.0"

TPQ = 480  # MIDI ticks per quarter note

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SCALES = {
    "lydian": [0, 2, 4, 6, 7, 9, 11],  # bright, floaty
    "pentatonic": [0, 2, 4, 7, 9],  # can't sound wrong
    "dorian": [0, 2, 3, 5, 7, 9, 10],  # moody but warm
    "minor": [0, 2, 3, 5, 7, 8, 10],  # dark
}

# Node types that make code "branchy". More branching -> darker scale.
BRANCHY = tuple(
    getattr(ast, name)
    for name in ("If", "For", "While", "Try", "BoolOp", "IfExp", "Match")
    if hasattr(ast, name)
)


@dataclass(frozen=True)
class Note:
    start: int  # ticks
    dur: int  # ticks
    pitch: int  # MIDI note number
    vel: int  # 1-127


def label(node: ast.AST) -> str:
    """A stable string that identifies a node, so recurring names recur musically."""
    kind = type(node).__name__
    for attr in ("id", "name", "attr", "arg"):
        value = getattr(node, attr, None)
        if isinstance(value, str):
            return f"{kind}:{value}"
    if isinstance(node, ast.Constant):
        return f"Constant:{node.value!r}"
    return kind


def pick_scale(tree: ast.AST) -> str:
    nodes = list(ast.walk(tree))
    stmts = sum(isinstance(n, ast.stmt) for n in nodes) or 1
    ratio = sum(isinstance(n, BRANCHY) for n in nodes) / stmts
    if ratio < 0.10:
        return "lydian"
    if ratio < 0.25:
        return "pentatonic"
    if ratio < 0.45:
        return "dorian"
    return "minor"


class Composer:
    """Depth-first walk of an AST that emits notes."""

    def __init__(self, root: int, scale: str):
        self.root = root
        self.scale = SCALES[scale]
        self.cursor = 0
        self.notes: list[Note] = []

    # -- helpers ----------------------------------------------------------
    def _octave(self, depth: int) -> int:
        return min(depth // 3, 3)  # deeper code sings higher

    def _vel(self, depth: int) -> int:
        return max(40, 100 - depth * 4)  # deeper code is quieter

    def _degree_pitch(self, degree: int, depth: int) -> int:
        n = len(self.scale)
        octave_up, idx = divmod(degree, n)
        return self.root + self.scale[idx] + 12 * (self._octave(depth) + octave_up)

    def _emit(self, pitch: int, dur: int, depth: int, at: int | None = None) -> None:
        start = self.cursor if at is None else at
        self.notes.append(Note(start, dur, max(0, min(127, pitch)), self._vel(depth)))

    # -- musical gestures -------------------------------------------------
    def single(self, key: str, depth: int, step: int) -> None:
        degree = zlib.crc32(key.encode()) % len(self.scale)
        self._emit(self._degree_pitch(degree, depth), step * 2, depth)
        self.cursor += step

    def chord(self, depth: int) -> None:  # def / class: a triad rings out
        base = max(28, self.root - 12 + 12 * self._octave(depth))
        for degree in (0, 2, 4):
            n = len(self.scale)
            octave_up, idx = divmod(degree, n)
            self._emit(base + self.scale[idx] + 12 * octave_up, TPQ * 2, depth)
        self.cursor += TPQ

    def arpeggio(self, key: str, depth: int) -> None:  # for / while: runs upward
        start = zlib.crc32(key.encode()) % len(self.scale)
        for i in range(4):
            self._emit(self._degree_pitch(start + i, depth), TPQ // 2, depth)
            self.cursor += TPQ // 4

    def tritone(self, depth: int) -> None:  # raise: the devil's interval
        p = self._degree_pitch(0, depth)
        self._emit(p, TPQ, depth)
        self._emit(p + 6, TPQ, depth)
        self.cursor += TPQ

    def clash(self, depth: int) -> None:  # except: a minor-second wince
        p = self._degree_pitch(0, depth)
        self._emit(p, TPQ // 2, depth)
        self._emit(p + 1, TPQ // 2, depth)
        self.cursor += TPQ // 2

    def resolve(self, depth: int) -> None:  # return: back home, one octave down
        self._emit(self.root - 12, TPQ, depth)
        self.cursor += TPQ

    # -- the walk ---------------------------------------------------------
    def visit(self, node: ast.AST, depth: int = 0) -> None:
        if isinstance(node, ast.expr_context):
            return  # Load/Store/Del carry no information worth hearing
        key = label(node)
        step = TPQ // 2 if isinstance(node, ast.stmt) else TPQ // 4

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self.chord(depth)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            self.arpeggio(key, depth)
        elif isinstance(node, ast.Raise):
            self.tritone(depth)
        elif isinstance(node, ast.ExceptHandler):
            self.clash(depth)
        elif isinstance(node, ast.Return):
            self.resolve(depth)
        elif isinstance(node, ast.If):
            self.cursor += TPQ // 4  # a breath before a decision
            self.single(key, depth, step)
        else:
            self.single(key, depth, step)

        for child in ast.iter_child_nodes(node):
            self.visit(child, depth + 1)


def compose(source: str, scale: str = "auto", root: int | None = None) -> tuple[list[Note], str, int]:
    """Return (notes, scale_name, root_midi_note) for a piece of Python source."""
    tree = ast.parse(source)
    if scale == "auto":
        scale = pick_scale(tree)
    if root is None:
        root = 48 + zlib.crc32(source.encode()) % 12  # every file gets its own key
    composer = Composer(root, scale)
    composer.visit(tree)
    return composer.notes, scale, root


# -- MIDI output -----------------------------------------------------------
def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def write_midi(notes: list[Note], path: str, bpm: int = 110, program: int = 11) -> None:
    """Write a single-track Standard MIDI File. Program 11 = vibraphone."""
    events: list[tuple[int, int, bytes]] = [
        (0, 0, b"\xff\x51\x03" + (60_000_000 // bpm).to_bytes(3, "big")),
        (0, 1, bytes([0xC0, program])),
    ]
    for n in notes:
        events.append((n.start, 3, bytes([0x90, n.pitch, n.vel])))
        events.append((n.start + n.dur, 2, bytes([0x80, n.pitch, 0])))
    events.sort(key=lambda e: (e[0], e[1]))  # note-offs sort before note-ons

    track = bytearray()
    last = 0
    for tick, _, data in events:
        track += _vlq(tick - last) + data
        last = tick
    track += _vlq(0) + b"\xff\x2f\x00"

    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + TPQ.to_bytes(2, "big")
    with open(path, "wb") as f:
        f.write(header + b"MTrk" + len(track).to_bytes(4, "big") + bytes(track))


# -- WAV output (tiny additive synth) ---------------------------------------
def render_wav(notes: list[Note], path: str, bpm: int = 110, rate: int = 22050) -> None:
    sec_per_tick = 60 / (bpm * TPQ)
    total = max(n.start + n.dur for n in notes) * sec_per_tick + 1.0
    buf = [0.0] * int(total * rate)
    attack = int(0.01 * rate)

    for n in notes:
        freq = 440 * 2 ** ((n.pitch - 69) / 12)
        w = 2 * math.pi * freq / rate
        t0 = int(n.start * sec_per_tick * rate)
        length = int((n.dur * sec_per_tick + 0.25) * rate)
        amp = n.vel / 127 * 0.15
        end = min(length, len(buf) - t0)
        for i in range(end):
            env = min(1.0, i / attack) * math.exp(-3.0 * i / rate)  # soft pluck
            buf[t0 + i] += amp * env * (math.sin(w * i) + 0.4 * math.sin(2 * w * i) + 0.2 * math.sin(3 * w * i))

    peak = max(abs(x) for x in buf) or 1.0
    gain = 0.9 / peak if peak > 0.9 else 1.0
    pcm = array.array("h", (int(max(-1.0, min(1.0, x * gain)) * 32767) for x in buf))
    if sys.byteorder == "big":
        pcm.byteswap()
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())


# -- CLI -------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="astsong", description="Turn Python source code into music.")
    p.add_argument("source", help="Python file to sonify, or - for stdin")
    p.add_argument("-o", "--output", help="MIDI output path (default: <source>.mid)")
    p.add_argument("--wav", metavar="PATH", help="also render a WAV file")
    p.add_argument("--bpm", type=int, default=110)
    p.add_argument("--scale", choices=["auto", *SCALES], default="auto")
    p.add_argument("--instrument", type=int, default=11, help="General MIDI program 0-127 (default 11, vibraphone)")
    p.add_argument("--version", action="version", version=f"astsong {__version__}")
    args = p.parse_args(argv)

    text = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8")
    try:
        notes, scale, root = compose(text, args.scale)
    except SyntaxError as e:
        print(f"astsong: can't hear that, it isn't valid Python ({e.msg}, line {e.lineno})", file=sys.stderr)
        return 1
    if not notes:
        print("astsong: nothing to play (empty file?)", file=sys.stderr)
        return 1

    out = args.output or ("song.mid" if args.source == "-" else str(Path(args.source).with_suffix(".mid")))
    write_midi(notes, out, args.bpm, args.instrument)
    seconds = max(n.start + n.dur for n in notes) * 60 / (args.bpm * TPQ)
    print(f"key: {NOTE_NAMES[root % 12]} {scale} | {len(notes)} notes | {seconds:.1f}s -> {out}")

    if args.wav:
        render_wav(notes, args.wav, args.bpm)
        print(f"rendered -> {args.wav}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

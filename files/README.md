# 🎼 astsong

**Hear your code.** `astsong` walks the abstract syntax tree of a Python file and turns it into music: a MIDI file, plus an optional WAV rendered by a tiny built-in synth.

Zero dependencies. One file. Deterministic: the same code always plays the same song.

```bash
python astsong.py my_script.py -o song.mid --wav song.wav
# key: D dorian | 412 notes | 61.3s -> song.mid
```

Try it on itself:

```bash
python astsong.py astsong.py --wav self.wav
```

## How code becomes music

| Code | Sound |
|---|---|
| Every file | Gets its own **key** (hash of the source) |
| Branch-heavy code | Darker scale (`lydian` → `pentatonic` → `dorian` → `minor`) |
| `def` / `class` | A **chord** that rings over what follows |
| `for` / `while` | A rising **arpeggio** |
| `if` | A short breath, then a note |
| `return` | A low note, **back to the root** |
| `raise` | A **tritone**, the devil's interval |
| `except` | A **minor-second** wince |
| Variable / attribute / literal names | Hashed to a pitch, so a name **recurs as a motif** |
| Nesting depth | Deeper code is **higher** and **quieter** |

## Options

```
astsong SOURCE [-o OUT.mid] [--wav OUT.wav] [--bpm 110]
        [--scale auto|lydian|pentatonic|dorian|minor]
        [--instrument 0-127]    # General MIDI program, default 11 (vibraphone)
```

Use `-` as `SOURCE` to read from stdin:

```bash
git show HEAD:app.py | python astsong.py - -o commit.mid
```

## Tests

```bash
python -m unittest -v
```

## Ideas / roadmap

- [ ] Sonify a whole repo as an album (one track per file)
- [ ] Git history mode: one bar per commit, diff size drives dynamics
- [ ] JavaScript / Go support via tree-sitter
- [ ] Stereo panning by module

## License

MIT

import os
import tempfile
import unittest
import wave

import astsong

SAMPLE = '''
def greet(name):
    for i in range(3):
        if i % 2:
            print(name)
    return name

try:
    greet("world")
except Exception:
    raise ValueError("boom")
'''


class TestAstsong(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(astsong.compose(SAMPLE), astsong.compose(SAMPLE))

    def test_notes_are_valid_midi(self):
        notes, _, _ = astsong.compose(SAMPLE)
        self.assertTrue(notes)
        for n in notes:
            self.assertTrue(0 <= n.pitch <= 127)
            self.assertTrue(1 <= n.vel <= 127)
            self.assertGreater(n.dur, 0)

    def test_raise_is_a_tritone(self):
        notes, _, _ = astsong.compose("raise ValueError()", scale="minor")
        by_start = {}
        for n in notes:
            by_start.setdefault(n.start, []).append(n.pitch)
        self.assertTrue(any(len(p) == 2 and abs(p[0] - p[1]) == 6 for p in by_start.values()))

    def test_same_name_same_pitch_at_same_depth(self):
        notes, _, _ = astsong.compose("x = 1\nx = 2", scale="pentatonic", root=60)
        # both Name:x nodes sit at the same depth, so they must share a pitch
        pitches = [n.pitch for n in notes]
        self.assertGreaterEqual(pitches.count(pitches[1]), 2)

    def test_midi_file_structure(self):
        notes, _, _ = astsong.compose(SAMPLE)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.mid")
            astsong.write_midi(notes, path)
            with open(path, "rb") as f:
                data = f.read()
        self.assertEqual(data[:4], b"MThd")
        self.assertEqual(data[14:18], b"MTrk")
        self.assertEqual(data[-3:], b"\xff\x2f\x00")
        track_len = int.from_bytes(data[18:22], "big")
        self.assertEqual(len(data), 22 + track_len)

    def test_wav_renders(self):
        notes, _, _ = astsong.compose("a = 1")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.wav")
            astsong.render_wav(notes, path)
            with wave.open(path) as w:
                self.assertGreater(w.getnframes(), 0)

    def test_syntax_error_is_friendly(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "bad.py")
            with open(src, "w") as f:
                f.write("def (:")
            self.assertEqual(astsong.main([src, "-o", os.path.join(d, "x.mid")]), 1)


if __name__ == "__main__":
    unittest.main()

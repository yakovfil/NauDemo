"""Regression checks for the original vector font decoder and game art."""
import json
from pathlib import Path
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
from extract_battlezone_models import extract_glyphs


class OriginalArtTests(unittest.TestCase):
    def decode(self, words):
        memory = {}
        for address, word in words.items():
            memory[address], memory[address + 1] = word & 255, word >> 8
        for index in range(41):
            memory[0x33F0 + index * 2] = 0
            memory[0x33F1 + index * 2] = 0xA8  # VJSR $3000
        return extract_glyphs(memory)[0]

    def test_signed_short_vectors_and_blank_moves(self):
        glyph = self.decode({0x3000: 0x4C00, 0x3002: 0x40C8,
                             0x3004: 0x54D8, 0x3006: 0xC000})
        self.assertEqual(glyph["segments"], [[[0, 24], [16, 24]],
                                              [[16, 24], [0, 0]]])

    def test_call_return_jump_and_signed_long_vectors(self):
        glyph = self.decode({0x3000: 0xA808, 0x3002: 0xE80B,
                             0x3010: 0x1FFF, 0x3012: 0x7FFE,
                             0x3014: 0xC000, 0x3016: 0xC000})
        self.assertEqual(glyph["segments"], [[[0, 0], [-2, -1]]])

    def test_invalid_and_looping_programs_fail(self):
        for word in (0x2000, 0xE800):
            with self.assertRaises(ValueError):
                self.decode({0x3000: word})

    def test_original_alphabet_and_runtime_coverage(self):
        font = json.loads((PROJECT / "content/reference/battlezone/glyphs.json").read_text())
        self.assertEqual(len(font["glyphs"]), 41)
        glyphs = {g["character"]: g for g in font["glyphs"]}
        self.assertEqual(glyphs["A"]["segments"], [
            [[0, 0], [0, 16]], [[0, 16], [8, 24]], [[8, 24], [16, 16]],
            [[16, 16], [16, 0]], [[0, 8], [16, 8]]])
        self.assertEqual(glyphs["O"]["segments"], glyphs["0"]["segments"])
        self.assertEqual(glyphs["S"]["segments"], glyphs["5"]["segments"])
        self.assertTrue(all(g["advance"] == [24, 0] for g in font["glyphs"]))
        game = json.loads((PROJECT / "content/game/battlezone.json").read_text())
        for char in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-":
            self.assertIn("glyph_" + char, game["geometry"])
        self.assertEqual(len(game["geometry"]["tank"]["edges"]), 38)
        self.assertEqual(len(game["geometry"]["radar"]["edges"]), 10)
        for i in range(8):
            self.assertEqual(len(game["geometry"][f"tread{i}"]["edges"]), 3)


if __name__ == "__main__":
    unittest.main()

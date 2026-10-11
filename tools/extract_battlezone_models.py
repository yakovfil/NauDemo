"""Extract Battlezone rev-2 wire models from the annotated disassembly."""

import argparse
import hashlib
from html.parser import HTMLParser
from html import escape
import json
from pathlib import Path
import re
import struct
from urllib.request import urlopen


SOURCE = "https://6502disassembly.com/va-battlezone/Battlezone.html"
NAMES = [
    "narrow_pyramid", "tall_box", "slow_tank", "projectile",
    "rear_tread_0", "rear_tread_1", "rear_tread_2", "rear_tread_3",
    "front_tread_0", "front_tread_1", "front_tread_2", "front_tread_3",
    "wide_pyramid", "radar_dish", "projectile_explosion", "short_box",
    "tank_chunk_0", "tank_chunk_1", "tank_chunk_2", "tank_radar_chunk",
    "tank_chunk_1_alias", "tank_chunk_0_alias", "missile", "logo_ba",
    "missile_chunk_1", "missile_chunk_4", "missile_chunk_0",
    "missile_chunk_5", "missile_chunk_0_alias", "missile_chunk_4_alias",
    "logo_ttle", "logo_zone", "saucer", "super_tank", None, None,
    "spatter_0", "spatter_1", "spatter_2", "spatter_3",
    "spatter_4", "spatter_5", "spatter_6", "spatter_7",
]


class ListingText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def read_memory(html):
    parser = ListingText()
    parser.feed(html.decode("utf-8"))
    lines = "".join(parser.parts).splitlines()
    memory = {}
    cursor = None
    for line in lines:
        row = re.match(r"^([0-9a-f]{4}): ((?:[0-9a-f]{2} ?)+)\+?\s+", line)
        if row:
            cursor = int(row[1], 16)
            bulk = re.search(r"\.bulk\s+([^;]+)", line)
            values = (re.findall(r"\$([0-9a-f]{2})", bulk[1]) if bulk
                      else row[2].split())
        elif cursor is not None and re.match(r"^\s+\+\s+\$", line):
            values = re.findall(r"\$([0-9a-f]{2})", line.split(";")[0])
        else:
            cursor = None
            continue
        for value in values:
            byte = int(value, 16)
            if cursor in memory and memory[cursor] != byte:
                raise ValueError(f"Conflicting listing bytes at {cursor:04x}")
            memory[cursor] = byte
            cursor += 1
    return memory


def extract(memory):
    def word(address):
        return memory[address] | memory[address + 1] << 8

    models = []
    for index, name in enumerate(NAMES):
        vertex_address = word(0x388E + index * 2)
        command_address = word(0x7472 + index * 2)
        model = dict(index=index, hex_index=f"{index:02x}", name=name,
                     vertex_address=f"0x{vertex_address:04x}",
                     command_address=f"0x{command_address:04x}")
        if name is None:
            assert vertex_address == command_address == 0
            model["empty"] = True
            models.append(model)
            continue
        length = memory[vertex_address]
        assert (length - 1) % 6 == 0 and 0 < (length - 1) // 6 <= 26
        data = bytes(memory[a] for a in range(vertex_address + 1,
                                             vertex_address + length))
        raw = list(struct.iter_unpack("<hhh", data))
        # ROM order: depth, horizontal, vertical. Correct horizontal mirror
        # and math-box horizontal/depth factor, then use OBJ right-handed axes.
        vertices = [[-horizontal / 2, vertical, -depth / 2]
                    for depth, horizontal, vertical in raw]
        edges, points, commands, special = [], [], [], []
        current = None
        for offset in range(256):
            byte = memory[command_address + offset]
            commands.append(byte)
            if byte == 0xFF:
                break
            op, vertex = byte & 7, byte >> 3
            if op in (0, 2, 3, 4):
                assert vertex < len(vertices), (index, offset, vertex)
            if op in (2, 3):
                current = vertex
            elif op == 4:
                assert current is not None
                edges.append([current, vertex])
                current = vertex
            elif op == 0:
                points.append(vertex)
                current = vertex
            elif op == 5:
                special.append(dict(command=5, anchor=current,
                                    avg_address="0x347a"))
            elif op not in (1, 6):
                raise ValueError(f"Unsupported command {op}")
        else:
            raise ValueError("Unterminated draw list")
        model.update(raw_vertices=raw, vertices=vertices, edges=edges,
                     points=points, commands=commands, special_draws=special)
        models.append(model)
    return models


def obj_text(model):
    lines = ["# Battlezone (1980), Atari; extracted from rev-2 disassembly",
             f"# Source: {SOURCE}",
             "# Right-handed: +X right, +Y up, -Z forward; original units",
             f"# ROM object 0x{model['hex_index']}; vertex {model['vertex_address']}; draw {model['command_address']}",
             f"o {model['hex_index']}_{model['name']}"]
    lines += ["v " + " ".join(f"{v:g}" for v in vertex)
              for vertex in model["vertices"]]
    lines += [f"l {a + 1} {b + 1}" for a, b in model["edges"]]
    lines += [f"p {index + 1}" for index in model["points"]]
    if model["special_draws"]:
        lines.append("# Explosion anchor only; screen-space AVG effect is not a 3D mesh")
        lines += [f"p {draw['anchor'] + 1}" for draw in model["special_draws"]]
    return "\n".join(lines) + "\n"


def extract_glyphs(memory):
    """Execute the original AVG glyph subroutines, including shared tails."""
    def word(address):
        return memory[address] | memory[address + 1] << 8

    def signed(value, bits):
        value &= (1 << bits) - 1
        return value - (1 << bits) if value & (1 << (bits - 1)) else value

    glyphs = []
    for index, char in enumerate(" 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ -\u00a9\u2117"):
        call = word(0x33F0 + index * 2)
        assert call >> 13 == 5
        pc = 0x2000 + (call & 0xFFF) * 2
        address = pc
        x = y = 0
        stack, segments, instructions = [], [], []
        for _ in range(256):
            instruction = word(pc)
            instructions.append(dict(address=f"0x{pc:04x}", word=instruction))
            pc += 2
            op = instruction >> 13
            if op == 6:
                if not stack:
                    break
                pc = stack.pop()
                continue
            if op in (5, 7):
                if op == 5:
                    stack.append(pc)
                    assert len(stack) <= 8
                pc = 0x2000 + (instruction & 0xFFF) * 2
                continue
            if op == 2:
                dx = signed(instruction, 5) * 2
                dy = signed(instruction >> 8, 5) * 2
                intensity = (instruction >> 4) & 14
            elif op == 0:
                second = word(pc)
                instructions.append(dict(address=f"0x{pc:04x}", word=second))
                pc += 2
                dx, dy = signed(second, 13), signed(instruction, 13)
                intensity = second >> 12 & 14
            else:
                raise ValueError(f"Unexpected glyph opcode {op} at {pc - 2:04x}")
            if intensity:
                segments.append([[x, y], [x + dx, y + dy]])
            x, y = x + dx, y + dy
        else:
            raise ValueError("Unterminated glyph")
        glyphs.append(dict(index=index, character=char, address=f"0x{address:04x}",
                           segments=segments, advance=[x, y], instructions=instructions))
    return glyphs


def update_game(models, glyphs, path):
    """Replace runtime art while retaining the game's obstacle layout."""
    game = json.loads(path.read_text(encoding="utf-8"))
    shapes = {}
    # One uniform model scale; ground is ROM Y=-320. Radar is positioned by
    # runtime at the body's original rear mount, OBJ Z=+256.
    selections = {"tank": 2, "box": 1, "pyramid": 0, "projectile": 3,
                  "radar": 13, "chunk0": 16, "chunk1": 17, "chunk2": 18}
    selections.update({f"tread{i}": 4 + i for i in range(8)})
    for name, index in selections.items():
        model = models[index]
        ground = 320 if name in ("tank", "box", "pyramid", "radar") or name.startswith("tread") else 0
        shapes[name] = dict(vertices=[[x / 200, (y + ground) / 200, z / 200]
                                      for x, y, z in model["vertices"]],
                            edges=model["edges"])
    for glyph in glyphs:
        char = glyph["character"]
        if char not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-":
            continue
        vertices, edges = [], []
        for a, b in glyph["segments"]:
            edges.append([len(vertices), len(vertices) + 1])
            vertices.extend([[p[0] / 16, (24 - p[1]) / 16, 0] for p in (a, b)])
        shapes["glyph_" + char] = dict(vertices=vertices, edges=edges)
    game["geometry"] = shapes
    path.write_text(json.dumps(game, indent=2) + "\n", encoding="utf-8")


def font_preview(glyphs):
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="480" viewBox="0 0 800 480">',
           '<rect width="800" height="480" fill="black"/>']
    for i, glyph in enumerate(glyphs):
        x, y = (i % 10) * 80 + 20, (i // 10) * 96 + 14
        svg.append(f'<g stroke="#00ff50" stroke-width="1.5" fill="none" transform="translate({x},{y}) scale(2)">')
        for a, b in glyph["segments"]:
            svg.append(f'<path d="M {a[0]} {24-a[1]} L {b[0]} {24-b[1]}"/>')
        svg.append('</g>')
        label = f'{i:02x} {glyph["character"] if glyph["character"] != " " else "space"}'
        svg.append(f'<text x="{x-10}" y="{y+68}" fill="#aaaaaa" font-size="12">{escape(label)}</text>')
    return '\n'.join(svg + ['</svg>']) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-html", type=Path,
                        help="Use a saved listing instead of downloading")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] /
                        "content/reference/battlezone")
    parser.add_argument("--game-content", type=Path,
                        help="Replace geometry in this runtime game JSON; preserve layout")
    args = parser.parse_args()
    html = args.source_html.read_bytes() if args.source_html else urlopen(SOURCE).read()
    memory = read_memory(html)
    models = extract(memory)
    glyphs = extract_glyphs(memory)
    args.output.mkdir(parents=True, exist_ok=True)
    for model in models:
        if model.get("empty"):
            continue
        model["file"] = f"{model['hex_index']}_{model['name']}.obj"
        (args.output / model["file"]).write_text(obj_text(model), encoding="utf-8")
    manifest = dict(source=SOURCE, source_sha256=hashlib.sha256(html).hexdigest(),
                    coordinates="OBJ right-handed, X right, Y up, -Z forward",
                    transform="(raw0,raw1,raw2) -> (-raw1/2,raw2,-raw0/2)",
                    index_base=0, objects=models)
    (args.output / "models.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (args.output / "glyphs.json").write_text(json.dumps(dict(
        source=SOURCE, source_sha256=manifest["source_sha256"],
        cell=[16, 24], coordinates="X right, Y up, origin bottom-left",
        glyphs=glyphs), indent=2) + "\n", encoding="utf-8")
    (args.output / "glyphs.svg").write_text(font_preview(glyphs), encoding="utf-8")
    if args.game_content:
        update_game(models, glyphs, args.game_content)
    print(f"Exported {sum(not m.get('empty', False) for m in models)} OBJ objects to {args.output}")


if __name__ == "__main__":
    main()

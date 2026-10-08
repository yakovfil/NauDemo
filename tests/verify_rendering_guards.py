"""Prove independent rendering acceptance rejects false-positive evidence."""
import copy
import json
import pathlib
import tempfile
from PIL import Image
from rendering_evidence import verify_records, verify_image

project = pathlib.Path(__file__).resolve().parents[1]
build = project / "build/basic-rendering-scene"
archive = (build / "windows-debug/selected-input/content.nau_pack").read_bytes()
records = [json.loads(line.removeprefix("RENDER_PROBE ")) for line in (build / "native-observer-debug/normal.log").read_text().splitlines() if line.startswith("RENDER_PROBE ")][-1]
verify_records(records, archive)
results = []
for name in ("wrong-transform", "substituted-geometry", "missing-instance"):
    changed = copy.deepcopy(records)
    if name == "wrong-transform":
        changed["initial"]["draws"][0]["model"][12] += 5
    elif name == "substituted-geometry":
        changed["initial"]["draws"][0]["geometryHash"] = "0"
    else:
        changed["initial"]["draws"].pop()
    try:
        verify_records(changed, archive)
    except AssertionError:
        results.append(dict(case=name, rejected=True))
    else:
        raise AssertionError("Acceptance allowed " + name)
with tempfile.TemporaryDirectory() as temporary:
    image = pathlib.Path(temporary) / "blank.png"
    Image.new("RGB", (900, 600), (0, 0, 0)).save(image)
    try:
        verify_image(image)
    except AssertionError:
        results.append(dict(case="blank-output", rejected=True))
    else:
        raise AssertionError("Acceptance allowed blank output")
(build / "acceptance-guards.json").write_text(json.dumps(results, indent=2))
print("PASS", len(results), "acceptance guards")

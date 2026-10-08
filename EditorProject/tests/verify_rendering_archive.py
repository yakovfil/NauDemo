"""Validate explicit prepared rendering input without native cooking tools."""
import copy
import json
import pathlib
import subprocess
import sys
import tempfile
from rendering_cases import mutate
from verify_web_startup import unpack, pack


project = pathlib.Path(__file__).resolve().parents[1]
checkout = project.parents[1]
validator = checkout / "NauEngineModules/tools/asset_tools/packaged_project.py"
declaration = project / "portable_rendering_project.json"
archive = (project / "build/basic-rendering-scene/windows-debug/selected-input/content.nau_pack").read_bytes()
results = []
with tempfile.TemporaryDirectory(prefix="nau-rendering-archive-") as temporary:
    source = pathlib.Path(temporary) / "content.nau_pack"
    for name in ("valid", "missing-material", "corrupt-material", "missing-geometry", "corrupt-geometry", "unsupported-topology", "invalid-indices", "profile-mismatch", "settings-mismatch"):
        data = archive
        if name in ("profile-mismatch", "settings-mismatch"):
            files = unpack(archive)
            path = "config/assets.json" if name == "profile-mismatch" else "config/rendering.json"
            value = json.loads(files[path])
            if name == "profile-mismatch":
                value["profile"] = "non-rendering-scene"
            else:
                value["lighting"]["ambient"] = [.4, .4, .4]
            files[path] = json.dumps(value).encode()
            data = pack(files)
        elif name != "valid":
            data = mutate(archive, name)
        source.write_bytes(data)
        result = subprocess.run([sys.executable, str(validator), "--declaration", str(declaration), "--archive", str(source)], capture_output=True, text=True)
        assert (result.returncode == 0) == (name == "valid"), (name, result.stdout, result.stderr)
        assert "Traceback" not in result.stderr, result.stderr
        results.append(dict(case=name, exitCode=result.returncode, diagnostic=result.stderr.strip()))
destination = project / "build/basic-rendering-scene/archive-validation.json"
destination.write_text(json.dumps(results, indent=2))
print("PASS", len(results), "prepared archive cases")

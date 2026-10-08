"""Fresh-cook copied authored inputs and verify failure-safe publication."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from verify_web_startup import unpack


def verify(args):
    project = pathlib.Path(__file__).resolve().parents[1]
    checkout = project.parent
    tool = checkout / "NauEngineModules/tools/asset_tools/prepare_packaged_project.py"
    output = project / "build/basic-rendering-scene/freshness"
    output.mkdir(exist_ok=True)
    environment = os.environ.copy()
    python = pathlib.Path(args.python).resolve()
    tools, usd = pathlib.Path(args.tools).resolve(), pathlib.Path(args.usd).resolve()
    environment["PATH"] = os.pathsep.join([str(tools), str(tools / "plugins"), str(python.parent), str(usd / "bin"), str(usd / "lib"), environment["PATH"]])
    environment["PYTHONPATH"] = str(usd / "lib/python")
    environment["PXR_PLUGINPATH_NAME"] = os.pathsep.join([str(tools / "plugins"), str(usd / "plugin/usd")])
    results = []
    with tempfile.TemporaryDirectory(prefix="nau-rendering-freshness-") as temporary:
        source = pathlib.Path(temporary) / "project"
        source.mkdir()
        for directory in ("content", "config"):
            shutil.copytree(project / directory, source / directory)
        shutil.copy2(project / "portable_rendering_project.json", source)
        declaration = source / "portable_rendering_project.json"
        destination = source / "build/prepared"
        command = [str(python), str(tool), "--project", str(source), "--output", str(destination), "--asset-tool", str(tools / "AssetToolCmd.exe"), "--pack-tool", str(tools / "AssetPackToolCmd.exe"), "--module", str(pathlib.Path(args.module).resolve()), "--declaration", str(declaration)]
        def prepare(name, success=True):
            authored = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file() and not path.is_relative_to(source / "build")}
            completed = subprocess.run(command, env=environment, capture_output=True, text=True)
            (output / (name + ".log")).write_text(completed.stdout + completed.stderr)
            assert (completed.returncode == 0) == success, completed.stdout + completed.stderr
            after = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file() and not path.is_relative_to(source / "build")}
            assert authored == after, "Preparation changed authored inputs"
            results.append(dict(case=name, exitCode=completed.returncode, authoredUnchanged=True))
            return (destination / "content.nau_pack").read_bytes()
        initial = prepare("initial")
        material = source / "content/materials/portable_blue.json"
        value = json.loads(material.read_text())
        value["baseColor"][0] = .1
        material.write_text(json.dumps(value))
        changed_material = prepare("material-edit")
        assert unpack(changed_material)["materials/portable_blue.json"] != unpack(initial)["materials/portable_blue.json"]
        geometry = source / "content/meshes/portable_cube.usda"
        geometry.write_text(geometry.read_text().replace("(-1,-1,-1)", "(-1.1,-1,-1)", 1))
        changed_geometry = prepare("geometry-edit")
        before, after = unpack(changed_material), unpack(changed_geometry)
        assert any(after[path] != data for path, data in before.items() if path.endswith(".bin")), "Changed geometry was not recooked"
        policy = json.loads(declaration.read_text())
        policy["rendering"]["lighting"]["ambient"] = [.3, .3, .3]
        declaration.write_text(json.dumps(policy))
        changed_policy = prepare("declaration-edit")
        assert json.loads(unpack(changed_policy)["config/rendering.json"])["lighting"]["ambient"] == [.3, .3, .3]
        value["version"] = 99
        material.write_text(json.dumps(value))
        failed = prepare("failed-material", False)
        assert failed == changed_policy, "Failed preparation overwrote the accepted archive"
    (output / "results.json").write_text(json.dumps(results, indent=2))
    print("PASS", len(results), "freshness cases")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("python", "tools", "usd", "module"):
        parser.add_argument("--" + name, required=True)
    verify(parser.parse_args())

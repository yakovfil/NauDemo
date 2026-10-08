"""Verify native cooking invalidation and failure handling in a scratch project."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile


def run(args):
    project = pathlib.Path(__file__).resolve().parents[1]
    modules = project.parent / "NauEngineModules"
    native_python = args.python.resolve()
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join([str(args.tools.resolve()), str(args.tools.resolve() / "plugins"), str(native_python.parent), str(args.usd_sdk.resolve() / "bin"), str(args.usd_sdk.resolve() / "lib"), environment["PATH"]])
    environment["PYTHONPATH"] = str(args.usd_sdk.resolve() / "lib/python")
    environment["PXR_PLUGINPATH_NAME"] = os.pathsep.join([str(args.tools.resolve() / "plugins"), str(args.usd_sdk.resolve() / "plugin/usd")])
    build = (project / "build").resolve()
    evidence = []
    with tempfile.TemporaryDirectory(prefix="preparation-check-", dir=build) as temporary:
        root = pathlib.Path(temporary).resolve()
        assert root.is_relative_to(build)
        clone = root / "project"
        shutil.copytree(project / "content", clone / "content")
        shutil.copytree(project / "config", clone / "config")
        shutil.copy2(project / "portable_project.json", clone / "portable_project.json")
        output = clone / "build/prepared"
        command = [str(native_python), str(modules / "tools/asset_tools/prepare_browser_project.py"),
                   "--project", str(clone), "--output", str(output),
                   "--asset-tool", str(args.tools.resolve() / "AssetToolCmd.exe"),
                   "--pack-tool", str(args.tools.resolve() / "AssetPackToolCmd.exe"),
                   "--module", str(args.module.resolve()), "--scene", "scenes/web_startup_fixture.nausd_scene"]
        command += ["--declaration", str(clone / "portable_project.json")]

        def prepare(name, success=True, diagnostic=None, invocation=command):
            result = subprocess.run(invocation, env=environment, capture_output=True, text=True, timeout=90)
            (build / ("preparation-" + name + ".log")).write_text(result.stdout + result.stderr)
            assert (result.returncode == 0) == success, (name, result.stdout[-1500:] + result.stderr[-1500:])
            if diagnostic:
                assert diagnostic in result.stdout + result.stderr
            evidence.append(dict(name=name, exitCode=result.returncode, passed=True))
            print("PASS preparation:", name, flush=True)

        archive = output / "content.nau_pack"
        digest = lambda: hashlib.sha256(archive.read_bytes()).hexdigest()
        prepare("clean")
        first = digest()
        declaration_file = clone / "portable_project.json"
        policy = json.loads(declaration_file.read_text())
        original_policy = declaration_file.read_text()
        policy["supportedComponents"].remove("MyMover")
        declaration_file.write_text(json.dumps(policy))
        prepare("changed-component-policy", success=False, diagnostic="MyMover")
        assert digest() == first
        declaration_file.write_text(original_policy)
        scene = clone / "content/scenes/main.nausd_scene"
        scene.write_text(scene.read_text().replace("(0, 0, -15, 1)", "(0, 0, -11, 1)"))
        fixture = clone / "content/scenes/web_startup_fixture.nausd_scene"
        fixture.write_text(fixture.read_text().replace("float amplitude = 0.25", "float amplitude = 0.45"))
        prepare("changed-authored-values")
        assert digest() != first
        current = digest()
        metadata_file = clone / "content/scenes/main.nausd_scene.nausd"
        metadata_file.write_text(metadata_file.read_text().replace("b17469ee-c1c1-11f1-9548-d85ed3acac60", "99999999-2222-3333-4444-555555555555"))
        prepare("changed-metadata")
        assert digest() != current
        current = digest()

        # A native project-header change rebuilds its registration DLL and the
        # new reflected field appears in the next freshly cooked scene.
        shutil.copy2(project / "CMakeLists.txt", clone / "CMakeLists.txt")
        shutil.copytree(project / "cmake", clone / "cmake")
        shutil.copytree(project / "source", clone / "source")
        host = clone / "build/host-components"
        configure = subprocess.run(["cmake", "-S", str(clone), "-B", str(host), "-G", "Visual Studio 18 2026", "-A", "x64", "-DNauEngineFolder=" + str(args.sdk.resolve()), "-DNAU_WEB_HOST_COMPONENTS=ON", "-DBUILD_SHARED_LIBS=ON"], capture_output=True, text=True)
        assert configure.returncode == 0, configure.stdout + configure.stderr
        header = clone / "source/game/main_module/mover.h"
        header.write_text(header.read_text().replace('CLASS_NAMED_FIELD(m_axis, "axis"),', 'CLASS_NAMED_FIELD(m_axis, "axis"),\n        CLASS_NAMED_FIELD(m_startupFlag, "startupFlag"),').replace('AxisM m_axis = AxisM::Y;', 'bool m_startupFlag = true;\n    AxisM m_axis = AxisM::Y;'))
        compiled = subprocess.run(["cmake", "--build", str(host), "--config", "Release", "--target", "MainGameModule", "--parallel", "8"], capture_output=True, text=True, timeout=120)
        assert compiled.returncode == 0, compiled.stdout[-2000:] + compiled.stderr[-2000:]
        changed_command = list(command)
        changed_command[changed_command.index("--module") + 1] = str(host / "bin/Release/MainGameModule.dll")
        prepare("changed-component-definition", invocation=changed_command)
        metadata = json.loads((output / "preparation.json").read_text())
        work = pathlib.Path(metadata["work"])
        raw = (work / "assets_database/0/11111111-2222-3333-4444-555555555554.nscene").read_text()
        assert '"startupFlag" : true' in raw or '"startupFlag":true' in raw
        assert digest() != current
        current = digest()

        source = clone / "content/meshes/cube.usda"
        held = source.read_bytes()
        source.unlink()
        prepare("missing-reference", False, "cube.usda")
        assert digest() == current
        source.write_bytes(held)
        held = fixture.read_bytes()
        fixture.write_text("invalid USD scene")
        prepare("failed-conversion", False)
        assert digest() == current
        fixture.write_bytes(held)
        archive.chmod(stat.S_IREAD)
        try:
            prepare("failed-publication", False, "content.nau_pack")
            assert digest() == current
        finally:
            archive.chmod(stat.S_IREAD | stat.S_IWRITE)
    (build / "preparation-checks.json").write_text(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=pathlib.Path, required=True)
    parser.add_argument("--tools", type=pathlib.Path, required=True)
    parser.add_argument("--module", type=pathlib.Path, required=True)
    parser.add_argument("--sdk", type=pathlib.Path, required=True)
    parser.add_argument("--usd-sdk", type=pathlib.Path, required=True)
    run(parser.parse_args())

"""Exercise relocated production and observed portable Windows deliveries."""
import argparse
import copy
import ctypes
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading

from verify_web_startup import pack, read_scene, unpack, verify_scene, write_scene


def close_windows(pid):
    user = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _):
        owner = ctypes.c_ulong()
        user.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(owner))
        if owner.value == pid:
            user.PostMessageW(ctypes.c_void_p(hwnd), 0x10, 0, 0)
        return True
    user.EnumWindows(callback_type(callback), 0)


def run(configuration):
    project = pathlib.Path(__file__).resolve().parents[1]
    build = project / "build" / ("windows-" + configuration.lower())
    archive = (build / "selected-input/content.nau_pack").read_bytes()
    original = unpack(archive)
    results = []
    with tempfile.TemporaryDirectory(prefix="nau-native-delivery-") as temporary:
        root = pathlib.Path(temporary)
        for name in ("package", "probe-package"):
            shutil.copytree(build / name, root / name)
        environment = os.environ.copy()
        system_root = os.environ["SystemRoot"]
        environment["PATH"] = os.pathsep.join([system_root, str(pathlib.Path(system_root) / "System32")])
        def check(name, data=archive, config="/config/scene.json", expected=None, probe=False, stop=None):
            directory = root / ("probe-package" if probe else "package")
            (directory / "content.nau_pack").write_bytes(data)
            executable = directory / ("NauDemoStartupProbe.exe" if probe else "NauDemoMain.exe")
            arguments = [str(executable)]
            if probe:
                arguments += [str(directory / "content.nau_pack"), config]
                if stop:
                    arguments.append("stop:" + stop)
            else:
                arguments.append(config)
            process = subprocess.Popen(arguments, cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            lines = []
            ready = threading.Event()
            def reader():
                for line in process.stdout:
                    lines.append(line)
                    if "Packaged scene Running" in line:
                        ready.set()
            thread = threading.Thread(target=reader, daemon=True)
            thread.start()
            try:
                if not probe and not expected:
                    assert ready.wait(20), "".join(lines)
                    close_windows(process.pid)
                    close_windows(process.pid)
                code = process.wait(timeout=30)
                thread.join(timeout=3)
                text = "".join(lines)
                (project / "build" / ("native-" + configuration.lower() + "-" + name + ".log")).write_text(text)
                if expected:
                    assert code != 0 and expected in text, text
                    assert "Packaged scene Running" not in text, text
                else:
                    assert code == 0, text
                if probe:
                    assert "PROBE_CLEANUP true" in text, text
                if stop:
                    assert "PROBE_STOP " + stop in text and "PROBE_SCENE" not in text, text
                    assert "MainGameModule updateComponent" not in text, text
                    if stop == "activation":
                        assert "PROBE_ACTIVATION_SETTLED" in text, text
                elif probe and not expected:
                    observed = {}
                    for line in lines:
                        if line.startswith("PROBE_SCENE "):
                            value = json.loads(line[len("PROBE_SCENE "):])
                            observed[value["phase"]] = value
                    verify_scene(observed, original, "fixture" in config)
                    if "fixture" in config:
                        assert text.count("MainGameModule updateComponent") >= 20, text
                assert "Nau failure:" not in text, text
                results.append(dict(name=name, exitCode=code))
                print(f"PASS Windows {configuration}: {name}", flush=True)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

        check("actual-project")
        check("main-scene-state", probe=True)
        config = "/config/web_startup_fixture.json"
        check("authored-component-state", config=config, probe=True)
        main = next(name for name in original if name.endswith("b17469ee-c1c1-11f1-9548-d85ed3acac60.nscene"))
        for name, path in (("missing-config", "config/scene.json"), ("missing-scene", main), ("missing-mesh", next(name for name in original if name.endswith(".gltf"))), ("missing-buffer", next(name for name in original if name.endswith(".bin")))):
            changed = dict(original)
            del changed[path]
            check(name, pack(changed), expected=path)
        for name, path in (("corrupt-config", "config/scene.json"), ("corrupt-database", "assets_db/database.db"), ("corrupt-scene", main)):
            changed = dict(original)
            changed[path] = b"broken"
            check(name, pack(changed), expected="scene" if path == main else path)
        check("missing-archive", b"", expected="package")
        check("corrupt-archive", archive[:100], expected="package")
        for name, component, diagnostic in (("unknown-component", "UnknownProjectComponent", "UnknownProjectComponent"), ("excluded-component", "nau::SkinnedMeshComponent", "excluded service")):
            changed = dict(original)
            header, objects = read_scene(changed[main])
            objects[0]["rootComponent"]["componentTypeName"] = component
            changed[main] = write_scene(header, objects)
            check(name, pack(changed), expected=diagnostic)
        check("stop-before-mount", probe=True, stop="before-mount")
        fixture = next(name for name in original if name.endswith("555555555554.nscene"))
        header, objects = read_scene(original[fixture])
        gate = dict(componentTypeId=0, componentTypeName="StartupGateComponent", uid="11111111-2222-3333-4444-555555555559", properties={"uid": "11111111-2222-3333-4444-555555555559"})
        objects[0]["additionalComponents"].append(gate)
        objects[0]["additionalComponentCount"] += 1
        changed = dict(original)
        changed[fixture] = write_scene(header, objects)
        check("stop-activation", pack(changed), config=config, probe=True, stop="activation")
        for property_name, diagnostic in (("failActivation", "deferred activation failure"), ("immediateFailure", "immediate activation failure")):
            gate["properties"][property_name] = True
            changed[fixture] = write_scene(header, objects)
            check(property_name, pack(changed), config=config, expected=diagnostic, probe=True)
            del gate["properties"][property_name]
    (project / "build" / ("native-acceptance-" + configuration.lower() + ".json")).write_text(json.dumps(dict(configuration=configuration, archiveSha256=hashlib.sha256(archive).hexdigest(), results=results), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), required=True)
    run(parser.parse_args().configuration)

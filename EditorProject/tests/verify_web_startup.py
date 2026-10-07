"""Verify real browser scene state, package failures, relocation and Stop."""
import argparse
import copy
import functools
import http.server
import json
import math
import pathlib
import re
import shutil
import tempfile
import threading
import uuid
from playwright.sync_api import sync_playwright


def container(data):
    offset = data.index(b"\n\n") + 3
    length = int(next(line.split(b":", 1)[1] for line in data[:offset].splitlines() if line.startswith(b"Content-Length:")))
    return json.loads(data[offset:offset + length]), data[offset + length:]


def envelope(kind, header, payload):
    raw = json.dumps(header, separators=(",", ":")).encode()
    return f"NauContent-Kind: {kind}\nContent-Type: application/json\nContent-Length: {len(raw)}\n\n\n".encode() + raw + payload


def unpack(data):
    header, payload = container(data)
    return {entry["filePath"]: payload[entry["blobData"]["offset"]:entry["blobData"]["offset"] + entry["blobData"]["size"]] for entry in header["content"]}


def pack(files):
    entries, chunks, offset = [], [], 0
    for path, data in sorted(files.items()):
        entries.append(dict(filePath=path, blobData=dict(offset=offset, size=len(data)), clientSize=len(data), contentCompression=""))
        chunks.append(data)
        offset += len(data)
    return envelope("nau-vfs-pack", dict(version="0.1", description="Acceptance case", content=entries), b"".join(chunks))


def read_scene(data):
    header, payload = container(data)
    return header, [obj for block in header["objects"] for obj in json.loads(payload[block["offset"]:block["offset"] + block["size"]])]


def write_scene(header, objects, block_size=20):
    header = copy.deepcopy(header)
    blocks, payload, offset = [], [], 0
    for start in range(0, len(objects), block_size):
        raw = json.dumps(objects[start:start + block_size], separators=(",", ":")).encode()
        blocks.append(dict(offset=offset, size=len(raw)))
        payload.append(raw)
        offset += len(raw)
    header["objects"] = blocks
    return envelope("nau-scene", header, b"".join(payload))


def close_values(actual, expected):
    if isinstance(expected, list):
        assert len(actual) == len(expected), (actual, expected)
        for left, right in zip(actual, expected):
            close_values(left, right)
    elif isinstance(expected, float):
        assert math.isclose(actual, expected, abs_tol=1e-5, rel_tol=1e-5), (actual, expected)
    else:
        assert actual == expected, (actual, expected)


def verify_scene(observed, files, fixture):
    initial, updated = observed["initial"], observed["updated"]
    assert initial["updates"] == 0 and updated["updates"] == 10
    path = next(path for path in files if path.endswith("555555555554.nscene" if fixture else "b17469ee-c1c1-11f1-9548-d85ed3acac60.nscene"))
    _, cooked = read_scene(files[path])
    loaded = {obj["uid"]: obj for obj in initial["objects"]}
    assert len(loaded) == len(cooked)
    by_local = {obj["localId"]: obj for obj in cooked}
    for obj in cooked:
        actual = loaded[obj["uid"]]
        assert actual["name"] == obj["name"]
        assert actual["parent"] == (by_local[obj["parentLocalId"]]["uid"] if obj["parentLocalId"] else "")
        for key in ("translation", "rotation", "scale"):
            close_values(actual["transform"][key], obj["rootComponent"]["transform"][key])
        components = {component["uid"]: component for component in actual["components"]}
        for component in [obj["rootComponent"]] + obj["additionalComponents"]:
            assert components[component["uid"]]["type"] == component["componentTypeName"]
    # Independent authored expectations detect compiler/runtime agreement on an
    # incorrect value; comparison with the cooked output alone is insufficient.
    named = {obj["name"]: obj for obj in initial["objects"]}
    if fixture:
        parent, child = named["FixtureParent"], named["MovingChild"]
        close_values(parent["transform"]["translation"], [1.0, 2.0, 3.0])
        close_values(parent["transform"]["scale"], [2.0, 3.0, 4.0])
        close_values(child["transform"]["translation"], [4.0, -2.0, 5.0])
        assert child["parent"] == parent["uid"]
        components = {component["type"]: component for obj in initial["objects"] for component in obj["components"]}
        mover, rotator, camera = (components[name] for name in ("MyMover", "MyRotator", "nau::scene::CameraComponent"))
        assert mover["uid"] == "11111111-2222-3333-4444-555555555551"
        for key, value in dict(axis="Z", amplitude=0.25, frequency=1.75, phase=0.2).items():
            close_values(mover["properties"][key], value)
        assert rotator["uid"] == "11111111-2222-3333-4444-555555555552"
        close_values(rotator["properties"]["speedFactor"], 0.65)
        assert rotator["properties"]["axis"] == "X"
        close_values(camera["properties"]["transform"]["translation"], [6.0, 7.0, 8.0])
        close_values(camera["properties"]["FieldOfView"], 75.0)
        after = next(obj for obj in updated["objects"] if obj["uid"] == child["uid"])
        assert after["transform"]["translation"][2] != child["transform"]["translation"][2]
        assert after["transform"]["rotation"] != child["transform"]["rotation"]
        close_values(after["transform"]["translation"][:2], [4.0, -2.0])
    else:
        close_values(named["Xform"]["transform"]["translation"], [0.0, 0.0, -15.0])
        mesh = next(component for component in named["NauAssetMesh"]["components"] if component["type"].endswith("StaticMeshComponent"))
        assert mesh["properties"]["geometry"] == "uid:b17469e3-c1c1-11f1-9548-d85ed3acac60+[mesh/0]"


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, *args):
        pass


def run(args):
    project = pathlib.Path(__file__).resolve().parents[1]
    configuration = args.configuration.lower()
    build = project / "build" / ("web-" + configuration)
    archive = (project / "build" / ("prepared-" + configuration) / "content.nau_pack").read_bytes()
    original = unpack(archive)
    results = []
    with tempfile.TemporaryDirectory(prefix="nau-editor-web-") as temporary:
        root = pathlib.Path(temporary)
        for source, name in ((build / "package", "application"), (build / "probe-package", "probe")):
            target = root / "relocated/nested" / name
            target.mkdir(parents=True)
            for file in source.iterdir():
                if file.is_file() and not file.name.startswith("bootstrap"):
                    shutil.copy2(file, target / file.name)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                browser_version = browser.version

                def check(name, data=archive, configuration_path="/config/scene.json", expected=None, probe=False, stop_phase=None, delay=False):
                    directory = root / "relocated/nested" / ("probe" if probe else "application")
                    application = "NauDemoStartupProbe" if probe else "NauDemoMain"
                    page = browser.new_page()
                    logs = []
                    console_messages = []
                    page.on("console", lambda message: console_messages.append((message.type, message.text)))
                    page.on("console", lambda message: (logs.append(message.text), print(message.text[:2000], flush=True) if message.type == "error" else None))
                    page.on("pageerror", lambda error: (logs.append(str(error)), print(str(error)[:2000], flush=True)))
                    html = (directory / "index.html").read_text()
                    arguments = [configuration_path] + (["delay-startup"] if delay else [])
                    html = html.replace("window.Module = {", "window.Module = {arguments:" + json.dumps(arguments) + ",")
                    loader = (directory / (application + ".js")).read_text()
                    loader, count = re.subn(r'loadPackage\(\s*\{\s*"?files"?\s*:.*?"?remote_package_size"?\s*:\s*\d+\s*\}\s*\)',
                        'loadPackage(' + json.dumps(dict(files=[dict(filename="/project-package/content.nau_pack", start=0, end=len(data))], remote_package_size=len(data))) + ')', loader, count=1, flags=re.S)
                    assert count == 1
                    page.route("**/index.html", lambda route: route.fulfill(body=html, content_type="text/html", headers={"Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp"}))
                    isolation = {"Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp"}
                    page.route("**/" + application + ".js", lambda route: route.fulfill(body=loader, content_type="text/javascript", headers=isolation))
                    page.route("**/" + application + ".data", lambda route: route.fulfill(body=data, content_type="application/octet-stream", headers=isolation))
                    page.add_init_script("window.heartbeats=0;setInterval(()=>++window.heartbeats,10)")
                    page.goto(f"http://127.0.0.1:{server.server_port}/relocated/nested/{'probe' if probe else 'application'}/index.html")
                    if stop_phase:
                        page.wait_for_function("phase => Module.sceneProbePhase === phase", arg=stop_phase, timeout=30000)
                        state = page.evaluate("Module.nauRuntime.status")
                        assert state["state"] == "Starting" and state["completedSteps"] == 0, state
                        assert page.evaluate("heartbeats") > 0
                        page.evaluate("Module.nauRuntime.stop(); Module.nauRuntime.stop()")
                    elif expected:
                        page.wait_for_function("Module.nauRuntime?.status?.cleanupComplete", timeout=30000)
                    else:
                        page.wait_for_function("Module.nauRuntime?.status?.state === 'Running'", timeout=30000)
                        if probe:
                            page.wait_for_function("Module.sceneProbe?.updated", timeout=30000)
                            verify_scene(page.evaluate("Module.sceneProbe"), original, "fixture" in configuration_path)
                        page.evaluate("Module.nauRuntime.stop(); Module.nauRuntime.stop()")
                    page.wait_for_function("Module.nauRuntime.status.cleanupComplete", timeout=30000)
                    status, history = page.evaluate("[Module.nauRuntime.status,Module.nauRuntime.history]")
                    if expected:
                        assert status["state"] == "Failed" and expected in status["message"], status
                        assert not any(item["state"] == "Running" for item in history), history
                    else:
                        assert status["state"] == "Stopped", status
                    if probe:
                        assert page.evaluate("Module.sceneProbeCleanup") is True
                        for level, kind in (("info", "log"), ("warning", "warning"), ("error", "error"), ("critical", "error")):
                            matches = [(category, text) for category, text in console_messages if "PROBE_LOG " + level in text]
                            assert len(matches) == 1 and matches[0][0] == kind, matches
                    lifecycle = [(kind, text) for kind, text in console_messages if text.startswith("[Nau] ")]
                    assert any("Starting" in text for _, text in lifecycle), lifecycle
                    assert any("cleanup complete" in text for _, text in lifecycle), lifecycle
                    if expected:
                        assert any(kind == "error" and expected in text for kind, text in lifecycle), lifecycle
                    elif not stop_phase:
                        assert any("Running" in text for _, text in lifecycle), lifecycle
                    if name == "authored-component-state":
                        component_logs = [(kind, text) for kind, text in console_messages if "MainGameModule updateComponent" in text]
                        assert len(component_logs) >= 20 and all(kind == "warning" for kind, _ in component_logs), component_logs
                        assert len({text for _, text in component_logs}) == len(component_logs), component_logs
                    if stop_phase:
                        assert status["completedSteps"] == 0
                        assert not any(item["state"] == "Running" for item in history), history
                        if stop_phase == "activation":
                            assert page.evaluate("Module.sceneProbeActivationSettled") is True
                    assert not any("Nau failure:" in line or "Aborted(" in line for line in logs), logs
                    results.append(dict(name=name, status=status, history=history))
                    page.close()
                    print(f"PASS {args.configuration}: {name}", flush=True)

                check("actual-project")
                check("main-scene-state", probe=True)
                fixture_config = "/config/web_startup_fixture.json"
                check("authored-component-state", configuration_path=fixture_config, probe=True)
                main_scene = next(path for path in original if path.endswith("b17469ee-c1c1-11f1-9548-d85ed3acac60.nscene"))
                mesh = next(path for path in original if path.endswith(".gltf"))
                buffer = next(path for path in original if path.endswith(".bin"))
                for name, path in (("missing-config", "config/scene.json"), ("missing-scene", main_scene), ("missing-mesh", mesh), ("missing-mesh-buffer", buffer)):
                    changed = dict(original)
                    del changed[path]
                    check(name, pack(changed), expected=path)
                for name, path in (("corrupt-config", "config/scene.json"), ("corrupt-database", "assets_db/database.db"), ("corrupt-scene", main_scene)):
                    changed = dict(original)
                    changed[path] = b"broken"
                    check(name, pack(changed), expected="scene" if path.endswith(".nscene") else path)
                check("missing-archive", b"", expected="package")
                check("corrupt-archive", archive[:100], expected="package")
                for name, type_name, diagnostic in (("unknown-component", "UnknownProjectComponent", "UnknownProjectComponent"), ("excluded-service-component", "nau::SkinnedMeshComponent", "excluded service")):
                    changed = dict(original)
                    header, objects = read_scene(changed[main_scene])
                    objects[0]["rootComponent"]["componentTypeName"] = type_name
                    changed[main_scene] = write_scene(header, objects)
                    check(name, pack(changed), expected=diagnostic)
                changed = dict(original)
                header, objects = read_scene(changed[main_scene])
                next(obj for obj in objects if obj["name"] == "NauAssetMesh")["rootComponent"]["properties"]["geometry"] = "uid:ffffffff-ffff-ffff-ffff-ffffffffffff+[mesh/0]"
                changed[main_scene] = write_scene(header, objects)
                check("unresolved-asset-reference", pack(changed), expected="ffffffff-ffff-ffff-ffff-ffffffffffff")
                changed = dict(original)
                header, payload = container(changed[main_scene])
                header["objects"][0]["offset"] += 2 ** 32
                changed[main_scene] = envelope("nau-scene", header, payload)
                check("overflowed-scene-block", pack(changed), expected="scene")
                changed = dict(original)
                header, objects = read_scene(changed[main_scene])
                objects[0]["childLocalIds"].append(objects[0]["localId"])
                objects[0]["childCount"] += 1
                changed[main_scene] = write_scene(header, objects)
                check("cyclic-scene-hierarchy", pack(changed), expected="scene")
                changed = dict(original)
                header, objects = read_scene(changed[main_scene])
                camera = next(component for obj in objects for component in obj["additionalComponents"] if component["componentTypeName"].endswith("CameraComponent"))
                camera["properties"]["FieldOfView"] = "invalid-number"
                changed[main_scene] = write_scene(header, objects)
                check("invalid-component-property", pack(changed), expected="requires a number")
                check("stop-before-mount", probe=True, stop_phase="before-mount", delay=True)
                changed = dict(original)
                fixture = next(path for path in original if path.endswith("555555555554.nscene"))
                header, objects = read_scene(changed[fixture])
                gate = dict(componentTypeId=0, componentTypeName="StartupGateComponent", uid="11111111-2222-3333-4444-555555555559", properties={"uid": "11111111-2222-3333-4444-555555555559"})
                objects[0]["additionalComponents"].append(gate)
                objects[0]["additionalComponentCount"] += 1
                changed[fixture] = write_scene(header, objects)
                check("stop-pending-activation", pack(changed), fixture_config, probe=True, stop_phase="activation")
                for property_name, diagnostic in (("failActivation", "deferred activation failure"), ("immediateFailure", "immediate activation failure")):
                    gate["properties"][property_name] = True
                    changed[fixture] = write_scene(header, objects)
                    check(property_name, pack(changed), fixture_config, expected=diagnostic, probe=True)
                    del gate["properties"][property_name]
                header, objects = read_scene(original[fixture])
                parent = next(obj for obj in objects if obj["name"] == "FixtureParent")
                model = next(obj for obj in objects if obj["name"] == "MovingChild")
                for index in range(2000):
                    child = copy.deepcopy(model)
                    child.update(localId=100 + index, uid=str(uuid.uuid4()), name=f"Load{index}", childCount=0, childLocalIds=[], additionalComponentCount=1, additionalComponents=[], parentLocalId=parent["localId"])
                    identity = str(uuid.uuid4())
                    child["rootComponent"]["uid"] = child["rootComponent"]["properties"]["uid"] = identity
                    parent["childLocalIds"].append(child["localId"])
                    parent["childCount"] += 1
                    objects.append(child)
                changed[fixture] = write_scene(header, objects, block_size=2)
                check("stop-pending-load", pack(changed), fixture_config, probe=True, stop_phase="load")
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    output = project / "build" / ("acceptance-" + configuration + ".json")
    output.write_text(json.dumps(dict(configuration=args.configuration, browser=browser_version, results=results), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), required=True)
    run(parser.parse_args())

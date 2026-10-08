"""Check relocated scene submission and eligible cleanup with the real DX12 driver."""
import argparse
import ctypes
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
from PIL import Image

from verify_native_startup import close_windows
from rendering_cases import CONTENT_FAILURES, mutate
from rendering_evidence import verify_records, verify_image, verify_projection


def capture_owned_window(pid, path, resize=False):
    windows = json.loads(subprocess.check_output(["orca", "computer", "list-windows", "--app", f"pid:{pid}", "--json"], text=True))["result"]["windows"]
    assert len(windows) == 1, windows
    handle = windows[0]["id"]
    user = ctypes.WinDLL("user32")
    user.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    if resize:
        for width, height in ((420, 680), (1000, 420)):
            assert user.SetWindowPos(handle, ctypes.c_void_p(-1), 100, 100, width, height, 0x40)
            time.sleep(.2)
        user.ShowWindow(handle, 6)
        time.sleep(.2)
        user.ShowWindow(handle, 9)
    assert user.SetWindowPos(handle, ctypes.c_void_p(-1), 100, 100, 900, 600, 0x40)
    time.sleep(.3)
    snapshot = json.loads(subprocess.check_output(["orca", "computer", "get-app-state", "--app", f"pid:{pid}", "--window-id", str(handle), "--json"], text=True))["result"]
    assert snapshot["screenshotStatus"]["state"] == "captured", snapshot
    shutil.copy2(snapshot["screenshot"]["path"], path)
    class Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    class Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    user.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(Rect)]
    user.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(Point)]
    client, origin = Rect(), Point()
    assert user.GetClientRect(handle, ctypes.byref(client))
    assert user.ClientToScreen(handle, ctypes.byref(origin))
    window = snapshot["snapshot"]["window"]
    x, y = origin.x - window["x"], origin.y - window["y"]
    # Inspect only the actual drawable, excluding desktop pixels in the DWM
    # frame and native title-bar controls.
    Image.open(path).crop((x, y, x + client.right, y + client.bottom)).save(path)


def verify(configuration):
    project = pathlib.Path(__file__).resolve().parents[1]
    build = project / "build/basic-rendering-scene" / ("windows-" + configuration.lower())
    output = build.parent / ("native-observer-" + configuration.lower())
    output.mkdir(exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="nau-rendering-delivery-") as temporary:
        delivery = pathlib.Path(temporary) / "delivery"
        shutil.copytree(build / "probe-package", delivery)
        environment = os.environ.copy()
        environment["PATH"] = os.pathsep.join([os.environ["SystemRoot"], str(pathlib.Path(os.environ["SystemRoot"]) / "System32")])
        archive = (delivery / "content.nau_pack").read_bytes()
        for mode in ("normal", "async-motion", "visibility", "removal", "empty", "component-offset", "camera", "activation", "init-error", "upload-error", "submit-error", "context-loss", "stop-upload", "stop-load", "remove-load") + CONTENT_FAILURES:
            data = archive
            if mode in ("stop-load", "remove-load") or mode in CONTENT_FAILURES:
                data = mutate(archive, mode)
            (delivery / "content.nau_pack").write_bytes(data)
            process = subprocess.Popen([str(delivery / "NauSceneRenderingProbe.exe"), mode, "/config/render_scene.json", str(delivery / "content.nau_pack")], cwd=temporary, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            lines = []
            ready = threading.Event()
            def read():
                for line in process.stdout:
                    lines.append(line)
                    if "RENDER_PROBE_READY" in line:
                        ready.set()
            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            failed = mode.endswith("error") or mode == "context-loss" or mode in CONTENT_FAILURES
            try:
                if not failed and mode not in ("stop-load", "stop-upload"):
                    assert ready.wait(30), "Probe readiness timeout"
                    capture_owned_window(process.pid, output / (mode + ".png"), resize=mode == "normal")
                    if mode in ("normal", "empty", "visibility", "component-offset", "camera", "activation"):
                        verify_image(output / (mode + ".png"), empty=mode == "empty")
                    close_windows(process.pid)
                    close_windows(process.pid)
                code = process.wait(timeout=30)
                reader.join(timeout=3)
                text = "".join(lines)
                (output / (mode + ".log")).write_text(text)
                assert (code != 0) == failed, text
                cleanup = [json.loads(line.removeprefix("RENDER_CLEANUP ")) for line in lines if line.startswith("RENDER_CLEANUP ")]
                assert len(cleanup) == 1 and cleanup[0]["cleanup"], text
                assert "live resources" not in text.lower(), text
                if mode == "stop-load":
                    assert cleanup[0]["loadAccepted"] and cleanup[0]["loadSettled"], text
                    assert cleanup[0]["frames"] == 0 and cleanup[0]["updates"] == 0, text
                elif mode == "stop-upload":
                    assert cleanup[0]["updates"] == 0 and cleanup[0]["frames"] == 1, cleanup
                elif failed:
                    assert ("Probe injected" in text) if mode not in CONTENT_FAILURES else ("error:" in text), text
                    assert "Packaged scene Running" not in text or mode == "context-loss", text
                else:
                    records = [json.loads(line.removeprefix("RENDER_PROBE ")) for line in lines if line.startswith("RENDER_PROBE ")][-1]
                    if mode != "remove-load":
                        verify_records(records, archive)
                    else:
                        assert cleanup[0]["loadAccepted"] and cleanup[0]["loadSettled"], cleanup
                        assert all(draw["object"] == "OrangeTetra" for record in records.values() for draw in record["draws"]), records
                    assert all(record["valid"] and record["ownerThread"] for record in records.values()), records
                    assert records["initial"]["updates"] == 0, records
                    draws = records["frozen"]["draws"]
                    count = {"normal": 3, "async-motion": 3, "visibility": 2, "removal": 2, "empty": 0, "component-offset": 4, "camera": 3, "activation": 4, "remove-load": 1}[mode]
                    assert len(draws) == count, records
                    if mode in ("normal", "async-motion"):
                        assert records["updated"]["updates"] == 10, records
                        first = {draw["component"]: draw for draw in records["initial"]["draws"]}
                        assert any(draw["model"] != first[draw["component"]]["model"] for draw in records["updated"]["draws"]), records
                        assert len({draw["geometry"] for draw in draws}) == 2, records
                        projection = verify_projection(output / (mode + ".png"), records["updated"], archive)
                        (output / (mode + "-projection.json")).write_text(json.dumps(projection, indent=2))
                    if mode == "camera":
                        assert records["initial"]["camera"] != records["frozen"]["camera"], records
                results.append(dict(mode=mode, exitCode=code, cleanup=cleanup[0]))
                print("PASS", configuration, mode, flush=True)
            finally:
                if process.poll() is None:
                    close_windows(process.pid)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                (output / (mode + ".log")).write_text("".join(lines))
    (output / "results.json").write_text(json.dumps(dict(archiveHash=hashlib.sha256((build / "probe-package/content.nau_pack").read_bytes()).hexdigest(), cases=results), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configuration", choices=("Debug", "Release"))
    verify(parser.parse_args().configuration)

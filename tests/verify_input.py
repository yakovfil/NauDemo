"""Exercise production CoreInput and the shared camera through native/DOM events."""
import argparse
import ctypes
import functools
import hashlib
import http.server
import json
import math
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
from verify_native_rendering import capture_owned_window
from verify_native_startup import close_windows
from verify_web_startup import Handler


CAMERA = "22222222-3333-4444-5555-666666666683"
MOVEMENTS = (("w", 2, -1), ("s", 2, 1), ("a", 0, -1), ("d", 0, 1), ("q", 1, -1), ("e", 1, 1))


def distance(first, second):
    return math.sqrt(sum((a-b)**2 for a, b in zip(first, second)))


def valid(record):
    assert record["valid"] and record["camera"] == CAMERA, record
    assert all(math.isfinite(value) for field in ("position", "rotation", "viewProjection", "delta") for value in record[field]), record


def unchanged(before, after):
    valid(after)
    assert distance(before["position"], after["position"]) < .002, (before, after)
    assert distance(before["rotation"], after["rotation"]) < .0001, (before, after)
    assert not any(after["held"]) and not after["drag"] and after["delta"] == [0, 0], after


def changed_image(first, second):
    a, b = (Image.open(path).convert("RGB") for path in (first, second))
    assert a.size == b.size
    assert ImageChops.difference(a, b).getbbox(), "Camera input did not change visible output"


def expected_drag(record):
    yaw, pitch = -.2, -.12 # 50/30 client pixels at the shared .004 sensitivity.
    expected = [math.sin(pitch/2)*math.cos(yaw/2), math.sin(yaw/2)*math.cos(pitch/2),
                -math.sin(yaw/2)*math.sin(pitch/2), math.cos(pitch/2)*math.cos(yaw/2)]
    assert distance(record["rotation"], expected) < .003, (record["rotation"], expected)


def web(delivery, root, output):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results, logs = [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for dpr in (1, 2):
                context = browser.new_context(viewport=dict(width=900, height=600), device_scale_factor=dpr)
                page = context.new_page()
                page.on("console", lambda message: logs.append(message.text))
                page.on("pageerror", lambda error: logs.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html")
                page.wait_for_function("Module.inputProbe?.frame > 3 && Module.nauRuntime.status.state === 'Running'", timeout=30000)
                def sample():
                    record = page.evaluate("Module.inputProbe")
                    valid(record)
                    return record
                def advance(count=4):
                    previous = sample()["frame"]
                    page.wait_for_function("frame => Module.inputProbe.frame > frame", arg=previous+count, timeout=10000)
                    return sample()
                initial = sample()
                unchanged(initial, advance())
                page.locator("#canvas").screenshot(path=str(output / f"web-dpr{dpr}-initial.png"))
                page.mouse.click(350, 250)
                assert page.evaluate("document.activeElement.id") == "nau-window"
                movement = []
                for key, axis, direction in MOVEMENTS:
                    before = sample()
                    page.keyboard.down(key)
                    page.wait_for_function("data => Math.abs(Module.inputProbe.position[data.axis] - data.start) > .04",
                                           arg=dict(axis=axis, start=before["position"][axis]), timeout=10000)
                    during = sample()
                    if key == "w":
                        page.locator("#canvas").screenshot(path=str(output / f"web-dpr{dpr}-movement.png"))
                        changed_image(output / f"web-dpr{dpr}-initial.png", output / f"web-dpr{dpr}-movement.png")
                    page.keyboard.up(key)
                    page.wait_for_function("!Module.inputProbe.held.some(Boolean)")
                    released = advance()
                    unchanged(released, advance())
                    assert (during["position"][axis]-before["position"][axis])*direction > .03, (key, before, during)
                    assert before["viewProjection"] != during["viewProjection"]
                    movement.append(dict(key=key, before=before, during=during, released=released))
                before = sample()
                page.mouse.move(350, 250)
                page.mouse.down()
                page.mouse.move(400, 280, steps=5)
                page.wait_for_function("rotation => Module.inputProbe.rotation.some((x,i) => Math.abs(x-rotation[i]) > .01)", arg=before["rotation"])
                rotated = advance()
                expected_drag(rotated)
                assert rotated["drag"]
                page.locator("#canvas").screenshot(path=str(output / f"web-dpr{dpr}-drag.png"))
                page.mouse.up()
                released = advance()
                page.mouse.move(500, 300)
                after = advance()
                assert distance(released["rotation"], after["rotation"]) < .0001
                # A capture must retain events outside the host and end on release.
                page.evaluate("document.querySelector('#nau-window').style.cssText='width:600px;height:400px;position:relative'")
                page.mouse.move(300, 200)
                page.mouse.down()
                page.mouse.move(650, 450, steps=4)
                assert page.evaluate("document.querySelector('#nau-window').hasPointerCapture(1)")
                page.mouse.up()
                page.wait_for_function("!Module.inputProbe.drag")
                stable = advance()
                page.mouse.move(700, 500)
                unchanged(stable, advance())
                page.mouse.move(300, 200)
                page.mouse.down(button="middle")
                page.wait_for_function("Module.inputProbe.buttons[1]")
                page.mouse.move(650, 450)
                page.mouse.up(button="middle")
                page.wait_for_function("!Module.inputProbe.buttons.some(Boolean)")
                # Losing focus while a key is held must clear it; page controls stay usable.
                page.evaluate("const button=document.createElement('button'); button.id='outside'; button.textContent='Outside'; document.body.appendChild(button)")
                page.mouse.click(300, 200)
                page.keyboard.down("w")
                page.wait_for_function("Module.inputProbe.held[0]")
                page.locator("#outside").focus()
                page.wait_for_function("!Module.inputProbe.held.some(Boolean)")
                stable = advance()
                page.keyboard.up("w")
                page.keyboard.press("w")
                unchanged(stable, advance())
                # Browser visibility and lost capture use the production reset handlers.
                page.mouse.click(300, 200)
                page.keyboard.down("w")
                page.wait_for_function("Module.inputProbe.held[0]")
                page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true}); document.dispatchEvent(new Event('visibilitychange'))")
                page.wait_for_function("!Module.inputProbe.held.some(Boolean)")
                page.keyboard.up("w")
                page.evaluate("delete document.hidden; document.dispatchEvent(new Event('visibilitychange'))")
                page.wait_for_function("Module.nauRuntime.status.state === 'Running'")
                stable = advance()
                unchanged(stable, advance())
                page.set_viewport_size(dict(width=1000, height=650))
                page.evaluate("document.querySelector('#nau-window').style.cssText=''")
                advance()
                # Unknown keys never alter the portable frame.
                page.evaluate("document.querySelector('#nau-window').dispatchEvent(new KeyboardEvent('keydown',{code:'UnknownCode',bubbles:true}))")
                assert not any(advance()["held"])
                assert page.evaluate("Module.nauInputBindings.size") == 1
                page.keyboard.down("w")
                page.mouse.move(300, 200)
                page.mouse.down()
                page.evaluate("Module.nauRuntime.stop(); Module.nauRuntime.stop()")
                page.wait_for_function("Module.nauRuntime.status.state === 'Stopped'", timeout=20000)
                assert page.evaluate("Module.nauInputBindings.size") == 0
                page.keyboard.up("w")
                page.mouse.up()
                page.evaluate("document.querySelector('#nau-window').dispatchEvent(new KeyboardEvent('keydown',{code:'KeyW'}))")
                results.append(dict(dpr=dpr, movement=movement, dragBefore=before, dragAfter=rotated, stopped=True))
                context.close()
            # Host loss also detaches input through checked runtime cleanup.
            page = browser.new_page()
            page.on("console", lambda message: logs.append(message.text))
            page.goto(f"http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html")
            page.wait_for_function("Module.inputProbe?.frame > 3", timeout=30000)
            page.evaluate("document.querySelector('#nau-window').remove()")
            page.wait_for_function("['Failed','Stopped'].includes(Module.nauRuntime.status.state)", timeout=20000)
            page.wait_for_function("Module.nauInputBindings.size === 0", timeout=20000)
            # Partial installation must remove the listeners already accepted.
            page = browser.new_page()
            page.on("console", lambda message: logs.append(message.text))
            page.add_init_script("""const original=HTMLElement.prototype.addEventListener;
                HTMLElement.prototype.addEventListener=function(type, callback, options) {
                    if(this.id==='nau-window' && type==='pointermove') throw new Error('Injected input binding failure');
                    return original.call(this,type,callback,options);
                };""")
            page.goto(f"http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html")
            page.wait_for_function("Module.nauRuntime?.status.state === 'Failed'", timeout=20000)
            page.wait_for_function("Module.nauInputBindings?.size === 0", timeout=20000)
            assert any("CoreInput browser callback installation failed" in line for line in logs), logs[-20:]
            assert any("unsupported by browser CoreInput" in line for line in logs), logs[-20:]
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        (output / "runtime.log").write_text("\n".join(logs))
    return results


def native(delivery, output):
    executable = delivery / "NauDemoInputProbe.exe"
    process = subprocess.Popen([str(executable)], cwd=delivery.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    records, logs = [], []
    def read():
        for line in process.stdout:
            logs.append(line)
            if line.startswith("INPUT_PROBE "):
                records.append(json.loads(line[len("INPUT_PROBE "):]))
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    def wait(predicate):
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            if records and predicate(records[-1]):
                valid(records[-1])
                return records[-1]
            if process.poll() is not None:
                raise AssertionError("Input probe exited: " + "".join(logs[-20:]))
            time.sleep(.01)
        raise AssertionError("Native input timeout: " + "".join(logs[-15:]))
    def advance():
        frame = records[-1]["frame"]
        return wait(lambda record: record["frame"] > frame+4)
    try:
        initial = wait(lambda record: record["frame"] > 3)
        windows = json.loads(subprocess.check_output(["orca", "computer", "list-windows", "--app", f"pid:{process.pid}", "--json"], text=True))["result"]["windows"]
        assert len(windows) == 1, windows
        handle = windows[0]["id"]
        user = ctypes.WinDLL("user32")
        user.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        user.SendMessageW.argtypes = user.PostMessageW.argtypes
        user.GetDpiForWindow.argtypes = [ctypes.c_void_p]
        dpi = user.GetDpiForWindow(handle)
        def send(message, wparam=0, lparam=0):
            assert user.PostMessageW(handle, message, wparam, lparam)
        def point(x, y):
            return (x & 65535) | ((y & 65535) << 16)
        unchanged(initial, advance())
        capture_owned_window(process.pid, output / "native-initial.png")
        movement = []
        for key, axis, direction in MOVEMENTS:
            before = records[-1]
            send(0x100, ord(key.upper()))
            during = wait(lambda record: abs(record["position"][axis]-before["position"][axis]) > .04)
            send(0x101, ord(key.upper()))
            wait(lambda record: not any(record["held"]))
            released = advance()
            if key == "w":
                capture_owned_window(process.pid, output / "native-movement.png")
                changed_image(output / "native-initial.png", output / "native-movement.png")
            unchanged(released, advance())
            assert (during["position"][axis]-before["position"][axis])*direction > .03, (key, before, during)
            assert before["viewProjection"] != during["viewProjection"]
            movement.append(dict(key=key, before=before, during=during, released=released))
        before = records[-1]
        send(0x200, 0, point(300, 200))
        send(0x201, 1, point(300, 200))
        wait(lambda record: record["drag"])
        send(0x200, 1, point(300+round(50*dpi/96), 200+round(30*dpi/96)))
        rotated = wait(lambda record: distance(record["rotation"], before["rotation"]) > .01)
        rotated = advance()
        expected_drag(rotated)
        capture_owned_window(process.pid, output / "native-drag.png")
        send(0x202, 0, point(950, 650))
        wait(lambda record: not record["drag"])
        stable = advance()
        send(0x200, 0, point(600, 400))
        after = advance()
        assert distance(stable["rotation"], after["rotation"]) < .0001
        send(0x207, 0x10, point(300, 200)) # WM_MBUTTONDOWN
        wait(lambda record: record["buttons"][1])
        send(0x208, 0, point(950, 650)) # WM_MBUTTONUP outside the window
        wait(lambda record: not any(record["buttons"]))
        send(0x100, ord("W"))
        wait(lambda record: record["held"][0])
        # Focus messages can be sent directly by Windows and never enter the pump.
        user.SendMessageW(handle, 0x8, 0, 0) # WM_KILLFOCUS
        wait(lambda record: not any(record["held"]))
        stable = advance()
        unchanged(stable, advance())
        send(0x101, ord("W"))
        capture_owned_window(process.pid, output / "native-resized.png", resize=True)
        advance()
        send(0x100, ord("W"))
        send(0x201, 1, point(300, 200))
        wait(lambda record: record["held"][0] and record["drag"])
        close_windows(process.pid)
        assert process.wait(timeout=20) == 0
        reader.join(timeout=3)
        assert "presentation cleanup complete" in "".join(logs)
        return dict(movement=movement, dragBefore=before, dragAfter=rotated, stopped=True)
    finally:
        if process.poll() is None:
            close_windows(process.pid)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        (output / "runtime.log").write_text("".join(logs))


def verify(platform, configuration):
    project = pathlib.Path(__file__).resolve().parents[1]
    build = project / "build/basic-rendering-scene" / (platform.lower()+"-"+configuration.lower())
    output = build.parent / ("input-"+platform.lower()+"-"+configuration.lower())
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nau-input-") as temporary:
        root = pathlib.Path(temporary)
        delivery = root / "relocated/nested/application"
        shutil.copytree(build / "input-probe-package", delivery)
        results = web(delivery, root, output) if platform == "Web" else native(delivery, output)
    archive = hashlib.sha256((build / "selected-input/content.nau_pack").read_bytes()).hexdigest()
    (output / "results.json").write_text(json.dumps(dict(platform=platform, configuration=configuration, archive=archive, results=results, passed=True), indent=2))
    print("PASS", platform, configuration)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("Windows", "Web"))
    parser.add_argument("configuration", choices=("Debug", "Release"))
    args = parser.parse_args()
    verify(args.platform, args.configuration)

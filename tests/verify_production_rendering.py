"""Validate real relocated production rendering without observer/test services."""
import argparse
import functools
import http.server
import json
import os
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
from rendering_evidence import verify_image


def verify(platform, configuration):
    project = pathlib.Path(__file__).resolve().parents[1]
    build = project / "build/basic-rendering-scene" / (platform.lower() + "-" + configuration.lower())
    output = build.parent / ("production-" + platform.lower() + "-" + configuration.lower())
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nau-production-rendering-") as temporary:
        root = pathlib.Path(temporary)
        delivery = root / "relocated/nested/application"
        shutil.copytree(build / "package", delivery)
        if platform == "Windows":
            environment = os.environ.copy()
            environment["PATH"] = os.pathsep.join([os.environ["SystemRoot"], str(pathlib.Path(os.environ["SystemRoot"]) / "System32")])
            lines, ready = [], threading.Event()
            process = subprocess.Popen([str(delivery / "NauDemoMain.exe")], cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            def read():
                for line in process.stdout:
                    lines.append(line)
                    if "Packaged scene Running" in line:
                        ready.set()
            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            try:
                assert ready.wait(30), "Production readiness timeout"
                capture_owned_window(process.pid, output / "first.png")
                time.sleep(.3)
                capture_owned_window(process.pid, output / "second.png", resize=True)
                close_windows(process.pid)
                assert process.wait(timeout=20) == 0
                reader.join(timeout=3)
                assert "presentation cleanup complete" in "".join(lines)
                assert "Shutdown without destroying" not in "".join(lines)
            finally:
                if process.poll() is None:
                    close_windows(process.pid)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                (output / "runtime.log").write_text("".join(lines))
        else:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            logs = []
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel="chrome", headless=True, args=["--enable-unsafe-swiftshader"])
                    page = browser.new_page(viewport=dict(width=900, height=600))
                    page.on("console", lambda message: logs.append(message.text))
                    page.goto(f"http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html")
                    page.wait_for_function("Module.nauRuntime?.status?.state === 'Running'", timeout=30000)
                    page.locator("#canvas").screenshot(path=str(output / "first.png"))
                    page.wait_for_timeout(300)
                    page.locator("#canvas").screenshot(path=str(output / "second.png"))
                    page.evaluate("Module.nauRuntime.stop();Module.nauRuntime.stop()")
                    page.wait_for_function("Module.nauRuntime.status.cleanupComplete", timeout=30000)
                    assert page.evaluate("Module.nauRuntime.status.state") == "Stopped"
                    browser.close()
            finally:
                (output / "runtime.log").write_text("\n".join(logs))
                server.shutdown()
                server.server_close()
        evidence = verify_image(output / "second.png")
        first, second = (Image.open(output / name).convert("RGB") for name in ("first.png", "second.png"))
        assert first.size == second.size
        assert ImageChops.difference(first, second).getbbox(), "Production scene motion did not change output"
        (output / "results.json").write_text(json.dumps(dict(platform=platform, configuration=configuration, passed=True, image=evidence), indent=2))
        print("PASS", platform, configuration)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("Windows", "Web"))
    parser.add_argument("configuration", choices=("Debug", "Release"))
    args = parser.parse_args()
    verify(args.platform, args.configuration)

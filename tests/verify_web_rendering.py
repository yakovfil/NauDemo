"""Exercise relocated portable scene submissions in real Chrome/WebGL."""
import argparse
import functools
import http.server
import json
import pathlib
import re
import shutil
import tempfile
import threading
from playwright.sync_api import sync_playwright
from verify_web_startup import Handler
from rendering_cases import CONTENT_FAILURES, mutate
from rendering_evidence import verify_records, verify_image, verify_projection, verify_billboard_marker


def verify(configuration):
    project = pathlib.Path(__file__).resolve().parents[1]
    build = project / "build/basic-rendering-scene" / ("web-" + configuration.lower())
    output = build.parent / ("web-observer-" + configuration.lower())
    output.mkdir(exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="nau-rendering-web-") as temporary:
        root = pathlib.Path(temporary)
        delivery = root / "relocated/nested/application"
        shutil.copytree(build / "probe-package", delivery)
        html = (delivery / "index.html").read_text()
        archive = (delivery / "NauSceneRenderingProbe.data").read_bytes()
        original_loader = (delivery / "NauSceneRenderingProbe.js").read_text()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True, args=["--enable-unsafe-swiftshader"])
                for mode in ("normal", "async-motion", "visibility", "removal", "empty", "component-offset", "camera", "activation", "zero-startup", "zero-startup-stop", "init-error", "upload-error", "submit-error", "shader-error", "context-loss", "stop-upload", "stop-load", "remove-load") + CONTENT_FAILURES:
                    selected_html = html.replace("window.Module = {", "window.Module = {arguments:" + json.dumps([mode]) + ",")
                    if mode.startswith("zero-startup"):
                        selected_html = selected_html.replace("<body>", '<style id="zero-drawable">#canvas{width:0!important;height:0!important}</style><body>')
                    (delivery / "index.html").write_text(selected_html)
                    page = browser.new_page(viewport=dict(width=900, height=600), device_scale_factor=2 if mode == "normal" else 1)
                    logs = []
                    page.on("console", lambda message: logs.append(message.text))
                    page.on("pageerror", lambda error: logs.append(str(error)))
                    if mode in ("stop-load", "remove-load") or mode in CONTENT_FAILURES:
                        data = mutate(archive, mode)
                        loader, count = re.subn(r'loadPackage\(\s*\{\s*"?files"?\s*:.*?"?remote_package_size"?\s*:\s*\d+\s*\}\s*\)', 'loadPackage(' + json.dumps(dict(files=[dict(filename="/project-package/content.nau_pack", start=0, end=len(data))], remote_package_size=len(data))) + ')', original_loader, count=1, flags=re.S)
                        assert count == 1
                        page.route("**/NauSceneRenderingProbe.js", lambda route: route.fulfill(body=loader, content_type="application/javascript", headers={"Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp"}))
                        page.route("**/NauSceneRenderingProbe.data", lambda route: route.fulfill(body=data, content_type="application/octet-stream", headers={"Cross-Origin-Resource-Policy": "same-origin"}))
                    try:
                        page.goto(f"http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html")
                        failed = mode.endswith("error") or mode == "context-loss" or mode in CONTENT_FAILURES
                        if mode.startswith("zero-startup"):
                            page.wait_for_function("Module.nauRuntime?.status?.state === 'Starting'", timeout=30000)
                            page.wait_for_timeout(300)
                            assert page.evaluate("Module.nauRuntime.status.completedSteps") == 0
                            assert not page.evaluate("Module.renderSubmittedFrames || 0")
                            if mode == "zero-startup-stop":
                                page.evaluate("Module.nauRuntime.stop();Module.nauRuntime.stop()")
                            else:
                                page.evaluate("document.getElementById('zero-drawable').remove()")
                        if not failed and mode not in ("stop-load", "stop-upload", "zero-startup-stop"):
                            page.wait_for_function("Module.renderProbeReady", timeout=30000)
                            records = page.evaluate("Module.renderProbe")
                            if mode != "remove-load":
                                verify_records(records, archive)
                            else:
                                assert all(draw["object"] == "OrangeTetra" for record in records.values() for draw in record["draws"]), records
                            assert all(record["valid"] and record["ownerThread"] for record in records.values()), records
                            assert records["initial"]["updates"] == 0, records
                            count = {"normal": 3, "async-motion": 3, "visibility": 2, "removal": 2, "empty": 0, "component-offset": 4, "camera": 3, "activation": 4, "remove-load": 1, "zero-startup": 3}[mode]
                            assert len(records["frozen"]["draws"]) == count, records
                            page.locator("#canvas").screenshot(path=str(output / (mode + ".png")))
                            if mode in ("normal", "empty", "visibility", "component-offset", "camera", "activation"):
                                verify_image(output / (mode + ".png"), empty=mode == "empty")
                            if mode == "normal":
                                projection = verify_projection(output / "normal.png", records["updated"], archive)
                                (output / "normal-projection.json").write_text(json.dumps(projection, indent=2))
                                page.wait_for_function("document.getElementById('canvas').width === 1800 && document.getElementById('canvas').height === 1200")
                                for width, height in ((420, 680), (1000, 420)):
                                    page.set_viewport_size(dict(width=width, height=height))
                                    page.wait_for_function("document.getElementById('canvas').width === " + str(width*2) + " && document.getElementById('canvas').height === " + str(height*2))
                                    page.wait_for_timeout(200)
                                    image = output / f"resize-{width}-{height}.png"
                                    page.locator("#canvas").screenshot(path=str(image))
                                    verify_image(image)
                                    verify_billboard_marker(image)
                                page.evaluate("document.getElementById('canvas').style.width='0px';document.getElementById('canvas').style.height='0px'")
                                page.wait_for_function("document.getElementById('canvas').clientWidth === 0 && document.getElementById('canvas').clientHeight === 0")
                                page.wait_for_timeout(100)
                                submitted = page.evaluate("Module.renderSubmittedFrames")
                                page.wait_for_timeout(200)
                                assert page.evaluate("Module.nauRuntime.status.state") == "Running"
                                assert page.evaluate("Module.renderSubmittedFrames") == submitted
                                page.evaluate("document.getElementById('canvas').style.width='';document.getElementById('canvas').style.height=''")
                                page.wait_for_function("document.getElementById('canvas').width > 0 && document.getElementById('canvas').height > 0")
                                page.wait_for_timeout(200)
                                assert page.evaluate("Module.renderSubmittedFrames") > submitted
                                image = output / "zero-size-recovered.png"
                                page.locator("#canvas").screenshot(path=str(image))
                                verify_image(image)
                                verify_billboard_marker(image)
                            page.evaluate("Module.nauRuntime.stop();Module.nauRuntime.stop()")
                        page.wait_for_function("Module.nauRuntime?.status?.cleanupComplete", timeout=30000)
                        status = page.evaluate("Module.nauRuntime.status")
                        assert status["state"] == ("Failed" if failed else "Stopped"), status
                        page.wait_for_function("Module.renderCleanup", timeout=10000)
                        cleanup = page.evaluate("Module.renderCleanup")
                        assert cleanup["cleanup"], cleanup
                        if mode == "stop-load":
                            assert cleanup["loadAccepted"] and cleanup["loadSettled"] and cleanup["frames"] == 0 and cleanup["updates"] == 0, cleanup
                        if mode == "stop-upload":
                            assert cleanup["updates"] == 0 and cleanup["frames"] == 1, cleanup
                        if mode == "zero-startup-stop":
                            assert cleanup["updates"] == 0 and cleanup["frames"] == 0, cleanup
                        results.append(dict(mode=mode, status=status, cleanup=cleanup))
                        print("PASS", configuration, mode, flush=True)
                    finally:
                        (output / (mode + ".log")).write_text("\n".join(logs), encoding="utf-8")
                        page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    (output / "results.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configuration", choices=("Debug", "Release"))
    verify(parser.parse_args().configuration)

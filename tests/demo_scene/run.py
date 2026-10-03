"""Build and run real CPU scene checks on Windows and in Chrome; no renderer acceptance."""
import functools
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading

from playwright.sync_api import sync_playwright


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, *args):
        pass


def main():
    source = Path(__file__).resolve().parent
    engine = source.parents[1] / "../NauEngineLite"
    sdk = Path(os.environ["EMSDK"])
    evidence = engine / "build/demo-scene-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    results = {"runs": [], "passed": False}

    def run(command, name):
        print(name, flush=True)
        (evidence / f"{name}.command.json").write_text(json.dumps(command, indent=2))
        with (evidence / f"{name}.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1200)

    try:
        for platform in ("web", "native"):
            for config in ("Debug", "Release"):
                name = f"{platform}-{config.lower()}"
                build = engine / f"build/demo-scene-{name}{'-vs2026' if platform == 'native' else ''}"
                command = ["cmake", "-S", str(source), "-B", str(build)]
                if platform == "web":
                    command += ["-G", "Ninja", f"-DCMAKE_BUILD_TYPE={config}",
                                f"-DCMAKE_TOOLCHAIN_FILE={sdk}/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake"]
                else:
                    command += ["-G", "Visual Studio 18 2026", "-A", "x64", "-T", "v145,host=x64"]
                run(command, f"{name}-configure")
                run(["cmake", "--build", str(build), "--config", config,
                     "--target", "NauDemoSceneTests", "NauDemoMeshDecoder", "-j", "8"], f"{name}-build")
                run(["ctest", "--test-dir", str(build), "-C", config, "--output-on-failure", "-V"], f"{name}-ctest")
                if platform == "native":
                    results["runs"].append({"platform": platform, "config": config, "passed": True})

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(engine / "build")))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=False)
                results["browser"] = browser.version
                try:
                    for config in ("Debug", "Release"):
                        directory = engine / f"build/demo-scene-web-{config.lower()}"
                        executable = list(directory.rglob("NauDemoSceneTests.js"))
                        assert len(executable) == 1, executable
                        relative = executable[0].relative_to(directory).as_posix()
                        (directory / "test.html").write_text('''<!doctype html><meta charset="utf-8"><title>Nau CPU scene tests</title>
<script>window.lines=[]; var Module={print:s=>lines.push(s),printErr:s=>lines.push(s),
onExit:c=>window.exitCode=c,onAbort:r=>window.abortReason=String(r)};</script>
''' + f'<script src="{relative}"></script>', encoding="utf-8")
                        page = browser.new_page()
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto(f"http://127.0.0.1:{server.server_port}/{directory.name}/test.html")
                        page.wait_for_function("window.exitCode !== undefined || window.abortReason !== undefined", timeout=30000)
                        result = page.evaluate("({exitCode:window.exitCode,abort:window.abortReason,lines,isolated:crossOriginIsolated})")
                        result.update(platform="chrome", config=config, errors=errors)
                        results["runs"].append(result)
                        assert result.get("exitCode") == 0 and not result.get("abort") and not errors, result
                        assert result["isolated"] and any("[  PASSED  ] 20 tests." in line for line in result["lines"]), result
                        result["passed"] = True
                        page.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
        results["passed"] = True
    finally:
        (evidence / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Passed: {evidence}")


if __name__ == "__main__":
    main()

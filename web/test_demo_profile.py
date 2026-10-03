"""Configure and audit the CPU-only stage of the demo profile; no runtime claim."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shutil


def run(command, log):
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Command failed; see {log}")


def main():
    demo = Path(__file__).resolve().parents[1]
    engine = demo.parent / "NauEngineLite"
    modules = demo.parent / "NauEngineModules"
    sdk = Path(os.environ["EMSDK"])
    manifest = json.loads((demo / "cmake/naudemo_sources.json").read_text())
    evidence = engine / "build/demo-profile-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for platform in ("web", "native"):
        for config in ("Debug", "Release"):
            build = engine / f"build/{platform}-demo-cpu-{config.lower()}{'-vs2026' if platform == 'native' else ''}"
            query = build / ".cmake/api/v1/query/codemodel-v2"
            query.parent.mkdir(parents=True, exist_ok=True)
            query.touch()
            command = ["cmake", "-S", str(engine), "-B", str(build),
                       "-DNAU_RUNTIME_PROFILE=scene", "-DBUILD_SHARED_LIBS=OFF",
                       f"-DNAU_EXTERNAL_RUNTIME_FILE={demo / 'cmake/NauDemoRuntime.cmake'}",
                       f"-DNAU_MODULES_SOURCE_DIR={modules}",
                       f"-DNAU_EXTERNAL_PROJECT_DIRS={modules}"]
            if platform == "web":
                command += ["-G", "Ninja", f"-DCMAKE_BUILD_TYPE={config}",
                            f"-DCMAKE_TOOLCHAIN_FILE={sdk}/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake"]
            else:
                command += ["-G", "Visual Studio 18 2026", "-A", "x64", "-T", "v145,host=x64"]
            run(command, evidence / f"{platform}-{config}.log")
            reply = build / ".cmake/api/v1/reply"
            index = json.loads(max(reply.glob("index-*.json"), key=lambda p: p.stat().st_mtime).read_text())
            model = json.loads((reply / index["reply"]["codemodel-v2"]["jsonFile"]).read_text())
            configuration = next(c for c in model["configurations"] if c["name"] == config)
            targets = {t["name"]: json.loads((reply / t["jsonFile"]).read_text()) for t in configuration["targets"]}
            assert {"CoreScene", "CoreAssets", "NauFrameworkScene", "NauKernel", "PlatformApp"} <= targets.keys()
            assert not set(manifest["excluded_targets"]) & targets.keys()
            assert "NauFrameworkMinimal" not in targets and "MinimalAppSample" not in targets
            for target in targets.values():
                directory = target["paths"]["source"].replace("\\", "/")
                if "3rdparty_libs/" in directory:
                    assert directory.split("3rdparty_libs/", 1)[1].split("/")[0] in manifest["dependencies"], directory
                if platform == "native":
                    flags = json.dumps(target.get("compileGroups", []))
                    assert "-pthread" not in flags and "EMSCRIPTEN" not in flags, flags
            source_groups = dict(manifest["sources"])
            if platform == "web":
                source_groups.update(manifest["browser_targets"])
            else:
                assert not set(manifest["browser_targets"]) & targets.keys()
            for name, sources in source_groups.items():
                actual = {s["path"].replace("\\", "/") for s in targets[name]["sources"] if s["path"].endswith(".cpp")}
                expected = set(sources)
                actual = {p.removeprefix(modules.as_posix() + "/") for p in actual}
                assert actual == expected, (name, actual ^ expected)
            summaries[f"{platform}-{config}"] = sorted(targets)
            print(f"PASS {platform} {config}: explicit sources and dependency graph", flush=True)

    # Exercise source diagnostics in a disposable source tree, never remove real dependencies.
    fixture = Path(tempfile.mkdtemp(prefix="demo-missing-source-", dir=engine / "build"))
    (fixture / "cmake").mkdir()
    shutil.copy2(demo / "cmake/NauDemoRuntime.cmake", fixture / "cmake/NauDemoRuntime.cmake")
    shutil.copy2(demo / "cmake/naudemo_sources.json", fixture / "cmake/naudemo_sources.json")
    (fixture / "modules/cmake").mkdir(parents=True)
    shutil.copy2(modules / "cmake/NauMinimalRuntime.cmake", fixture / "modules/cmake/NauMinimalRuntime.cmake")
    shutil.copy2(engine / "cmake/NauStandaloneMinimal.cmake", fixture / "cmake/NauStandaloneMinimal.cmake")
    for name in manifest["dependencies"]:
        path = fixture / "engine/3rdparty_libs" / name / "CMakeLists.txt"
        path.parent.mkdir(parents=True)
        path.touch()
    probe = fixture / "check.cmake"
    probe.write_text(f'set(NAU_ENGINE_SOURCE_DIR "{fixture.as_posix()}")\n'
                     f'set(NAU_MODULES_SOURCE_DIR "{(fixture / "modules").as_posix()}")\n'
                     f'include("{(fixture / "cmake/NauDemoRuntime.cmake").as_posix()}")\n')
    result = subprocess.run(["cmake", "-P", str(probe)], capture_output=True, text=True)
    assert result.returncode != 0 and "Missing demo runtime source:" in result.stderr, result.stderr
    (evidence / "missing-source.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    current = json.loads((engine / "CMakePresets.json").read_text())
    for group in ("configurePresets", "buildPresets", "testPresets"):
        assert not any("vs2022" in p["name"] for p in current.get(group, []))
    (evidence / "results.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print("PASS missing-source diagnostics and browser preset definitions")


if __name__ == "__main__":
    main()

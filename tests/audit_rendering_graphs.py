"""Audit actual CMake targets for profile and platform dependency exclusions."""
import json
import pathlib
import subprocess

project = pathlib.Path(__file__).resolve().parents[1]
engine = project.parent / "NauEngineLite"
results = []
for profile in ("basic-rendering-scene", "non-rendering-scene"):
    for platform in ("windows", "web"):
        for configuration in ("debug", "release"):
            build = project / "build" / ("basic-rendering-scene" if profile == "basic-rendering-scene" else "") / (platform + "-" + configuration)
            query = build / ".cmake/api/v1/query"
            query.mkdir(parents=True, exist_ok=True)
            (query / "codemodel-v2").write_text("")
            completed = subprocess.run(["cmake", "-S", str(engine), "-B", str(build)], capture_output=True, text=True)
            assert completed.returncode == 0, completed.stdout + completed.stderr
            reply = build / ".cmake/api/v1/reply"
            index = json.loads(max(reply.glob("index-*.json"), key=lambda path: path.stat().st_mtime).read_text())
            model = json.loads((reply / index["reply"]["codemodel-v2"]["jsonFile"]).read_text())
            targets = {target["name"] for config in model["configurations"] for target in config["targets"]}
            policy = json.loads((project / ("portable_rendering_project.json" if profile == "basic-rendering-scene" else "portable_project.json")).read_text())
            requested_input = "CoreInput" in policy["modules"]
            excluded = {"Graphics", "Physics", "Audio", "Animation", "VFX", "Qt6::Core", "usd"}
            if not requested_input:
                excluded.add("CoreInput")
            assert not targets & excluded, targets & excluded
            assert ("CoreInput" in targets) == requested_input
            if platform == "web":
                assert not targets & {"gainput", "gainputstatic"}
            if platform == "web" or profile == "non-rendering-scene":
                assert "Render" not in targets
            if profile == "non-rendering-scene":
                assert "SceneRenderer" not in targets and "NauBrowserRenderer" not in targets
            else:
                assert "SceneRenderer" in targets
                assert ("Render" in targets) == (platform == "windows")
                assert ("NauBrowserRenderer" in targets) == (platform == "web")
            results.append(dict(profile=profile, platform=platform, configuration=configuration, targets=sorted(targets)))
destination = project / "build/basic-rendering-scene/graph-audits.json"
destination.write_text(json.dumps(results, indent=2))
print("PASS", len(results), "target graphs")

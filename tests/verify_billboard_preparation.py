"""Exercise real host cooking, deterministic identities and failed publication."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from PIL import Image
from verify_web_startup import unpack, read_scene


def verify():
    project = pathlib.Path(__file__).resolve().parents[1]
    checkout = project.parent
    tools = checkout / "NauEditorPublic/build/latest-release/bin/Release"
    usd = checkout / "NauEngineLite/engine/3rdparty_libs/build/openusd/install"
    python = pathlib.Path(subprocess.check_output(["py", "-3.10", "-c", "import sys;print(sys.executable)"], text=True).strip())
    output = project / "build/billboard-preparation-validation"
    output.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(map(str,(tools,tools/"plugins",python.parent,usd/"bin",usd/"lib")))+os.pathsep+environment["PATH"]
    environment["PYTHONPATH"] = str(usd/"lib/python")
    environment["PXR_PLUGINPATH_NAME"] = os.pathsep.join(map(str,(tools/"plugins",usd/"plugin/usd")))
    original = {str(path.relative_to(project)):hashlib.sha256(path.read_bytes()).hexdigest() for path in (project/"content").rglob("*") if path.is_file()}
    results=[]
    with tempfile.TemporaryDirectory(prefix="nau-billboard-preparation-") as temporary:
        root=pathlib.Path(temporary).resolve()
        candidate=root/"project"
        assert candidate.resolve().is_relative_to(root)
        candidate.mkdir()
        for name in ("content","config"): shutil.copytree(project/name,candidate/name)
        for name in ("portable_rendering_project.json","portable_project.json"): shutil.copy2(project/name,candidate/name)
        prepared=candidate/"build/prepared"
        command=[str(python),str(checkout/"NauEngineModules/tools/asset_tools/prepare_packaged_project.py"),"--project",str(candidate),"--output",str(prepared),"--asset-tool",str(tools/"AssetToolCmd.exe"),"--pack-tool",str(tools/"AssetPackToolCmd.exe"),"--module",str(project/"build/portable-host-components/bin/Release/MainGameModule.dll"),"--declaration",str(candidate/"portable_rendering_project.json")]
        def run(name,arguments=command,expected=True,env=environment):
            completed=subprocess.run(arguments,cwd=root,env=env,capture_output=True,text=True)
            text=completed.stdout+completed.stderr
            (output/(name+".log")).write_text(text,encoding="utf-8")
            assert (completed.returncode==0)==expected,(name,text)
            results.append(dict(name=name,exitCode=completed.returncode))
            print("PASS",name,flush=True)
        run("first")
        archive=prepared/"content.nau_pack"; initial=archive.read_bytes()
        run("repeat")
        assert archive.read_bytes()==initial,"Repeated real scene cooking changed the archive"
        files=unpack(initial)
        _,objects=read_scene(next(data for path,data in files.items() if path.endswith("666666666684.nscene")))
        identities=[]
        for obj in objects:
            identities.append(obj["uid"])
            identities.extend(component["uid"] for component in [obj["rootComponent"]]+obj["additionalComponents"])
        assert len(identities)==len(set(identities))
        marker=next(component for obj in objects for component in [obj["rootComponent"]]+obj["additionalComponents"] if component["uid"].endswith("666666666691"))
        assert marker["properties"]["texture"]=="uid:22222222-3333-4444-5555-666666666690"
        source=candidate/"content/textures/portable_marker.png"; authored=source.read_bytes()
        image=Image.open(source).convert("RGBA"); image.putpixel((10,10),(17,31,47,255)); image.save(source)
        run("changed-pixels")
        changed=archive.read_bytes(); assert changed!=initial
        pixels=next(data[24:] for path,data in unpack(changed).items() if path.endswith("666666666690.ntex"))
        assert pixels[(10*64+10)*4:(10*64+10)*4+4]==bytes((17,31,47,255))
        source.unlink()
        run("missing-png",expected=False); assert archive.read_bytes()==changed
        source.write_bytes(b"invalid PNG")
        run("corrupt-png",expected=False); assert archive.read_bytes()==changed
        source.write_bytes(authored)
        # A shadow package tests the actual host interpreter without uninstalling anything.
        shadow=root/"without-pillow"; (shadow/"PIL").mkdir(parents=True)
        (shadow/"PIL/__init__.py").write_text('raise ImportError("Pillow intentionally absent")\n')
        no_decoder=environment.copy(); no_decoder["PYTHONPATH"]=str(shadow)+os.pathsep+environment["PYTHONPATH"]
        run("missing-decoder",expected=False,env=no_decoder)
        nonrendering=command.copy(); nonrendering[-1]=str(candidate/"portable_project.json")
        run("non-rendering-without-decoder",arguments=nonrendering,env=no_decoder)
    after={str(path.relative_to(project)):hashlib.sha256(path.read_bytes()).hexdigest() for path in (project/"content").rglob("*") if path.is_file()}
    assert original==after,"Validation altered authored content"
    (output/"results.json").write_text(json.dumps(dict(cases=results,authoredUnchanged=True),indent=2))


if __name__=="__main__": verify()

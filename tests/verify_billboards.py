"""Validate packaged billboard pixels, scene identity and texture lifetime."""
import argparse
import functools
import http.server
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading
import time
from PIL import Image
from playwright.sync_api import sync_playwright
from verify_web_startup import Handler, unpack
from verify_native_startup import close_windows
from verify_native_rendering import capture_owned_window
from rendering_cases import mutate

CASES = ("billboard-only", "billboard-distance", "billboard-fov", "billboard-facing", "billboard-parent", "billboard-share", "billboard-swap", "billboard-hidden", "billboard-remove", "billboard-behind", "billboard-near", "billboard-far", "billboard-depth", "billboard-front", "billboard-edge", "stop-texture", "remove-texture", "replace-texture", "missing-texture", "corrupt-texture", "texture-dimensions", "invalid-billboard-size")
MUTATIONS = set(CASES[-7:])
FAILURES = set(CASES[-4:])


def inspect(records, archive, mode, screenshot):
    record = records["frozen"]
    assert record["valid"] and record["ownerThread"]
    draws = record["billboards"]
    expected = 0 if mode in ("billboard-hidden", "billboard-remove", "remove-texture") else 2 if mode == "billboard-share" else 1
    assert len(draws) == expected, (mode, draws)
    if mode == "billboard-parent":
        position = (1 + .4*math.cos(.5) - .9*math.sin(.5), .5 + .4*math.sin(.5) + .9*math.cos(.5), -8)
        assert all(abs(a-b) < .005 for a,b in zip(draws[0]["position"],position)), draws
    if mode == "billboard-distance":
        # Native scene composition uses SSE reciprocal estimates; at depth 12
        # its established error is below 0.01 world units (subpixel here).
        assert all(abs(a-b) < .01 for a,b in zip(draws[0]["position"],(3.6,2.8,-12))), draws
    files = unpack(archive)
    for draw in draws:
        identity = draw["texture"].split(":", 1)[1]
        payload = next(data for path, data in files.items() if path.endswith(identity + ".ntex"))
        hash_value = 14695981039346656037
        for byte in payload[24:]: hash_value = ((hash_value ^ byte) * 1099511628211) & ((1 << 64) - 1)
        assert draw["pixelHash"] == str(hash_value), draw
    if mode in ("billboard-swap", "replace-texture"):
        assert draws[0]["texture"].endswith("666666666694")
    image = Image.open(screenshot).convert("RGB")
    width, height = image.size
    checks = 0
    if mode not in ("billboard-depth",):
        for draw in draws:
            vp, p = record["viewProjection"].copy(), draw["position"]
            original_width, original_height = record["drawable"]
            ratio = (height / width) / (original_height / original_width)
            for column in range(4): vp[column*4] *= ratio
            clip = [vp[12 + row] + sum(vp[axis * 4 + row] * p[axis] for axis in range(3)) for row in range(4)]
            if clip[3] <= 0 or not -clip[3] <= clip[2] <= clip[3]: continue
            center = ((clip[0]/clip[3]+1)*width/2, (1-clip[1]/clip[3])*height/2)
            side = draw["size"] * width
            texture = draw["texture"].split(":", 1)[1]
            payload = next(data for path, data in files.items() if path.endswith(texture + ".ntex"))
            source = Image.frombytes("RGBA", (draw["width"], draw["height"]), payload[24:])
            for u,v in ((.18,.18),(.82,.18),(.18,.82),(.82,.82)):
                x,y = round(center[0]+(u-.5)*side), round(center[1]+(v-.5)*side)
                if not (4 <= x < width-4 and 4 <= y < height-4): continue
                expected_color = source.getpixel((int(u*source.width),int(v*source.height)))[:3]
                actual = image.getpixel((x,y))
                assert max(abs(a-b) for a,b in zip(actual,expected_color)) < 25, (mode, (x,y), actual, expected_color)
                checks += 1
            if mode == "billboard-front":
                x,y = round(center[0]), round(center[1])
                actual=image.getpixel((x,y))
                assert actual[2] > actual[0]*1.5, ("cutout must reveal blue mesh", actual)
    colors = [(40,220,70),(220,30,200),(240,220,30),(30,200,220)]
    marker_pixels = [(x,y) for y in range(4,height-4) for x in range(4,width-4) if any(max(abs(a-b) for a,b in zip(image.getpixel((x,y)),color)) < 12 for color in colors)]
    if mode in ("billboard-hidden","billboard-remove","remove-texture","billboard-behind","billboard-near","billboard-far","billboard-depth"):
        assert len(marker_pixels) < 10, (mode,len(marker_pixels))
    elif mode in ("billboard-only","billboard-distance","billboard-fov","billboard-facing","billboard-parent","billboard-swap","replace-texture"):
        assert len(marker_pixels) > 100, (mode,len(marker_pixels))
        bbox=(min(x for x,y in marker_pixels),min(y for x,y in marker_pixels),max(x for x,y in marker_pixels),max(y for x,y in marker_pixels))
        actual_width=bbox[2]-bbox[0]+1; actual_height=bbox[3]-bbox[1]+1
        expected_width=draws[0]["size"]*width*56/64
        assert abs(actual_width-expected_width) < 5 and abs(actual_height-expected_width) < 5, (mode,bbox,expected_width)
    return dict(sampleChecks=checks,markerPixels=len(marker_pixels),width=width,height=height)


def verify(platform, configuration):
    project=pathlib.Path(__file__).resolve().parents[1]
    build=project/"build/basic-rendering-scene"/(platform.lower()+"-"+configuration.lower())
    output=build.parent/("billboards-"+platform.lower()+"-"+configuration.lower()); output.mkdir(exist_ok=True)
    results=[]
    with tempfile.TemporaryDirectory(prefix="nau-billboard-") as temporary:
        root=pathlib.Path(temporary); delivery=root/"relocated/nested/application"
        shutil.copytree(build/"probe-package",delivery)
        if platform=="Web":
            html=(delivery/"index.html").read_text(); archive=(delivery/"NauSceneRenderingProbe.data").read_bytes()
            loader=(delivery/"NauSceneRenderingProbe.js").read_text()
            server=http.server.ThreadingHTTPServer(("127.0.0.1",0),functools.partial(Handler,directory=str(root)))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(channel="chrome",headless=True,args=["--enable-unsafe-swiftshader"])
                try:
                    for mode in CASES:
                        (delivery/"index.html").write_text(html.replace("window.Module = {","window.Module = {arguments:"+json.dumps([mode])+","))
                        page=browser.new_page(viewport=dict(width=900,height=600)); logs=[]
                        page.on("console",lambda message:logs.append(message.text)); page.on("pageerror",lambda error:logs.append(str(error)))
                        try:
                            if mode in MUTATIONS:
                                data=mutate(archive,mode)
                                modified,count=re.subn(r'loadPackage\(\s*\{\s*"?files"?\s*:.*?"?remote_package_size"?\s*:\s*\d+\s*\}\s*\)', 'loadPackage('+json.dumps(dict(files=[dict(filename="/project-package/content.nau_pack",start=0,end=len(data))],remote_package_size=len(data)))+')',loader,count=1,flags=re.S)
                                assert count==1
                                page.route("**/NauSceneRenderingProbe.js",lambda route:route.fulfill(body=modified,content_type="application/javascript",headers={"Cross-Origin-Opener-Policy":"same-origin","Cross-Origin-Embedder-Policy":"require-corp"}))
                                page.route("**/NauSceneRenderingProbe.data",lambda route:route.fulfill(body=data,content_type="application/octet-stream",headers={"Cross-Origin-Resource-Policy":"same-origin"}))
                            page.goto(f"http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html")
                            if mode not in FAILURES and mode!="stop-texture":
                                page.wait_for_function("Module.renderProbeReady",timeout=30000)
                                records=page.evaluate("Module.renderProbe"); screenshot=output/(mode+".png")
                                page.locator("#canvas").screenshot(path=str(screenshot))
                                evidence=inspect(records,archive,mode,screenshot)
                                page.evaluate("Module.nauRuntime.stop();Module.nauRuntime.stop()")
                            else: evidence={}
                            page.wait_for_function("Module.nauRuntime?.status?.cleanupComplete",timeout=30000)
                            status=page.evaluate("Module.nauRuntime.status"); assert status["state"]==("Failed" if mode in FAILURES else "Stopped"),status
                            cleanup=page.evaluate("Module.renderCleanup"); assert cleanup["cleanup"]
                            if mode=="stop-texture": assert cleanup["loadAccepted"] and cleanup["loadSettled"] and cleanup["frames"]==cleanup["updates"]==0,cleanup
                            if mode=="billboard-share": assert "billboards releasing 1 textures" in "\n".join(logs)
                            results.append(dict(mode=mode,evidence=evidence,status=status,cleanup=cleanup)); print("PASS",platform,configuration,mode,flush=True)
                        finally: (output/(mode+".log")).write_text("\n".join(logs),encoding="utf-8"); page.close()
                finally: browser.close(); server.shutdown(); server.server_close()
        else:
            archive=(delivery/"content.nau_pack").read_bytes()
            environment=os.environ.copy(); environment["PATH"]=os.pathsep.join([os.environ["SystemRoot"],str(pathlib.Path(os.environ["SystemRoot"])/"System32")])
            for mode in CASES:
                (delivery/"content.nau_pack").write_bytes(mutate(archive,mode) if mode in MUTATIONS else archive)
                lines=[]; ready=threading.Event()
                process=subprocess.Popen([str(delivery/"NauSceneRenderingProbe.exe"),mode],cwd=root,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                def read():
                    for line in process.stdout:
                        lines.append(line)
                        if "RENDER_PROBE_READY" in line: ready.set()
                reader=threading.Thread(target=read,daemon=True); reader.start()
                try:
                    evidence={}
                    if mode not in FAILURES and mode!="stop-texture":
                        assert ready.wait(30),(mode,"".join(lines))
                        records=[json.loads(line.removeprefix("RENDER_PROBE ")) for line in lines if line.startswith("RENDER_PROBE ")][-1]
                        screenshot=output/(mode+".png"); capture_owned_window(process.pid,screenshot)
                        evidence=inspect(records,archive,mode,screenshot); close_windows(process.pid)
                    code=process.wait(timeout=30); reader.join(timeout=3)
                    assert (code!=0)==(mode in FAILURES),(mode,code,"".join(lines))
                    cleanup=[json.loads(line.removeprefix("RENDER_CLEANUP ")) for line in lines if line.startswith("RENDER_CLEANUP ")][-1]
                    assert cleanup["cleanup"] and "Shutdown without destroying" not in "".join(lines)
                    if mode=="stop-texture": assert cleanup["loadAccepted"] and cleanup["loadSettled"] and cleanup["frames"]==cleanup["updates"]==0,cleanup
                    if mode=="billboard-share": assert "billboards releasing 1 textures" in "".join(lines)
                    results.append(dict(mode=mode,evidence=evidence,exitCode=code,cleanup=cleanup)); print("PASS",platform,configuration,mode,flush=True)
                finally:
                    if process.poll() is None:
                        close_windows(process.pid)
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: process.kill(); process.wait()
                    (output/(mode+".log")).write_text("".join(lines),encoding="utf-8")
    (output/"results.json").write_text(json.dumps(results,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("platform",choices=("Windows","Web")); parser.add_argument("configuration",choices=("Debug","Release"))
    args=parser.parse_args(); verify(args.platform,args.configuration)

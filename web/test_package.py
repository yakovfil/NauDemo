"""Run the actual staged NauDemo in installed Chrome with an isolated local host."""
import argparse
import functools
import http.server
import json
from pathlib import Path
import threading
import importlib.util
import math
import struct
import hashlib
import base64
import sys
import subprocess
import tempfile
import time
from contextlib import contextmanager
sys.dont_write_bytecode = True
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, *args):
        pass


def assert_scene_pixel(path, frame, package):
    """Check nearest asset triangles at interior pixels, away from moving edges."""
    image = Image.open(path).convert('RGB')
    asset = json.loads((package/'cube.gltf').read_text())
    binary = (package/'cube.bin').read_bytes()
    primitive = asset['meshes'][0]['primitives'][0]
    def accessor(index, format):
        a = asset['accessors'][index]
        start = asset['bufferViews'][a['bufferView']].get('byteOffset',0)
        size = struct.calcsize(format)
        return [struct.unpack_from(format,binary,start+i*size) for i in range(a['count'])]
    positions = accessor(primitive['attributes']['POSITION'],'<3f')
    normals = accessor(primitive['attributes']['NORMAL'],'<3f')
    indices = [v[0] for v in accessor(primitive['indices'],'<H')]
    def multiply(matrix, vector):
        return [sum(matrix[c*4+r]*vector[c] for c in range(4)) for r in range(4)]
    projected=[]
    for position in positions:
        p=[*position,1]
        for key in ('model','view','projection'):
            p=multiply(frame[key],p)
        projected.append([(p[0]/p[3]+1)*image.width/2,(1-p[1]/p[3])*image.height/2,p[2]/p[3]])
    left,right=min(p[0] for p in projected),max(p[0] for p in projected)
    top,bottom=min(p[1] for p in projected),max(p[1] for p in projected)
    checks=[]
    for row in range(1,10):
      for column in range(1,10):
        x,y=int(left+(right-left)*column/10)+.5,int(top+(bottom-top)*row/10)+.5
        if not (0<=x<image.width and 0<=y<image.height): continue
        nearest=None
        for i in range(0,len(indices),3):
            a,b,c=[projected[index] for index in indices[i:i+3]]
            d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(d)<1e-8: continue
            u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/d
            v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/d
            w=1-u-v
            if min(u,v,w)<0: continue
            depth=u*a[2]+v*b[2]+w*c[2]
            margin=min(weight*abs(d)/math.hypot(p[0]-q[0],p[1]-q[1])
                       for weight,p,q in ((u,b,c),(v,c,a),(w,a,b)))
            if nearest is None or depth<nearest[0]: nearest=(depth,indices[i],margin)
        # Choose pixels geometrically, before looking at screenshot colors.
        # A compositor frame may lag the submitted frame around a moving edge.
        if nearest is None or nearest[2]<12: continue
        normal=multiply(frame['model'],[*normals[nearest[1]],0])[:3]
        light=[-.5,.8,.6]
        diffuse=max(0,sum(a*b for a,b in zip(normal,light))/math.sqrt(sum(a*a for a in normal)*sum(a*a for a in light)))
        expected=[round(c*(.25+.75*diffuse)*255) for c in [.06,.32,.95]]
        actual=image.getpixel((int(x),int(y)))
        checks.append({'pixel':[int(x),int(y)],'actual':actual,'expected':expected,'edgeMargin':nearest[2]})
    assert len(checks)>=4,'Too few interior pixels to validate scene/depth provenance'
    assert all(max(abs(a-b) for a,b in zip(check['actual'],check['expected']))<=22 for check in checks), f'Nearest-face/depth shading mismatch: {checks}'
    return checks


def capture_frame(page, path, package, capture_scale=1):
    # At presentation cadence a screenshot can span several submitted frames.
    # Validate against snapshots immediately before and after capture.
    canvas=page.locator('#canvas')
    canvas.scroll_into_view_if_needed()
    page.wait_for_timeout(100)
    box=canvas.bounding_box()
    scroll=page.evaluate('({x:scrollX,y:scrollY})')
    box['x']+=scroll['x']
    box['y']+=scroll['y']
    session=page.context.new_cdp_session(page)
    for attempt in range(8):
        before=page.evaluate('structuredClone(Module.nauRender)')
        capture=session.send('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,
            'clip':{'x':box['x'],'y':box['y'],'width':box['width'],'height':box['height'],'scale':capture_scale}})
        path.write_bytes(base64.b64decode(capture['data']))
        after=page.evaluate('structuredClone(Module.nauRender)')
        if after['frames']-before['frames']>8:
            continue
        for frame in (before,after):
            try:
                assert_scene_pixel(path,frame,package)
            except AssertionError:
                continue
            session.detach()
            return frame
    session.detach()
    raise AssertionError('Screenshot did not match geometry from nearby submitted frames')


def assert_font_pixels(path, references, scale=1, variant=0, color=(1,1,1,1), position=(24,24)):
    """Compare actual canvas pixels against stb coverage from the packaged TTF."""
    stem=f'text-reference-{scale}'+(f'-variant{variant}' if variant else '')
    metadata = json.loads((references/(stem+'.json')).read_text())
    coverage = (references/(stem+'.raw')).read_bytes()
    image = Image.open(path).convert('RGB')
    background = (6, 9, 14)
    # CDP temporarily hides the scrollbar when capturing, shifting a centered
    # canvas by half its width. Locate the canvas edge independently of glyphs.
    origin = next(x for x in range(24*scale) if image.getpixel((x,100*scale)) == background)
    errors = []
    for y in range(metadata['height']):
        for x in range(metadata['width']):
            alpha = coverage[y*metadata['width']+x]/255*color[3]
            expected = [round(c*(1-alpha)+255*tint*alpha) for c,tint in zip(background,color)]
            point=(origin+position[0]*scale+metadata['left']+x,position[1]*scale+metadata['top']+y)
            if not(origin<=point[0]<image.width and 0<=point[1]<image.height):continue
            actual = image.getpixel(point)
            errors.append(max(abs(a-b) for a,b in zip(actual,expected)))
    assert max(errors) <= 2, f'Canvas glyphs differ from specified font: maximum error {max(errors)}'
    return {'pixels':len(errors),'maximumError':max(errors),'canvasOrigin':origin}


@contextmanager
def chrome_session(playwright):
    # no_defaults preserves genuine document visibility; Playwright's default
    # controlled-page settings make all pages visible in the tested version.
    with tempfile.TemporaryDirectory(prefix='nau-demo-chrome-', ignore_cleanup_errors=True) as profile:
        process = subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe',
            '--headless=new',f'--user-data-dir={profile}','--remote-debugging-port=0',
            '--no-first-run','--no-default-browser-check','about:blank'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        browser = None
        try:
            port = Path(profile)/'DevToolsActivePort'
            deadline=time.monotonic()+15
            while not port.exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Chrome did not expose its debugging port')
                time.sleep(.05)
            browser=playwright.chromium.connect_over_cdp('http://127.0.0.1:'+port.read_text().splitlines()[0],no_defaults=True)
            yield browser
        finally:
            if browser:
                try: browser.contexts[0].new_cdp_session(browser.contexts[0].pages[0]).send('Browser.close')
                except Exception: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-path", default="/")
    parser.add_argument("--text-variant",type=int,choices=(0,1,2),default=0)
    parser.add_argument("--device-scale",type=int,choices=(1,2),default=1)
    parser.add_argument("--text-readback",action='store_true',help='Require a package built with -TestHooks for exact DPR framebuffer checks')
    parser.add_argument("--text-position",nargs=2,type=int,default=(24,24))
    parser.add_argument("--text-reference", type=Path,
                        default=Path(__file__).resolve().parents[1]/'build/text-tests-native/fixtures')
    parser.add_argument("--scenario", default="success", choices=["success", "host-loss", "context-loss", "missing-buffer", "bad-shader", "bad-config", "missing-canvas", "no-context", "missing-font", "text-upload", "stop-assets", "stop-graphics", "pending-scene", "camera", "bad-link", "missing-headers", "file-url", "no-offscreen", "missing-loader", "missing-wasm", "missing-data", "blank-frame", "runner-failure"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {"package": str(args.package.resolve()), "scenario":args.scenario, "passed": False, "console": [], "errors": []}
    result['manifest'] = json.loads((args.package/'manifest.json').read_text())
    result['runnerSha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['python'] = sys.version
    spec = importlib.util.spec_from_file_location("nau_demo_host", args.package / "serve.py")
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    server = host.PackageServer(("127.0.0.1", 0), host.PackageHandler)
    server.package_root = args.package.resolve()
    server.base_path = args.base_path
    if args.scenario == 'missing-headers':
        host.PackageHandler.end_headers = http.server.SimpleHTTPRequestHandler.end_headers
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            chrome = chrome_session(playwright)
            browser = chrome.__enter__()
            result["browser"] = browser.version
            try:
                context = browser.contexts[0]
                page = context.pages[0]
                page.set_viewport_size({"width":1280,"height":900})
                metrics=page.context.new_cdp_session(page)
                metrics.send('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,'deviceScaleFactor':args.device_scale,'mobile':False})
                settings={}
                if args.text_variant or tuple(args.text_position)!=(24,24):
                    source=(args.package/'NauDemo.js').read_text(encoding='utf-8')
                    settings={'NAU_DEMO_TEXT':'Glyph AVjgy','NAU_DEMO_TEXT_SIZE':'32','NAU_DEMO_TEXT_R':'0.25','NAU_DEMO_TEXT_G':'0.75','NAU_DEMO_TEXT_B':'0.5','NAU_DEMO_TEXT_A':'0.6'} if args.text_variant==1 else {}
                    settings.update(NAU_DEMO_TEXT_X=str(args.text_position[0]),NAU_DEMO_TEXT_Y=str(args.text_position[1]))
                    page.route('**/NauDemo.js',lambda route:route.fulfill(status=200,content_type='application/javascript',body=source+'\nObject.assign(ENV,'+json.dumps(settings)+');\n',headers={'Cross-Origin-Opener-Policy':'same-origin','Cross-Origin-Embedder-Policy':'require-corp','Cache-Control':'no-store'}))
                    if args.text_variant==2:
                        original=(args.package/'fonts/Abel-Regular.ttf').read_bytes()
                        alternate=(args.text_reference/'Abel-Changed.ttf').read_bytes()
                        assert len(original)==len(alternate)
                        def replace_font(route):
                            response=route.fetch();data=response.body();assert data.count(original)==1
                            route.fulfill(response=response,body=data.replace(original,alternate))
                        page.route('**/NauDemo.data',replace_font)
                wait = functools.partial(page.wait_for_function, polling=10)
                page.on("console", lambda message: result["console"].append(message.text))
                page.on("pageerror", lambda error: result["errors"].append(str(error)))
                page.add_init_script("window.beats=0;setInterval(()=>++window.beats,10)")
                result['requests'] = []
                page.on('request', lambda request: result['requests'].append(request.url))
                if args.scenario == 'no-offscreen':
                    page.add_init_script('window.OffscreenCanvas=undefined')
                if args.scenario in ('missing-loader','missing-wasm','missing-data'):
                    filename={'missing-loader':'NauDemo.js','missing-wasm':'NauDemo.wasm','missing-data':'NauDemo.data'}[args.scenario]
                    page.route('**/'+filename,lambda route:route.fulfill(status=404,body='Missing fixture input'))
                if args.scenario in ("missing-buffer", "context-loss", "no-context", "missing-font", "text-upload"):
                    loader_source = (args.package / "NauDemo.js").read_text(encoding="utf-8")
                    if settings:
                        loader_source += '\nObject.assign(ENV,'+json.dumps(settings)+');\n'
                    def loader(route):
                        source = loader_source
                        if args.scenario == "missing-buffer":
                            assert '/demo-package/cube.bin' in source
                            source = source.replace('/demo-package/cube.bin', '/demo-package/gone.bin')
                        elif args.scenario == "no-context":
                            source += "\nif(ENVIRONMENT_IS_PTHREAD) OffscreenCanvas.prototype.getContext=()=>null;\n"
                        elif args.scenario == 'missing-font':
                            assert '/demo-package/fonts/Abel-Regular.ttf' in source
                            source=source.replace('/demo-package/fonts/Abel-Regular.ttf','/demo-package/fonts/gone.ttf')
                        elif args.scenario == 'text-upload':
                            source += '\nif(ENVIRONMENT_IS_PTHREAD) WebGL2RenderingContext.prototype.createTexture=()=>null;\n'
                        else:
                            source += """\nif(ENVIRONMENT_IS_PTHREAD) self.addEventListener('message', e=>{
                                if(e.data.nauTestLoss){e.stopImmediatePropagation();
                                if(GL.currentContext) GL.currentContext.GLctx.getExtension('WEBGL_lose_context').loseContext();}
                            },true);\n"""
                        route.fulfill(status=200, content_type="application/javascript", body=source,
                            headers={"Cross-Origin-Opener-Policy": "same-origin",
                                     "Cross-Origin-Embedder-Policy": "require-corp",
                                     "Cache-Control": "no-store"})
                    page.route("**/NauDemo.js", loader)
                if args.scenario in ("bad-shader", "bad-config", "bad-link", "blank-frame"):
                    def corrupt(route):
                        response = route.fetch()
                        body = response.body()
                        source = b'vec3(0.06, 0.32, 0.95)' if args.scenario=='blank-frame' else b'#version 300 es' if args.scenario == 'bad-shader' else b'blue-diffuse'
                        assert source in body
                        replacement=b'vec3(0.0)'.ljust(len(source)) if args.scenario=='blank-frame' else b'!'*len(source)
                        if args.scenario=='bad-link':
                            body=body.replace(b'worldNormal',b'otherNormal',2)
                        else:
                            body = body.replace(source, replacement, 1)
                        route.fulfill(response=response, body=body)
                    page.route("**/NauDemo.data", corrupt)
                if args.scenario == "missing-canvas":
                    page.add_init_script("new MutationObserver(()=>document.getElementById('canvas')?.remove()).observe(document,{childList:true,subtree:true})")
                if args.scenario in ('stop-assets','stop-graphics'):
                    def stop_stage(route):
                        response = route.fetch()
                        stage = args.scenario.removeprefix('stop-')
                        html = response.text().replace("stopButton.addEventListener", "Object.defineProperty(Module,'nauDemoStage',{set(value){if(value==='"+stage+"') Module.nauRuntime.stop();}});\nstopButton.addEventListener")
                        route.fulfill(response=response, body=html)
                    page.route("**/", stop_stage)
                if args.scenario == 'pending-scene':
                    def pending_scene(route):
                        response = route.fetch()
                        html = response.text().replace('window.Module = {','window.Module = {nauDemoPendingTest:true,')
                        route.fulfill(response=response,body=html)
                    page.route('**/',pending_scene)
                page.goto((args.package.resolve()/"index.html").as_uri() if args.scenario=="file-url" else f"http://127.0.0.1:{server.server_port}{args.base_path}")
                wait("['Running','Stopped'].includes(Module.nauRuntime?.status?.state) || document.getElementById('status').textContent === 'Failed'", timeout=60000)
                result["startup"] = page.evaluate("({status:Module.nauRuntime?.status, render:Module.nauRender, message:document.getElementById('message').textContent})")
                if args.scenario in ('missing-loader','missing-wasm','missing-data','missing-headers','file-url','no-offscreen'):
                    assert page.locator('#status').inner_text()=='Failed',result
                    assert page.locator('#cleanup').inner_text()!='Complete',result
                    assert result['startup']['message'],result
                    result['passed']=True
                    return
                if args.scenario in ('stop-assets','stop-graphics'):
                    assert result['startup']['status']['state'] == 'Stopped', result
                    assert result['startup']['status']['cleanupComplete'], result
                    assert result['startup']['status']['completedSteps'] == 0, result
                    assert not result['startup'].get('render'), result
                    result['passed'] = True
                    return
                if args.scenario in ("missing-buffer", "bad-shader", "bad-link", "bad-config", "missing-canvas", "no-context", "missing-font", "text-upload"):
                    if args.scenario == 'missing-canvas' and not result['startup'].get('status'):
                        assert page.locator('#status').inner_text() == 'Failed'
                    else:
                        wait("Module.nauRuntime.status.cleanupComplete", timeout=30000)
                        result['terminal'] = page.evaluate('Module.nauRuntime.status')
                        assert result['terminal']['state'] == 'Failed', result
                        assert result['terminal']['completedSteps'] == 0, result
                        if args.scenario=='missing-font':
                            assert 'Abel-Regular.ttf' in result['terminal']['message'],result
                        if args.scenario=='text-upload':
                            assert 'text upload' in result['terminal']['message'],result
                    result['passed'] = True
                    return
                assert result["startup"].get("status", {}).get("state") == "Running", result["startup"]
                if args.scenario == 'pending-scene':
                    wait('Module.nauDemoPending?.pending')
                    page.evaluate('Module.nauRuntime.stop();Module.nauRuntime.stop()')
                    wait("Module.nauRuntime.status.state==='Stopping'")
                    page.wait_for_timeout(200)
                    result['pending'] = page.evaluate('({status:Module.nauRuntime.status,work:Module.nauDemoPending,render:Module.nauRender})')
                    assert not result['pending']['status']['cleanupComplete']
                    assert result['pending']['work']['deactivated'] == 1
                    assert result['pending']['work']['destroyed'] == 0
                    page.evaluate('Module.nauDemoReleasePending=true')
                    wait('Module.nauRuntime.status.cleanupComplete')
                    result['terminal'] = page.evaluate('({status:Module.nauRuntime.status,work:Module.nauDemoPending,render:Module.nauRender})')
                    assert result['terminal']['status']['state']=='Stopped',result
                    assert result['terminal']['work']['destroyed']==1,result
                    assert result['pending']['render']['frames']==result['terminal']['render']['frames'],result
                    result['passed']=True
                    return
                wait("Module.nauRender?.frames >= 3")
                first = capture_frame(page,args.output/'cube-first.png',args.package)
                result['first']=first
                result['textPixels']=assert_font_pixels(args.output/'cube-first.png',args.text_reference,args.device_scale,args.text_variant,(.25,.75,.5,.6) if args.text_variant==1 else (1,1,1,1),args.text_position)
                result['firstPixels']=assert_scene_pixel(args.output/'cube-first.png',first,args.package)
                wait(f"Module.nauRender.frames >= {first['frames'] + 11}")
                second = capture_frame(page,args.output/'cube-rotated.png',args.package)
                result['second']=second
                result['secondPixels']=assert_scene_pixel(args.output/'cube-rotated.png',second,args.package)
                for name in ("cube-first.png", "cube-rotated.png"):
                    image = Image.open(args.output / name).convert("RGB")
                    blue = sum(b > 40 and b > r * 2 and b > g * 1.5 for r, g, b in image.getdata())
                    assert blue > image.width * image.height * 0.01, f"Blank or missing blue cube: {name} ({blue} pixels)"
                difference = ImageChops.difference(Image.open(args.output / "cube-first.png").convert("RGB"), Image.open(args.output / "cube-rotated.png").convert("RGB"))
                assert difference.getbbox(), "Rendered orientations did not change"
                assert first["model"] != second["model"]
                assert second["indices"] == 36 and second["worker"]
                result["first"], result["second"] = first, second
                if args.scenario == 'camera':
                    page.evaluate('Module.nauDemoMoveCamera=true')
                    wait('Math.abs(Module.nauRender.view[12])>1')
                    moved = page.evaluate('structuredClone(Module.nauRender)')
                    assert abs(moved['projection'][5]-math.sqrt(3))<1e-4
                    page.locator('#canvas').screenshot(path=str(args.output/'cube-camera.png'))
                    assert ImageChops.difference(Image.open(args.output/'cube-rotated.png').convert('RGB'),Image.open(args.output/'cube-camera.png').convert('RGB')).getbbox()
                    result['camera']=moved
                if args.scenario == 'runner-failure':
                    raise AssertionError('Deliberately broken acceptance assertion')
                if args.scenario == 'success':
                    before=page.evaluate('({time:performance.now(),steps:Module.nauRuntime.status.completedSteps,beats})')
                    page.wait_for_timeout(5000)
                    after=page.evaluate('({time:performance.now(),steps:Module.nauRuntime.status.completedSteps,beats})')
                    result['rate']=(after['steps']-before['steps'])*1000/(after['time']-before['time'])
                    assert result['rate']>15,result['rate']
                    assert after['beats']-before['beats']>300
                    simulation=page.evaluate('Module.nauDemoSimulation')
                    expected=(.35+simulation['milliseconds']*.000785398163)%(2*math.pi)
                    assert abs(simulation['angle']-expected)<.01745
                    result['simulation']=simulation
                    other=page.context.new_page()
                    other.goto('about:blank')
                    other.bring_to_front()
                    result['visibilityCheckpoint']='hide'
                    wait('document.hidden')
                    page.wait_for_timeout(400)
                    page.bring_to_front()
                    result['visibilityCheckpoint']='show'
                    wait('!document.hidden')
                    result['visibilityCheckpoint']='resume'
                    resumed=page.evaluate('Module.nauRuntime.status.completedSteps')
                    wait(f'Module.nauRuntime.status.completedSteps>{resumed+2}')
                    assert page.evaluate('Module.nauDemoSimulation.elapsed')<=100
                    history=page.evaluate('Module.nauRuntime.history')
                    updates=[b for a,b in zip(history,history[1:]) if b['completedSteps']>a['completedSteps']]
                    assert any(b['timestamp']-a['timestamp']<80 for a,b in zip(updates,updates[1:])),updates
                    result['visibility']=True
                    other.close()
                    page.locator('#canvas').evaluate("c=>{c.style.width='420px';c.style.height='260px'}")
                    wait('Module.nauRender.width===420 && Module.nauRender.height===260')
                    resized = page.evaluate('structuredClone(Module.nauRender)')
                    assert abs(resized['projection'][0] / resized['projection'][5] - 260/420) < 1e-5
                    page.locator('#canvas').evaluate("c=>c.style.height='0px'")
                    page.wait_for_timeout(250)
                    frozen = page.evaluate('Module.nauRender.frames')
                    page.wait_for_timeout(250)
                    assert page.evaluate('Module.nauRender.frames') == frozen
                    page.locator('#canvas').evaluate("c=>c.style.height='260px'")
                    wait(f'Module.nauRender.frames>{frozen}')
                    session = page.context.new_cdp_session(page)
                    session.send('Emulation.setDeviceMetricsOverride', {'width':1280,'height':900,'deviceScaleFactor':2,'mobile':False})
                    wait('Module.nauRender.width===840 && Module.nauRender.height===520')
                    wait('Module.nauText.scale===2 && Module.nauText.textures===1')
                    if args.text_readback:
                        page.evaluate('Module.nauTextSurface=null;Module.nauTextCaptureRequest=true')
                        wait('Module.nauTextSurface')
                        surface=page.evaluate('Module.nauTextSurface')
                        assert surface['width']==840,(surface['width'],surface['height'],page.evaluate('Module.nauText'))
                        raw=Image.frombytes('RGBA',(surface['width'],surface['height']),bytes(surface['pixels'])).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                        raw.save(args.output/'text-dpr2-framebuffer.png')
                        result['textDprPixels']=assert_font_pixels(args.output/'text-dpr2-framebuffer.png',args.text_reference,2,args.text_variant,(.25,.75,.5,.6) if args.text_variant==1 else (1,1,1,1),args.text_position)
                    capture_frame(page,args.output/'text-dpr2.png',args.package,2)
                    result['resized'] = page.evaluate('structuredClone(Module.nauRender)')
                    session.send('Emulation.clearDeviceMetricsOverride')
                    page.locator('#canvas').evaluate("c=>{c.style.width='100000px';c.style.height='1000px'}")
                    wait('Module.nauRender.width>840 && Module.nauRender.width<100000')
                    limited = page.evaluate('structuredClone(Module.nauRender)')
                    assert abs(limited['width']/limited['height'] - 100) < 1
                    result['limited'] = limited
                    page.locator('#canvas').evaluate("c=>{c.style.width='420px';c.style.height='260px'}")
                if args.scenario == 'host-loss':
                    page.locator('#canvas').evaluate('c=>c.remove()')
                elif args.scenario == 'context-loss':
                    page.evaluate("Object.values(PThread.pthreads).forEach(w=>w.postMessage({nauTestLoss:true}))")
                    wait("Module.nauRuntime.status.state==='Failed'", timeout=10000)
                else:
                    page.locator("#stop").click()
                page.evaluate("Module.nauRuntime.stop()")
                wait("Module.nauRuntime.status.cleanupComplete", timeout=30000)
                result["terminal"] = page.evaluate("({status:Module.nauRuntime.status, render:Module.nauRender})")
                expected = 'Failed' if args.scenario in ('host-loss','context-loss') else 'Stopped'
                assert result["terminal"]["status"]["state"] == expected, result["terminal"]
                assert result["terminal"]["render"]["stopped"]
                result['textCleanup']=page.evaluate('Module.nauText')
                assert result['textCleanup']['stopped'] and result['textCleanup']['textures']==0
                frozen = result['terminal']['render']['frames']
                page.wait_for_timeout(150)
                assert page.evaluate('Module.nauRender.frames') == frozen
                assert not page.evaluate('Module.nauRuntime.start().accepted')
                assert all(url.startswith(f'http://127.0.0.1:{server.server_port}{args.base_path}') or url.startswith('blob:') for url in result['requests']), result['requests']
                if args.scenario=='success':
                    page.locator('#canvas').evaluate("c=>c.dataset.previouslyUsed='true'")
                    page.reload()
                    wait("Module.nauRuntime?.status?.state==='Running' && Module.nauRender?.frames>=2",timeout=30000)
                    assert page.locator('#canvas').get_attribute('data-previously-used') is None
                    page.locator('#stop').click()
                    wait('Module.nauRuntime.status.cleanupComplete')
                    result['reloaded']=page.evaluate('Module.nauRuntime.status')
                    assert result['reloaded']['state']=='Stopped'
                assert not result["errors"], result["errors"]
                result["passed"] = True
            finally:
                chrome.__exit__(None,None,None)
    except Exception as error:
        result["passed"] = False
        result["error"] = str(error)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        (args.output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("console","first","second")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()

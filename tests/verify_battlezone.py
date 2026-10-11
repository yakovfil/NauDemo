"""Exercise relocated native and nested-URL browser Battlezone deliveries."""
import argparse
import ctypes
import functools
import hashlib
import http.server
import json
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
from verify_native_rendering import capture_owned_window
from verify_native_startup import close_windows
from verify_web_startup import Handler


def mutate_required(raw, mode):
    if mode == 'missing-game':
        return raw.replace(b'content/game/battlezone.json', b'content/game/missingxxx.json', 1)
    if mode == 'missing-sound':
        return raw.replace(b'audio/fire.wav', b'audio/miss.wav', 1)
    separator=raw.index(b'\n\n\n')+3
    length=int(next(line.split(b':',1)[1] for line in raw[:separator].splitlines() if line.startswith(b'Content-Length:')))
    header=json.loads(raw[separator:separator+length])
    path='content/game/battlezone.json' if mode=='corrupt-game' else 'audio/fire.wav'
    entry=next(e for e in header['content'] if e['filePath']==path)
    start=separator+length+entry['blobData']['offset'];end=start+entry['blobData']['size']
    result=bytearray(raw)
    if mode=='corrupt-game':
        result[start:end]=raw[start:end].replace(b'"version": 1',b'"version": 9',1)
    else:result[start+34]=32
    assert result!=raw and len(result)==len(raw)
    return bytes(result)


def image_check(path):
    image=Image.open(path).convert('RGB')
    w,h=image.size
    green=sum(g>100 and r<60 and b<60 for r,g,b in image.getdata())
    black=sum(max(pixel)<25 for pixel in image.getdata())
    assert green>500 and black>w*h*.8,(green,black,w,h)
    regions={}
    for name,box in {'hud':(0,0,w,h*.23),'world':(0,h*.23,w,h*.75),'controls':(0,h*.8,w,h)}.items():
        count=sum(g>100 and r<60 and b<60 for r,g,b in image.crop(tuple(map(int,box))).getdata())
        assert count>50,(name,count)
        regions[name]=count
    return dict(green=green,black=black,size=[w,h],regions=regions)


def native(delivery,output):
    import numpy as np
    import soundcard as sc
    logs=[];records=[]
    p=subprocess.Popen([str(delivery/'NauBattlezoneProbe.exe')],cwd=delivery.parent,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    def read():
        for line in p.stdout:
            logs.append(line)
            if line.startswith('BATTLEZONE_PROBE '): records.append(json.loads(line[17:]))
    threading.Thread(target=read,daemon=True).start()
    def wait(predicate,timeout=25):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if records and predicate(records[-1]):return records[-1]
            assert p.poll() is None,''.join(logs[-20:])
            time.sleep(.02)
        raise AssertionError(records[-1] if records else ''.join(logs[-20:]))
    captured=[];stop=threading.Event()
    def record():
        speaker=sc.default_speaker(); microphone=sc.get_microphone(speaker.id,include_loopback=True)
        with microphone.recorder(samplerate=48000,channels=2) as recorder:
            while not stop.is_set(): captured.append(recorder.record(numframes=2048))
    audio=threading.Thread(target=record,daemon=True)
    user=ctypes.WinDLL('user32')
    user.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
    user.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
    try:
        wait(lambda r:r['frame']>2)
        windows=json.loads(subprocess.check_output(['orca','computer','list-windows','--app',f'pid:{p.pid}','--json'],text=True))['result']['windows']
        handle=windows[0]['id'];user.SendMessageW(handle,7,0,0)
        audio.start();time.sleep(.2)
        user.PostMessageW(handle,0x100,32,0);user.PostMessageW(handle,0x101,32,0)
        killed=wait(lambda r:r['score']==1000)
        assert killed['requests']>=2 and killed['nonzeroFrames']>0,killed
        # Movement and focus pause use real production input publication.
        origin=records[-1]['z'];user.PostMessageW(handle,0x100,ord('W'),0)
        wait(lambda r:r['z']<origin-1);user.SendMessageW(handle,8,0,0)
        wait(lambda r:not r['focused']);position=(records[-1]['x'],records[-1]['z']);time.sleep(.25)
        assert (records[-1]['x'],records[-1]['z'])==position
        user.SendMessageW(handle,7,0,0);wait(lambda r:r['focused'])
        capture_owned_window(p.pid,output/'probe.png',resize=True)
        close_windows(p.pid);assert p.wait(timeout=20)==0
    finally:
        stop.set()
        if audio.ident:audio.join(timeout=5)
        if p.poll() is None:close_windows(p.pid);p.wait(timeout=20)
        (output/'probe.log').write_text(''.join(logs))
    assert captured,'No WASAPI capture'
    samples=np.concatenate(captured);peak=float(np.max(np.abs(samples)));assert peak>.0001,peak
    with wave.open(str(output/'output.wav'),'wb') as wav:
        wav.setparams((2,2,48000,0,'NONE','not compressed'));wav.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
    # Production screenshot comes from the executable without the observer.
    with (output/'production.log').open('w') as log:
        prod=subprocess.Popen([str(delivery/'NauDemoMain.exe')],cwd=delivery.parent,stdout=log,stderr=log)
        try:time.sleep(2);capture_owned_window(prod.pid,output/'production.png')
        finally:close_windows(prod.pid);assert prod.wait(timeout=20)==0
    # Deterministic scene setup affects the real scene, then real hostile combat reaches game over.
    late=subprocess.Popen([str(delivery/'NauBattlezoneProbe.exe'),'last-life'],cwd=delivery.parent,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    late_records=[];late_logs=[]
    def later():
        for line in late.stdout:
            late_logs.append(line)
            if line.startswith('BATTLEZONE_PROBE '):late_records.append(json.loads(line[17:]))
    threading.Thread(target=later,daemon=True).start()
    try:
        deadline=time.monotonic()+10
        while not late_records:
            assert time.monotonic()<deadline;time.sleep(.02)
        handle=json.loads(subprocess.check_output(['orca','computer','list-windows','--app',f'pid:{late.pid}','--json'],text=True))['result']['windows'][0]['id']
        user.SendMessageW(handle,7,0,0)
        deadline=time.monotonic()+20
        while not late_records or late_records[-1]['lives']:
            assert late.poll() is None and time.monotonic()<deadline,late_logs[-10:];time.sleep(.05)
        capture_owned_window(late.pid,output/'game-over.png')
        handle=json.loads(subprocess.check_output(['orca','computer','list-windows','--app',f'pid:{late.pid}','--json'],text=True))['result']['windows'][0]['id']
        user.PostMessageW(handle,0x100,ord('R'),0);user.PostMessageW(handle,0x101,ord('R'),0)
        deadline=time.monotonic()+5
        while late_records[-1]['lives']!=3: assert time.monotonic()<deadline;time.sleep(.02)
    finally:close_windows(late.pid);assert late.wait(timeout=20)==0;(output/'last-life.log').write_text(''.join(late_logs))
    failures=[]
    for mode in ('invalid-vector','capacity','init-error','shader-error','upload-error','submit-error','stop-startup','stop','remove'):
        completed=subprocess.run([str(delivery/'NauBattlezoneProbe.exe'),mode],cwd=delivery.parent,capture_output=True,text=True,timeout=25)
        text=completed.stdout+completed.stderr;(output/(mode+'.log')).write_text(text)
        assert (completed.returncode==0)==(mode in ('stop','stop-startup','remove')),text[-3000:]
        if mode=='remove':assert '"vectors":0' in text
        assert 'presentation cleanup complete' in text,text[-3000:]
        failures.append(mode)
    archive_path=delivery/'content.nau_pack';archive=archive_path.read_bytes()
    for mode in ('missing-game','corrupt-game','missing-sound','corrupt-sound'):
        archive_path.write_bytes(mutate_required(archive,mode))
        completed=subprocess.run([str(delivery/'NauDemoMain.exe')],cwd=delivery.parent,capture_output=True,text=True,timeout=25)
        message=completed.stdout+completed.stderr
        assert completed.returncode!=0,message[-2000:]
        assert ('battlezone.json' if 'game' in mode else 'fire.wav') in message,message[-2000:]
        (output/(mode+'.log')).write_text(message);failures.append(mode)
    archive_path.write_bytes(archive)
    return dict(outputPeak=peak,score=killed['score'],focusPause=True,restart=True,failures=failures,image=image_check(output/'production.png'))


def web(delivery,root,output):
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(root)))
    threading.Thread(target=server.serve_forever,daemon=True).start();logs=[]
    url=f'http://127.0.0.1:{server.server_port}/relocated/nested/application'
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(channel='chrome',headless=True,args=['--enable-unsafe-swiftshader'])
            page=browser.new_page(viewport=dict(width=900,height=600))
            page.on('console',lambda message:logs.append(message.text))
            page.goto(url+'/probe.html');page.wait_for_function('Module.battlezoneProbe?.frame>3',timeout=30000)
            page.evaluate("""() => {const device=window.miniaudio.devices.find(Boolean);const analyser=device.webaudio.createAnalyser();analyser.fftSize=2048;device.scriptNode.connect(analyser);window.outputPeak=0;const data=new Float32Array(2048);window.audioTimer=setInterval(()=>{analyser.getFloatTimeDomainData(data);for(const v of data)window.outputPeak=Math.max(window.outputPeak,Math.abs(v));},5);} """)
            host=page.locator('#nau-window');host.focus();page.keyboard.press('Space')
            page.wait_for_function('Module.battlezoneProbe.score===1000 && window.outputPeak>.001',timeout=15000)
            killed=page.evaluate('Module.battlezoneProbe');assert killed['requests']>=2,killed
            start=page.evaluate('Module.battlezoneProbe.z');page.keyboard.down('w')
            page.wait_for_function(f'Module.battlezoneProbe.z<{start-1}')
            page.evaluate("document.querySelector('#nau-window').blur()")
            page.wait_for_function('!Module.battlezoneProbe.focused');position=page.evaluate('[Module.battlezoneProbe.x,Module.battlezoneProbe.z]')
            page.wait_for_timeout(250);assert page.evaluate('[Module.battlezoneProbe.x,Module.battlezoneProbe.z]')==position
            host.focus();page.keyboard.up('w');page.keyboard.down('d');page.wait_for_timeout(250);page.keyboard.up('d')
            assert page.evaluate('Module.battlezoneProbe.heading')>.1
            for size in ((420,680),(1000,420),(900,600)):page.set_viewport_size(dict(width=size[0],height=size[1]));page.wait_for_timeout(100)
            page.evaluate("document.querySelector('#nau-window').style.display='none'");page.wait_for_timeout(100)
            page.evaluate("document.querySelector('#nau-window').style.display=''");page.wait_for_timeout(100)
            page.locator('#canvas').screenshot(path=str(output/'probe.png'))
            peak=page.evaluate('window.outputPeak');assert peak>.001
            page.evaluate('Module.nauRuntime.stop();Module.nauRuntime.stop()');page.wait_for_function('Module.nauRuntime.status.cleanupComplete')
            # The untouched production executable supplies independent visible evidence.
            production=browser.new_page(viewport=dict(width=900,height=600));production.goto(url+'/index.html')
            production.wait_for_function("Module.nauRuntime?.status?.state==='Running'",timeout=30000)
            production.locator('#canvas').screenshot(path=str(output/'production.png'))
            production.evaluate('Module.nauRuntime.stop()');production.wait_for_function('Module.nauRuntime.status.cleanupComplete')
            late=browser.new_page();late.goto(url+'/last-life.html');late.wait_for_function('Module.battlezoneProbe?.frame>3',timeout=30000)
            late.locator('#nau-window').focus();late.wait_for_function('Module.battlezoneProbe.lives===0',timeout=20000)
            late.locator('#canvas').screenshot(path=str(output/'game-over.png'));late.keyboard.press('r');late.wait_for_function('Module.battlezoneProbe.lives===3')
            late.evaluate('Module.nauRuntime.stop()');late.wait_for_function('Module.nauRuntime.status.cleanupComplete')
            for mode in ('invalid-vector','capacity','init-error','shader-error','upload-error','submit-error','stop-startup','stop','context-loss'):
                test=browser.new_page();test.goto(url+'/'+mode+'.html')
                test.wait_for_function('Module.nauRuntime?.status?.cleanupComplete',timeout=30000)
                state=test.evaluate('Module.nauRuntime.status.state');assert state==('Stopped' if mode in ('stop','stop-startup') else 'Failed'),(mode,state)
                test.close()
            archive=(delivery/'NauDemoMain.data').read_bytes()
            for mode in ('missing-game','corrupt-game','missing-sound','corrupt-sound'):
                test=browser.new_page();data=mutate_required(archive,mode)
                test.route('**/NauDemoMain.data',lambda route:route.fulfill(body=data,content_type='application/octet-stream',headers={'Cross-Origin-Resource-Policy':'same-origin'}))
                test.goto(url+'/index.html');test.wait_for_function('Module.nauRuntime?.status?.cleanupComplete',timeout=30000)
                assert test.evaluate('Module.nauRuntime.status.state')=='Failed',mode
                test.close()
            removed=browser.new_page();removed.goto(url+'/remove.html')
            removed.wait_for_function('Module.battlezoneProbe?.frame>3 && Module.battlezoneProbe.vectors===0',timeout=30000)
            removed.evaluate('Module.nauRuntime.stop()');removed.wait_for_function('Module.nauRuntime.status.cleanupComplete')
            blocked=browser.new_page();blocked.goto(url+'/probe.html');blocked.wait_for_function('Module.battlezoneProbe?.frame>3',timeout=30000)
            blocked.evaluate("""async()=>{const b=[...Module.nauAudioBindings.values()][0];await b.context.suspend();window.realResume=b.context.resume.bind(b.context);b.context.resume=()=>new Promise(resolve=>window.resolveActivation=resolve);} """)
            blocked.locator('#nau-window').focus();blocked.keyboard.press('Space');blocked.wait_for_function('Module.battlezoneProbe.requests===1')
            blocked.evaluate("document.querySelector('#nau-window').blur();window.resolveActivation()")
            blocked.wait_for_timeout(150);assert blocked.evaluate('Module.battlezoneProbe.started')==0
            blocked.evaluate("[...Module.nauAudioBindings.values()][0].context.resume=window.realResume")
            blocked.locator('#nau-window').focus();blocked.wait_for_timeout(500);blocked.keyboard.press('Space')
            blocked.wait_for_function('Module.battlezoneProbe.started>=1',timeout=15000)
            blocked.evaluate('Module.nauRuntime.stop();Module.nauRuntime.stop()');blocked.wait_for_function('Module.nauRuntime.status.cleanupComplete')
            assert blocked.evaluate('Module.nauAudioBindings.size')==0
            browser.close()
        return dict(outputPeak=peak,score=killed['score'],focusPause=True,restart=True,resize=True,image=image_check(output/'production.png'))
    finally:(output/'runtime.log').write_text('\n'.join(logs));server.shutdown();server.server_close()


def verify(platform,configuration):
    project=pathlib.Path(__file__).resolve().parents[1];build=project/'build/basic-rendering-scene'/f'{platform.lower()}-{configuration.lower()}'
    output=build.parent/f'battlezone-{platform.lower()}-{configuration.lower()}';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nau-battlezone-') as temporary:
        root=pathlib.Path(temporary);delivery=root/'relocated/nested/application';shutil.copytree(build/'battlezone-probe-package',delivery)
        # Merge only the production executable/loader; both packages must carry identical content.
        archive=(build/'package'/('content.nau_pack' if platform=='Windows' else 'NauDemoMain.data')).read_bytes()
        probe_archive=(delivery/('content.nau_pack' if platform=='Windows' else 'NauBattlezoneProbe.data')).read_bytes()
        assert archive==probe_archive
        for source in (build/'package').iterdir():
            if source.name!='content.nau_pack':shutil.copy2(source,delivery/source.name)
        if platform=='Web':
            probe=(build/'battlezone-probe-package/index.html').read_text();(delivery/'probe.html').write_text(probe)
            for mode in ('last-life','invalid-vector','capacity','init-error','shader-error','upload-error','submit-error','stop-startup','stop','remove','context-loss'):
                (delivery/(mode+'.html')).write_text(probe.replace('window.Module = {','window.Module = { arguments: '+json.dumps([mode])+','))
        result=native(delivery,output) if platform=='Windows' else web(delivery,root,output)
        result.update(platform=platform,configuration=configuration,passed=True,archive=hashlib.sha256(archive).hexdigest())
        (output/'results.json').write_text(json.dumps(result,indent=2));print('PASS',platform,configuration)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--platform',choices=['Windows','Web'],required=True);parser.add_argument('--configuration',choices=['Debug','Release'],required=True)
    args=parser.parse_args();verify(args.platform,args.configuration)

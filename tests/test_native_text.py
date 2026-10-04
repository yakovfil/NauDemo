"""Capture the native client surface and compare it with font-derived coverage."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from PIL import Image, ImageChops

demo = Path(__file__).resolve().parents[1]
user = ctypes.windll.user32
user.SetProcessDPIAware()
references = demo/'build/text-tests-native/fixtures'
output = demo/'build/native-text-acceptance'
output.mkdir(parents=True, exist_ok=True)
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


def window_for(pid):
    found=[]
    @callback_type
    def visit(hwnd, _):
        owner=wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and user.IsWindowVisible(hwnd): found.append(hwnd)
        return True
    user.EnumWindows(visit,0)
    return found[0] if found else None


def run(config, name, settings, resized=False):
    environment=os.environ.copy();environment['NAU_DEMO_FREEZE']='1';environment.update(settings)
    log=output/f'{config}-{name}.log'
    rendered=output/f'{config}-{name}.ppm'
    rendered.unlink(missing_ok=True)
    environment['NAU_SCREEN_TEXT_CAPTURE']=str(rendered)
    with log.open('w',encoding='utf-8') as stream:
        process=subprocess.Popen([str(demo/'bin'/config/'NauDemo.exe')],cwd=demo,env=environment,stdout=stream,stderr=subprocess.STDOUT)
        hwnd=None
        try:
            deadline=time.monotonic()+20
            while time.monotonic()<deadline and process.poll() is None:
                hwnd=window_for(process.pid)
                if hwnd: break
                time.sleep(.05)
            assert hwnd, f'No native window: {log}'
            deadline=time.monotonic()+30
            while 'NauDemo text ready' not in log.read_text(encoding='utf-8',errors='replace'):
                assert time.monotonic()<deadline and process.poll() is None, f'Text never became ready: {log}'
                time.sleep(.1)
            if resized:
                user.MoveWindow(hwnd,10,10,640,480,True)
                time.sleep(.5)
            deadline=time.monotonic()+20
            while not rendered.exists() or rendered.stat().st_size<1000:
                assert time.monotonic()<deadline, f'No framebuffer readback: {log}'
                time.sleep(.1)
            time.sleep(.2)
            image=Image.open(rendered).convert('RGB')
            image.save(output/f'{config}-{name}.png')
        finally:
            if hwnd: user.PostMessageW(hwnd,0x10,0,0)
            try: code=process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=5)
                raise AssertionError(f'Native close timed out: {log}')
        assert code==0, f'Native exit {code}: {log}'
    contents=log.read_text(encoding='utf-8',errors='replace')
    return image, {'exitCode':code,'log':str(log),'shutdownComplete':'Graphics shutdown completed' in contents,
                   'existingValidationErrors':[line for line in contents.splitlines() if '[Critical]' in line or '[Error]' in line],
                   'textRelease':[line for line in contents.splitlines() if 'Screen text releasing' in line]}


def compare(image, baseline, variant=0, color=(1,1,1,1), position=(24,24)):
    stem='text-reference-1'+(f'-variant{variant}' if variant else '')
    metadata=json.loads((references/(stem+'.json')).read_text())
    coverage=(references/(stem+'.raw')).read_bytes()
    errors=[];visible=0
    for y in range(metadata['height']):
        for x in range(metadata['width']):
            point=(position[0]+metadata['left']+x,position[1]+metadata['top']+y)
            if not(0<=point[0]<image.width and 0<=point[1]<image.height):continue
            alpha=coverage[y*metadata['width']+x]/255*color[3]
            background=baseline.getpixel(point)
            expected=[round(c*(1-alpha)+255*tint*alpha) for c,tint in zip(background,color)]
            actual=image.getpixel(point)
            errors.append(max(abs(a-b) for a,b in zip(actual,expected)));visible+=alpha>0
    assert visible>20
    assert max(errors)<=4, f'Native font pixels differ: max {max(errors)}, mean {sum(errors)/len(errors)}'
    difference=ImageChops.difference(image,baseline)
    left=position[0]+metadata['left'];top=position[1]+metadata['top']
    from PIL import ImageDraw
    ImageDraw.Draw(difference).rectangle((left,top,left+metadata['width']-1,top+metadata['height']-1),fill=0)
    outside=max(max(pixel) for pixel in difference.get_flattened_data())
    assert outside<=4, f'Scene changed outside glyph rectangle: {outside}'
    return {'visibleGlyphPixels':visible,'maximumError':max(errors),'outsideMaximumError':outside}


def main():
    results=[]
    alternate=demo/'assets/fonts/Abel-Changed.ttf'
    assert not alternate.exists()
    shutil.copy2(references/'Abel-Changed.ttf',alternate)
    try:
        for config in ('Debug','Release'):
            baseline,blank=run(config,'blank',{'NAU_DEMO_TEXT':''})
            for name,settings,variant,color,position in (
                ('default',{},0,(1,1,1,1),(24,24)),
                ('variant',{'NAU_DEMO_TEXT':'Glyph AVjgy','NAU_DEMO_TEXT_SIZE':'32','NAU_DEMO_TEXT_R':'.25','NAU_DEMO_TEXT_G':'.75','NAU_DEMO_TEXT_B':'.5','NAU_DEMO_TEXT_A':'.6'},1,(.25,.75,.5,.6),(24,24)),
                ('font',{'NAU_DEMO_TEXT_FONT':'/demo/fonts/Abel-Changed.ttf'},2,(1,1,1,1),(24,24)),
                ('clipped',{'NAU_DEMO_TEXT_X':'-20','NAU_DEMO_TEXT_Y':'-5'},0,(1,1,1,1),(-20,-5))):
                image,result=run(config,name,settings)
                result.update(configuration=config,case=name,pixels=compare(image,baseline,variant,color,position))
                results.append(result)
            resized_blank,_=run(config,'resized-blank',{'NAU_DEMO_TEXT':''},True)
            resized,result=run(config,'resized',{},True)
            result.update(configuration=config,case='resize',pixels=compare(resized,resized_blank))
            results.append(result)
            # Compare the pre-existing renderer diagnostics separately from text.
            results.append({'configuration':config,'case':'baseline','diagnostics':blank})
            failure_log=output/f'{config}-missing-font.log'
            environment=os.environ.copy();environment['NAU_DEMO_TEXT_FONT']='/demo/fonts/missing.ttf'
            with failure_log.open('w') as stream:
                failure=subprocess.run([str(demo/'bin'/config/'NauDemo.exe')],cwd=demo,env=environment,
                    stdout=stream,stderr=subprocess.STDOUT,timeout=20)
            diagnostic=failure_log.read_text(errors='replace')
            assert failure.returncode==1 and '/demo/fonts/missing.ttf' in diagnostic
            assert 'NauDemo text ready' not in diagnostic
            results.append({'configuration':config,'case':'missing-font','exitCode':failure.returncode,'assetError':True})
        (output/'results.json').write_text(json.dumps({'passed':True,'results':results},indent=2))
    except Exception as error:
        (output/'results.json').write_text(json.dumps({'passed':False,'error':str(error),'results':results},indent=2))
        raise
    finally:
        alternate.unlink()


if __name__=='__main__': main()

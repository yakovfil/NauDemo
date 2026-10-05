"""Validate native demo startup, presentation, resize and orderly host teardown."""
import ctypes, json, os, pathlib, shutil, subprocess, time
from ctypes import wintypes
from PIL import Image, ImageChops
root=pathlib.Path(__file__).resolve().parents[1]
output=root/'build/common-host-native-demo/acceptance';output.mkdir(exist_ok=True)
user=ctypes.windll.user32
user.SetProcessDPIAware()
callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
user.MoveWindow.argtypes=(wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.BOOL)
user.PostMessageW.argtypes=(wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)

def find_window(pid):
    found=[]
    @callback
    def visit(hwnd,_):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        title=ctypes.create_unicode_buffer(256);user.GetWindowTextW(hwnd,title,256)
        if owner.value==pid and title.value=='Nau Demo - Rotating Cube':found.append(hwnd)
        return True
    user.EnumWindows(visit,0)
    return found[0] if found else None

def capture(process,window,name):
    command=['orca','computer','get-app-state','--app',f'pid:{process.pid}','--window-id',str(window),'--restore-window','--json']
    result=json.loads(subprocess.check_output(command,text=True,timeout=25))
    assert result['ok'],result
    assert result['result']['snapshot']['app']['pid']==process.pid,result
    destination=output/name;shutil.copyfile(result['result']['screenshot']['path'],destination)
    image=Image.open(destination).convert('RGB')
    blue=sum(b>60 and b>r*1.3 and b>g*.9 for r,g,b in image.get_flattened_data())
    assert blue>image.width*image.height*.01,'Missing blue cube'
    return image,result['result']['snapshot']['window']

checks=[]
for config in ('Debug','Release'):
    executable=root/f'bin/{config}/NauDemo.exe'
    log=output/f'{config}.log'
    with log.open('w') as stream:
        process=subprocess.Popen([str(executable)],cwd=root,stdout=stream,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+25
            while 'NauDemo text ready' not in log.read_text(errors='replace'):
                assert process.poll() is None,log.read_text(errors='replace')[-1000:]
                assert time.monotonic()<deadline,'Native startup did not complete'
                time.sleep(.05)
            window=find_window(process.pid);assert window
            first,_=capture(process,window,f'{config}-first.png');time.sleep(.5)
            second,_=capture(process,window,f'{config}-rotated.png')
            region=(first.width//4,first.height//4,first.width*3//4,first.height*3//4)
            assert ImageChops.difference(first.crop(region),second.crop(region)).getbbox(),'Rotation did not change cube pixels'
            label=first.crop((5,30,first.width//4,100))
            assert sum(min(rgb)>180 and max(rgb)-min(rgb)<10 for rgb in label.get_flattened_data())>20,'Missing label pixels'
            user.MoveWindow(window,10,10,900,600,True);time.sleep(.3)
            resized,geometry=capture(process,window,f'{config}-resized.png')
            assert geometry['width']==900 and geometry['height']==600,geometry
            user.PostMessageW(window,0x0010,0,0)
            code=process.wait(timeout=20);assert code==0,code
            checks.append(dict(configuration=config,scenario='presentation-resize-close',exitCode=code,passed=True))
        finally:
            if process.poll() is None:
                window=find_window(process.pid)
                if window:user.PostMessageW(window,0x0010,0,0)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
    env=os.environ.copy();env['NAU_DEMO_TEXT_FONT']='/demo/fonts/Missing.ttf'
    failure=subprocess.run([str(executable)],cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=25)
    (output/f'{config}-missing-font.log').write_text(failure.stdout)
    assert failure.returncode!=0 and 'Missing.ttf' in failure.stdout,failure.stdout[-1000:]
    assert 'Executor must be specified' not in failure.stdout
    assert 'application completion is blocked' not in failure.stdout
    checks.append(dict(configuration=config,scenario='missing-font',exitCode=failure.returncode,passed=True))
    print(config,'PASS',flush=True)
    (output/'results.json').write_text(json.dumps(checks,indent=2))

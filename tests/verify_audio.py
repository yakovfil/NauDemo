"""Verify focused click feedback and capture production output on Windows/web."""
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
from playwright.sync_api import sync_playwright
from verify_web_startup import Handler
from verify_native_startup import close_windows


def mutate_audio(raw, mode):
    if mode == 'missing':
        assert b'audio/click.wav' in raw
        return raw.replace(b'audio/click.wav', b'audio/missi.wav', 1)
    separator = raw.index(b'\n\n\n') + 3
    length = int(next(line.split(b':', 1)[1] for line in raw[:separator].splitlines() if line.startswith(b'Content-Length:')))
    header = json.loads(raw[separator:separator+length])
    entry = next(item for item in header['content'] if item['filePath'] == 'audio/click.wav')
    data = bytearray(raw)
    data[separator+length+entry['blobData']['offset']+34] = 32
    return bytes(data)


def native(delivery, output):
    import numpy as np
    import soundcard as sc
    logs, records, captured = [], [], []
    process = subprocess.Popen([str(delivery / "NauDemoInputProbe.exe")], cwd=delivery.parent,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    def reader():
        for line in process.stdout:
            logs.append(line)
            if line.startswith("INPUT_PROBE "):
                records.append(json.loads(line[12:]))
    threading.Thread(target=reader, daemon=True).start()
    def wait(predicate):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if records and predicate(records[-1]):
                return records[-1]
            assert process.poll() is None, ''.join(logs[-20:])
            time.sleep(.01)
        raise AssertionError('Audio timeout: ' + ''.join(logs[-15:]))
    stop_capture = threading.Event()
    def capture():
        microphone = sc.get_microphone(sc.default_speaker().id, include_loopback=True)
        with microphone.recorder(samplerate=48000, channels=2, blocksize=480) as recorder:
            while not stop_capture.is_set():
                captured.append(recorder.record(numframes=480))
    capture_thread = threading.Thread(target=capture, daemon=True)
    try:
        wait(lambda r: r['frame'] > 3)
        user = ctypes.WinDLL('user32')
        windows = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def window(handle, _):
            pid = ctypes.c_ulong()
            user.GetWindowThreadProcessId(ctypes.c_void_p(handle), ctypes.byref(pid))
            if pid.value == process.pid and user.IsWindowVisible(ctypes.c_void_p(handle)):
                windows.append(handle)
            return True
        user.EnumWindows(callback_type(window), 0)
        assert len(windows) == 1, windows
        handle = windows[0]
        user.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        user.SendMessageW.argtypes = user.PostMessageW.argtypes
        def send(message, value=0, point=0):
            assert user.PostMessageW(handle, message, value, point)
        capture_thread.start()
        time.sleep(.2)
        baseline = records[-1]['audio']['requests']
        tested = []
        for key in 'WASDQE':
            count = records[-1]['audio']['requests']
            send(0x100, ord(key)); wait(lambda r: r['audio']['requests'] == count + 1)
            for _ in range(4): send(0x100, ord(key), 1 << 30)
            time.sleep(.12)
            assert records[-1]['audio']['requests'] == count + 1
            send(0x101, ord(key)); wait(lambda r: not any(r['held']))
            tested.append(key)
        for down, up, value, name in ((0x201, 0x202, 1, 'left'), (0x207, 0x208, 16, 'middle'), (0x204, 0x205, 2, 'right')):
            count = records[-1]['audio']['requests']
            send(down, value, (200 << 16) | 300); send(up, 0, (200 << 16) | 300)
            wait(lambda r: r['audio']['requests'] == count + 1)
            time.sleep(.12)
            tested.append(name)
        assert records[-1]['audio']['requests'] == baseline + 9
        count = records[-1]['audio']['requests']
        send(0x100, ord('W')); send(0x101, ord('W'))
        wait(lambda r: r['audio']['requests'] == count+1)
        count = records[-1]['audio']['requests']
        for key in 'WA': send(0x100, ord(key))
        send(0x201, 1, (200 << 16) | 300)
        wait(lambda r: r['audio']['requests'] == count+3)
        for key in 'WA': send(0x101, ord(key))
        send(0x202, 0, (200 << 16) | 300)
        wait(lambda r: not any(r['held']) and not any(r['buttons']))
        count = records[-1]['audio']['requests']
        for _ in range(100):
            send(0x207, 16, (200 << 16) | 300); send(0x208, 0, (200 << 16) | 300)
        time.sleep(.25)
        assert 0 < records[-1]['audio']['requests']-count <= 100
        assert records[-1]['audio']['active'] <= 16 and records[-1]['audio']['pending'] <= 9
        count = records[-1]['audio']['requests']
        send(0x100, ord('X')); send(0x101, ord('X')); time.sleep(.15)
        assert records[-1]['audio']['requests'] == count
        # Cancellation before the queued update must not replay the pending tap.
        user.SendMessageW(handle, 0x8, 0, 0)
        time.sleep(.15)
        send(0x100, ord('W'), 1 << 30)
        time.sleep(.12)
        assert records[-1]['audio']['requests'] == count and not any(records[-1]['held'])
        last = records[-1]
        assert last['audio']['nonzeroFrames'] > 0 and last['audio']['peak'] > .001
        user.SendMessageW(handle, 0x7, 0, 0)
        send(0x100, ord('W'))
        wait(lambda r: r['audio']['active'] > 0)
        close_windows(process.pid)
        assert process.wait(timeout=20) == 0
        stop_capture.set(); capture_thread.join(timeout=5)
        samples = np.concatenate(captured)
        peak = float(np.max(np.abs(samples)))
        assert peak > .0001, f'WASAPI output is silent: {peak}'
        with wave.open(str(output / 'output.wav'), 'wb') as destination:
            destination.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            destination.writeframes((np.clip(samples, -1, 1)*32767).astype('<i2').tobytes())
        archive_path = delivery / 'content.nau_pack'
        archive = archive_path.read_bytes()
        failures = []
        for mode in ('missing', 'corrupt'):
            archive_path.write_bytes(mutate_audio(archive, mode))
            completed = subprocess.run([str(delivery / 'NauDemoInputProbe.exe')], cwd=delivery.parent, capture_output=True, text=True, timeout=25)
            text = completed.stdout + completed.stderr
            assert completed.returncode != 0 and 'audio/click.wav' in text, text
            (output / (mode+'.log')).write_text(text)
            failures.append(mode)
        archive_path.write_bytes(archive)
        return dict(tested=tested, final=last, capturePeak=peak, stopped=True, assetFailures=failures)
    finally:
        stop_capture.set()
        if process.poll() is None:
            close_windows(process.pid)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill()
        (output / 'runtime.log').write_text(''.join(logs))


def web(delivery, root, output):
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logs, results = [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for first in ('keyboard', 'mouse'):
                context = browser.new_context()
                page = context.new_page()
                page.on('console', lambda message: logs.append(message.text))
                page.on('pageerror', lambda error: logs.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html')
                page.wait_for_function('Module.inputProbe?.frame > 3', timeout=30000)
                page.evaluate("""() => {
                    const device = window.miniaudio.devices.find(Boolean);
                    const analyser = device.webaudio.createAnalyser();
                    analyser.fftSize = 2048;
                    device.scriptNode.connect(analyser);
                    window.outputPeak = 0;
                    const data = new Float32Array(2048);
                    window.audioTimer = setInterval(() => {
                        analyser.getFloatTimeDomainData(data);
                        for(const value of data) window.outputPeak = Math.max(window.outputPeak, Math.abs(value));
                    }, 5);
                }""")
                host = page.locator('#nau-window')
                host.focus()
                initial = page.evaluate('Module.inputProbe.audio')
                assert initial['requests'] == 0, initial
                if first == 'keyboard': page.keyboard.press('w')
                else: host.click(position=dict(x=200, y=150))
                page.wait_for_function('Module.inputProbe.audio.started === 1 && window.outputPeak > .001', timeout=15000)
                page.wait_for_timeout(150)
                tested = []
                for key in 'wasdqe':
                    count = page.evaluate('Module.inputProbe.audio.requests')
                    page.keyboard.down(key)
                    page.wait_for_function('Module.inputProbe.audio.requests === ' + str(count+1))
                    for _ in range(3): page.keyboard.down(key)
                    page.wait_for_timeout(120)
                    assert page.evaluate('Module.inputProbe.audio.requests') == count+1
                    page.keyboard.up(key)
                    tested.append(key)
                for button in ('left', 'middle', 'right'):
                    count = page.evaluate('Module.inputProbe.audio.requests')
                    host.click(button=button, position=dict(x=200, y=150))
                    page.wait_for_function('Module.inputProbe.audio.requests === ' + str(count+1))
                    page.wait_for_timeout(120)
                    tested.append(button)
                count = page.evaluate('Module.inputProbe.audio.requests')
                page.mouse.down(button='left'); page.mouse.down(button='right')
                page.wait_for_function('Module.inputProbe.audio.requests === ' + str(count+2))
                page.mouse.up(button='right'); page.mouse.up(button='left')
                page.wait_for_function('!Module.inputProbe.buttons.some(Boolean)')
                count = page.evaluate('Module.inputProbe.audio.requests')
                page.keyboard.down('w'); page.keyboard.down('a'); page.mouse.down()
                page.wait_for_function('Module.inputProbe.audio.requests === ' + str(count+3))
                page.keyboard.up('w'); page.keyboard.up('a'); page.mouse.up()
                count = page.evaluate('Module.inputProbe.audio.requests')
                page.evaluate("""() => {
                    const host = document.querySelector('#nau-window');
                    for(let i=0; i<100; ++i) {
                        host.dispatchEvent(new KeyboardEvent('keydown', {code:'KeyE'}));
                        host.dispatchEvent(new KeyboardEvent('keyup', {code:'KeyE'}));
                    }
                }""")
                page.wait_for_timeout(200)
                rapid = page.evaluate('Module.inputProbe.audio')
                assert 0 < rapid['requests']-count <= 100 and rapid['active'] <= 16 and rapid['pending'] <= 9
                count = page.evaluate('Module.inputProbe.audio.requests')
                page.keyboard.press('x'); page.mouse.wheel(0, 10); page.wait_for_timeout(120)
                assert page.evaluate('Module.inputProbe.audio.requests') == count
                page.evaluate("document.querySelector('#nau-window').blur()")
                page.keyboard.press('w'); page.wait_for_timeout(120)
                assert page.evaluate('Module.inputProbe.audio.requests') == count
                final = page.evaluate('Module.inputProbe.audio')
                peak = page.evaluate('window.outputPeak')
                assert final['nonzeroFrames'] > 0 and peak > .001
                host.focus()
                page.keyboard.down('a')
                page.wait_for_function('Module.inputProbe.audio.active > 0')
                page.evaluate('Module.nauRuntime.stop(); Module.nauRuntime.stop()')
                page.wait_for_function("Module.nauRuntime.status.state === 'Stopped'", timeout=20000)
                assert page.evaluate('Module.nauAudioBindings.size') == 0
                page.evaluate('clearInterval(window.audioTimer)')
                results.append(dict(first=first, tested=tested, final=final, outputPeak=peak, stopped=True))
                context.close()
            # Exercise failures and activation cancellation through the production path.
            context = browser.new_context()
            page = context.new_page()
            page.on('console', lambda message: logs.append(message.text))
            page.goto(f'http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html')
            page.wait_for_function('Module.inputProbe?.frame > 3', timeout=30000)
            page.locator('#nau-window').focus()
            page.evaluate("""async () => {
                const binding = [...Module.nauAudioBindings.values()][0];
                await binding.context.suspend();
                binding.originalResume = binding.context.resume.bind(binding.context);
                binding.context.resume = () => Promise.reject(new Error('Injected blocked activation'));
            }""")
            page.keyboard.press('w')
            page.wait_for_timeout(1200)
            blocked = page.evaluate('Module.inputProbe.audio')
            assert blocked['started'] == 0 and blocked['pending'] == 0, blocked
            page.evaluate("""() => {
                const binding = [...Module.nauAudioBindings.values()][0];
                binding.context.resume = binding.originalResume;
            }""")
            page.keyboard.press('a')
            page.wait_for_function('Module.inputProbe.audio.started === 1 && Module.inputProbe.audio.nonzeroFrames > 0')
            # Closed output must become an observable terminal device failure.
            page.evaluate('async () => await [...Module.nauAudioBindings.values()][0].context.close()')
            page.wait_for_function("Module.nauRuntime.status.state === 'Failed'", timeout=20000)
            page.wait_for_function('Module.nauAudioBindings.size === 0', timeout=20000)
            assert page.evaluate('Module.nauAudioBindings.size') == 0
            results.append(dict(blockedActivation=blocked, deviceFailure=True))
            context.close()
            context = browser.new_context()
            page = context.new_page()
            page.on('console', lambda message: logs.append(message.text))
            page.goto(f'http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html')
            page.wait_for_function('Module.inputProbe?.frame > 3', timeout=30000)
            page.locator('#nau-window').focus()
            page.evaluate("""async () => {
                const binding = [...Module.nauAudioBindings.values()][0];
                await binding.context.suspend();
                binding.context.resume = () => new Promise(resolve => { window.finishResume = resolve; });
            }""")
            page.wait_for_function('Module.inputProbe.audio.state === 1')
            page.keyboard.press('w')
            page.wait_for_function('Module.inputProbe.audio.pending === 1')
            page.evaluate("document.querySelector('#nau-window').blur()")
            page.wait_for_function('Module.inputProbe.audio.pending === 0')
            assert page.evaluate('Module.inputProbe.audio.started') == 0
            page.locator('#nau-window').focus()
            page.evaluate('window.finishResume(); delete window.finishResume')
            page.keyboard.press('a')
            page.wait_for_function('Module.inputProbe.audio.pending === 1')
            page.evaluate('Module.nauRuntime.stop(); Module.nauRuntime.stop()')
            page.wait_for_function("Module.nauRuntime.status.state === 'Stopped'", timeout=20000)
            page.evaluate('window.finishResume()')
            assert page.evaluate('Module.nauAudioBindings.size') == 0
            results.append(dict(delayedFocusCancellation=True, stopDuringActivation=True))
            context.close()
            for failure in ('device', 'binding'):
                context = browser.new_context()
                page = context.new_page()
                page.on('console', lambda message: logs.append(message.text))
                if failure == 'device':
                    page.add_init_script("window.AudioContext = function() { throw new Error('Injected unavailable audio device'); }; window.webkitAudioContext = undefined;")
                else:
                    page.add_init_script("""const original = HTMLElement.prototype.addEventListener;
                        HTMLElement.prototype.addEventListener = function(type, callback, options) {
                            if(this.id === 'nau-window' && type === 'pointerdown' && callback.toString().includes('context.resume'))
                                throw new Error('Injected audio binding failure');
                            return original.call(this, type, callback, options);
                        };""")
                page.goto(f'http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html')
                page.wait_for_function("Module.nauRuntime?.status?.state === 'Failed'", timeout=20000)
                page.wait_for_function('!Module.nauAudioBindings || Module.nauAudioBindings.size === 0', timeout=20000)
                diagnostic = page.evaluate('JSON.stringify(Module.nauRuntime.status)')
                assert ('output device initialization failed' if failure == 'device' else 'gesture binding failed') in diagnostic, diagnostic
                assert page.evaluate('!Module.nauAudioBindings || Module.nauAudioBindings.size === 0')
                results.append(dict(initializationFailure=failure, cleaned=True))
                context.close()
            archive = (delivery / 'NauDemoInputProbe.data').read_bytes()
            for mode in ('missing', 'corrupt'):
                context = browser.new_context()
                page = context.new_page()
                page.on('console', lambda message: logs.append(message.text))
                data = mutate_audio(archive, mode)
                assert len(data) == len(archive)
                page.route('**/NauDemoInputProbe.data', lambda route: route.fulfill(body=data, content_type='application/octet-stream', headers={'Cross-Origin-Resource-Policy':'same-origin'}))
                page.goto(f'http://127.0.0.1:{server.server_port}/relocated/nested/application/index.html')
                page.wait_for_function("Module.nauRuntime?.status?.state === 'Failed'", timeout=20000)
                page.wait_for_function('Module.nauAudioBindings.size === 0', timeout=20000)
                assert 'audio/click.wav' in page.evaluate('JSON.stringify(Module.nauRuntime.status)')
                assert page.evaluate('Module.nauAudioBindings.size') == 0
                results.append(dict(assetFailure=mode, cleaned=True))
                context.close()
            browser.close()
    finally:
        server.shutdown(); server.server_close()
        (output / 'runtime.log').write_text('\n'.join(logs))
    return results


def verify(platform, configuration):
    project = pathlib.Path(__file__).resolve().parents[1]
    build = project / 'build/basic-rendering-scene' / (platform.lower()+'-'+configuration.lower())
    output = build.parent / ('audio-'+platform.lower()+'-'+configuration.lower())
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nau-audio-') as temporary:
        root = pathlib.Path(temporary)
        delivery = root / 'relocated/nested/application'
        shutil.copytree(build / 'input-probe-package', delivery)
        results = web(delivery, root, output) if platform == 'Web' else native(delivery, output)
    archive = hashlib.sha256((build / 'selected-input/content.nau_pack').read_bytes()).hexdigest()
    (output / 'results.json').write_text(json.dumps(dict(platform=platform, configuration=configuration, archive=archive, results=results, passed=True), indent=2))
    print('PASS', platform, configuration)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('Windows', 'Web'))
    parser.add_argument('configuration', choices=('Debug', 'Release'))
    args = parser.parse_args()
    verify(args.platform, args.configuration)

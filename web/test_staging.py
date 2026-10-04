"""Check both real packages and transactional staging failure/stale-file behavior."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

demo = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build-prefix', default='web-demo-',
                    help='Directory prefix under NauDemo/build for Debug/Release packages')
args = parser.parse_args()
results = []
for configuration in ('Debug', 'Release'):
    build = demo / 'build' / f'{args.build_prefix}{configuration.lower()}'
    package = build / 'package'
    manifest = json.loads((package/'manifest.json').read_text())
    assert manifest['configuration'] == configuration
    assert {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()} == set(manifest['files']) | {'manifest.json'}
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((package/name).read_bytes()).hexdigest() == expected, name
    with tempfile.TemporaryDirectory(prefix='demo-stage-', dir=demo/'build') as scratch:
        root = Path(scratch).resolve()
        assert root.is_relative_to((demo/'build').resolve())
        command = ['cmake', f'-DBUILD_ROOT={root}', f'-DDESTINATION={root}/package',
            f'-DLOADER={build}/bin/NauDemo.js', f'-DWASM={build}/bin/NauDemo.wasm',
            f'-DDATA={build}/bin/NauDemo.data', f'-DASSETS={demo}/web',
            f'-DMESH_ASSETS={demo}/assets', f'-DCONFIGURATION={configuration}',
            '-P', str(demo/'web/stage.cmake')]
        subprocess.run(command, check=True, capture_output=True)
        (root/'package/stale.css').write_text('stale output')
        subprocess.run(command, check=True, capture_output=True)
        assert not (root/'package/stale.css').exists()
        inventory = lambda: {p.relative_to(root/'package').as_posix():p.read_bytes() for p in (root/'package').rglob('*') if p.is_file()}
        before = inventory()
        missing = command.copy()
        missing[3] = f'-DLOADER={root}/missing.js'
        failure = subprocess.run(missing, capture_output=True, text=True)
        assert failure.returncode and 'Missing required package input' in failure.stderr
        assert before == inventory()
        for name in ('Abel-Regular.ttf', 'OFL-Abel.txt'):
            assets = root/'assets'
            (assets/'fonts').mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(demo/'assets/cube.gltf', assets/'cube.gltf')
            shutil.copy2(demo/'assets/cube.bin', assets/'cube.bin')
            for present in ('Abel-Regular.ttf', 'OFL-Abel.txt'):
                if present != name:
                    shutil.copy2(demo/'assets/fonts'/present, assets/'fonts'/present)
                elif (assets/'fonts'/present).exists():
                    (assets/'fonts'/present).unlink()
            missing_asset = [f'-DMESH_ASSETS={assets}' if v.startswith('-DMESH_ASSETS=') else v for v in command]
            failure = subprocess.run(missing_asset, capture_output=True, text=True)
            assert failure.returncode and name in failure.stderr
            assert before == inventory()
        assert not (root/'package.staging').exists()
    results.append({'configuration':configuration, 'files':manifest['files'], 'passed':True})
(demo/'build/demo-staging-results.json').write_text(json.dumps(results,indent=2))
print('Passed package hashes, exact inventory, stale removal and missing-input preservation in Debug/Release')

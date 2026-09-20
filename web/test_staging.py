"""Check both real packages and transactional staging failure/stale-file behavior."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

demo = Path(__file__).resolve().parents[1]
engine = demo.parent / 'NauEngineLite'
results = []
for configuration in ('Debug', 'Release'):
    build = engine / 'build' / f'web-demo-{configuration.lower()}'
    package = build / 'package'
    manifest = json.loads((package/'manifest.json').read_text())
    assert manifest['configuration'] == configuration
    assert set(p.name for p in package.iterdir()) == set(manifest['files']) | {'manifest.json'}
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((package/name).read_bytes()).hexdigest() == expected, name
    with tempfile.TemporaryDirectory(prefix='demo-stage-', dir=engine/'build') as scratch:
        root = Path(scratch).resolve()
        assert root.is_relative_to((engine/'build').resolve())
        command = ['cmake', f'-DBUILD_ROOT={root}', f'-DDESTINATION={root}/package',
            f'-DLOADER={build}/bin/NauDemo.js', f'-DWASM={build}/bin/NauDemo.wasm',
            f'-DDATA={build}/bin/NauDemo.data', f'-DASSETS={demo}/web',
            f'-DMESH_ASSETS={demo}/assets', f'-DCONFIGURATION={configuration}',
            '-P', str(demo/'web/stage.cmake')]
        subprocess.run(command, check=True, capture_output=True)
        (root/'package/stale.css').write_text('stale output')
        subprocess.run(command, check=True, capture_output=True)
        assert not (root/'package/stale.css').exists()
        before = {p.name:p.read_bytes() for p in (root/'package').iterdir()}
        missing = command.copy()
        missing[3] = f'-DLOADER={root}/missing.js'
        failure = subprocess.run(missing, capture_output=True, text=True)
        assert failure.returncode and 'Missing required package input' in failure.stderr
        assert before == {p.name:p.read_bytes() for p in (root/'package').iterdir()}
        assert not (root/'package.staging').exists()
    results.append({'configuration':configuration, 'files':manifest['files'], 'passed':True})
(engine/'build/demo-staging-results.json').write_text(json.dumps(results,indent=2))
print('Passed package hashes, exact inventory, stale removal and missing-input preservation in Debug/Release')

"""Run screen-text browser acceptance sequentially, retaining every result."""
import json
from pathlib import Path
import subprocess
import sys

demo=Path(__file__).resolve().parents[1]
output=demo/'build/text-browser-acceptance'
output.mkdir(parents=True,exist_ok=True)
results=[]
for config in ('Debug','Release'):
    package=demo/f'build/web-demo-{config.lower()}/package'
    for scenario,variant in (('success',0),('context-loss',1),('context-loss',2),
                             ('text-upload',0),('missing-font',0),('no-context',0),
                             ('stop-assets',0),('stop-graphics',0),('pending-scene',0),('camera',0),('clipped',0)):
        name=f'{config}-{scenario}-{variant}'
        command=[sys.executable,str(demo/'web/test_package.py'),'--package',str(package),
                 '--output',str(output/name),'--base-path','/relocated/text/demo/',
                 '--scenario','context-loss' if scenario=='clipped' else scenario,'--text-variant',str(variant),'--text-readback']
        if scenario=='clipped':command+=['--text-position','-20','-10']
        with (output/(name+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        results.append({'name':name,'command':command,'exitCode':result.returncode})
        (output/'results.json').write_text(json.dumps({'passed':all(r['exitCode']==0 for r in results),'checks':results},indent=2))
        print(('PASS ' if result.returncode==0 else 'FAIL ')+name,flush=True)
        if result.returncode: raise SystemExit(result.returncode)
print('All screen-text browser acceptance checks passed.')

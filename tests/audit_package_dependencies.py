"""Audit configured target graphs for host/runtime dependency isolation."""
import json, pathlib, re, subprocess
demo=pathlib.Path(__file__).resolve().parents[1];workspace=demo.parent
cases=[('host',demo/'build/asset-pack-host',workspace/'NauEngineModules/cmake/probes/asset_pack'),
       ('minimal',workspace/'NauEngineModules/build/common-host-native',workspace/'NauEngineModules/cmake/probes/common_host')]
for config in ('debug','release'):
    cases.append(('web-'+config,demo/('build/web-demo-'+config),workspace/'NauEngineLite'))
results=[]
for kind,build,source in cases:
    query=build/'.cmake/api/v1/query';query.mkdir(parents=True,exist_ok=True)
    (query/'codemodel-v2').write_text('')
    configured=subprocess.run(['cmake','-S',str(source),'-B',str(build)],capture_output=True,text=True)
    assert configured.returncode==0,configured.stdout+configured.stderr
    reply=build/'.cmake/api/v1/reply'
    index=json.loads(max(reply.glob('index-*.json'),key=lambda path:path.stat().st_mtime).read_text())
    model=json.loads((reply/index['reply']['codemodel-v2']['jsonFile']).read_text())
    names=sorted({target['name'] for config in model['configurations'] for target in config['targets']})
    pattern=r'Graphics|^Render$|Physics|VFX|NauUi|Qt|Usd|AssetTool$'
    if kind in ('host','minimal'):pattern+=r'|CoreScene|BrowserRenderer'
    if kind=='host':pattern+=r'|Framework|PlatformApp'
    forbidden=[name for name in names if re.search(pattern,name,re.I)]
    assert not forbidden,(kind,forbidden)
    results.append({'kind':kind,'build':str(build),'targets':names,'forbidden':forbidden,'passed':True})
(demo/'build/asset-pack-dependency-audit.json').write_text(json.dumps(results,indent=2))
print('Host, minimal and browser package dependency audits passed')

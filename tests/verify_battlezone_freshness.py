"""Cook copied game assets and verify deterministic, failure-safe selection."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile


def verify(args):
    project=pathlib.Path(__file__).resolve().parents[1];checkout=project.parent
    tool=checkout/'NauEngineModules/tools/asset_tools/prepare_packaged_project.py'
    output=project/'build/basic-rendering-scene/battlezone-freshness';output.mkdir(exist_ok=True)
    environment=os.environ.copy();python=pathlib.Path(args.python).resolve();tools=pathlib.Path(args.tools).resolve();usd=pathlib.Path(args.usd).resolve()
    environment['PATH']=os.pathsep.join([str(tools),str(tools/'plugins'),str(python.parent),str(usd/'bin'),str(usd/'lib'),environment['PATH']])
    environment['PYTHONPATH']=str(usd/'lib/python');environment['PXR_PLUGINPATH_NAME']=os.pathsep.join([str(tools/'plugins'),str(usd/'plugin/usd')])
    results=[]
    with tempfile.TemporaryDirectory(prefix='nau-battlezone-freshness-') as temporary:
        source=pathlib.Path(temporary)/'project';source.mkdir()
        for name in ('content','config'):shutil.copytree(project/name,source/name)
        declaration=source/'policy.json';game_policy=(project/'portable_rendering_project.json').read_bytes();declaration.write_bytes(game_policy)
        destination=source/'build/prepared'
        command=[str(python),str(tool),'--project',str(source),'--output',str(destination),'--asset-tool',str(tools/'AssetToolCmd.exe'),'--pack-tool',str(tools/'AssetPackToolCmd.exe'),'--module',str(pathlib.Path(args.module).resolve()),'--declaration',str(declaration)]
        def prepare(name,success=True):
            before={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file() and not p.is_relative_to(source/'build')}
            completed=subprocess.run(command,env=environment,capture_output=True,text=True)
            (output/(name+'.log')).write_text(completed.stdout+completed.stderr)
            assert (completed.returncode==0)==success,completed.stdout+completed.stderr
            after={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file() and not p.is_relative_to(source/'build')}
            assert before==after
            archive=(destination/'content.nau_pack').read_bytes();results.append(dict(case=name,passed=True,archive=hashlib.sha256(archive).hexdigest()));return archive
        initial=prepare('initial');assert prepare('repeat')==initial
        geometry=source/'content/game/battlezone.json';original=geometry.read_bytes();data=json.loads(original)
        data['geometry']['tank']['vertices'][0][0]-=.1;geometry.write_text(json.dumps(data));changed=prepare('geometry-edit');assert changed!=initial
        data['geometry']['tank']['edges'].append([0,99999]);geometry.write_text(json.dumps(data));assert prepare('invalid-edge',False)==changed
        geometry.unlink();assert prepare('missing-geometry',False)==changed
        geometry.write_bytes(original);assert prepare('geometry-restore')==initial
        sound=source/'content/audio/fire.wav';original_sound=sound.read_bytes();edited=bytearray(original_sound);edited[50]^=1;sound.write_bytes(edited)
        changed=prepare('sound-edit');assert changed!=initial
        sound.unlink();assert prepare('missing-sound',False)==changed
        sound.write_bytes(b'corrupt');assert prepare('corrupt-sound',False)==changed
        sound.write_bytes(original_sound);assert prepare('sound-restore')==initial
        declaration.write_bytes((project/'portable_original_project.json').read_bytes());old=prepare('switch-original');assert old!=initial
        declaration.write_bytes(game_policy);assert prepare('switch-game')==initial
    (output/'results.json').write_text(json.dumps(results,indent=2));print('PASS',len(results),'game freshness cases')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('python','tools','usd','module'):parser.add_argument('--'+name,required=True)
    verify(parser.parse_args())

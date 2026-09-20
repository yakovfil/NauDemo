"""Fresh local Git checkouts plus an explicit source patch bundle; no commits or generated inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]
    destination = args.destination.resolve()
    assert not destination.exists(), 'Use a new destination; existing directories are never replaced'
    assert not destination.is_relative_to(source), 'Fresh checkout must be outside the original checkout'
    assert Path(os.environ['EMSDK']).resolve() == args.sdk.resolve(), 'Source the requested emsdk_env.ps1 first'
    evidence = source/'NauEngineLite/build/demo-fresh-evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    report = {'source':str(source),'checkout':str(destination),'sdk':str(args.sdk.resolve()),
              'method':'fresh local Git clones with recorded uncommitted patch bundle','repositories':{},'commands':[],'passed':False}
    def run(command, cwd, name):
        report['commands'].append({'cwd':str(cwd),'command':list(map(str,command))})
        with (evidence/(name+'.log')).open('w',encoding='utf-8') as log:
            subprocess.run(list(map(str,command)),cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
        print(name,flush=True)
    try:
        for name in ('root','NauEngineLite','NauSamples','NauDemo'):
            original = source if name=='root' else source/name
            target = destination if name=='root' else destination/name
            revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=original,text=True).strip()
            patch = subprocess.check_output(['git','diff','--binary','--ignore-submodules=all','HEAD'],cwd=original)
            patch_file = evidence/(name+'.patch')
            patch_file.write_bytes(patch)
            run(['git','clone','--no-hardlinks','--no-checkout',original,target],source,name+'-clone')
            run(['git','checkout','--detach',revision],target,name+'-checkout')
            if patch:
                run(['git','apply','--whitespace=nowarn',patch_file],target,name+'-apply')
            untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=original).decode().split('\0')
            files = {}
            for relative in filter(None,untracked):
                input_file = original/relative
                assert input_file.is_file() and input_file.resolve().is_relative_to(original.resolve())
                output_file = target/relative
                output_file.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(input_file,output_file)
                files[relative]=hashlib.sha256(input_file.read_bytes()).hexdigest()
            report['repositories'][name]={'base':revision,'patchSha256':hashlib.sha256(patch).hexdigest(),'untrackedSha256':files}
        before = {name:subprocess.check_output(['git','diff','--binary','--ignore-submodules=all','HEAD'],cwd=destination/name)
                  for name in ('NauEngineLite','NauSamples','NauDemo')}
        for executable in ('git','cmake','ninja','em++'):
            run([executable,'--version'],destination,'tool-'+executable.replace('+','p'))
        for configuration in ('debug','release'):
            run(['cmake', '--preset', 'web-minimal-'+configuration], destination/'NauEngineLite', configuration+'-minimal-configure')
            run(['cmake', '--build', '--preset', 'web-minimal-'+configuration, '-j', '8'], destination/'NauEngineLite', configuration+'-minimal-build')
            run([sys.executable, destination/'NauEngineLite/cmake/probes/minimal_web_delivery/run.py',
                 '--build', destination/f'NauEngineLite/build/web-minimal-{configuration}'], destination, configuration+'-minimal-chrome')
            shutil.copytree(destination/f'NauEngineLite/build/web-minimal-{configuration}/delivery-evidence',
                            evidence/(configuration+'-minimal'), dirs_exist_ok=True)
            run(['cmake','--preset','web-demo-'+configuration,'-DNAU_DEMO_TEST_HOOKS=OFF'],destination/'NauEngineLite',configuration+'-configure')
            run(['cmake','--build','--preset','web-demo-'+configuration,'-j','8'],destination/'NauEngineLite',configuration+'-build')
            run([sys.executable,destination/'NauDemo/web/test_package.py','--package',destination/f'NauEngineLite/build/web-demo-{configuration}/package',
                 '--output',evidence/configuration,'--base-path','/fresh/demo/'],destination,configuration+'-chrome')
        for name, original in before.items():
            assert original == subprocess.check_output(['git','diff','--binary','--ignore-submodules=all','HEAD'],cwd=destination/name), f'Build changed tracked source: {name}'
        report['passed']=True
    finally:
        (evidence/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Fresh checkout Debug/Release rendering and Stop passed')


if __name__=='__main__':
    main()

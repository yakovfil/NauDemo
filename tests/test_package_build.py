"""Verify archive changes propagate through delivery and missing inputs fail."""
import argparse, hashlib, json, pathlib, subprocess
parser=argparse.ArgumentParser()
parser.add_argument('--build',type=pathlib.Path,required=True)
parser.add_argument('--configuration',choices=['Debug','Release'],default='Debug')
parser.add_argument('--web',action='store_true')
args=parser.parse_args();demo=pathlib.Path(__file__).resolve().parents[1]
source=demo/('web/cube.vert' if args.web else 'assets/cube.gltf')
original=source.read_bytes();held=source.with_name(source.name+'.build-check-held')
assert not held.exists()
archive=args.build/('external/NauDemo/assets/NauDemo.nau_pack' if args.web else f'external/NauDemo/native-assets/{args.configuration}/NauDemo.nau_pack')
delivery=args.build/'package/NauDemo.data' if args.web else demo/f'bin/{args.configuration}/NauDemo.nau_pack'
command=['cmake','--build',str(args.build),'--config',args.configuration,'--target','NauDemoWebPackage' if args.web else 'NauDemo','--parallel','8']
evidence=[]
def build(expect=True):
    process=subprocess.run(command,capture_output=True,text=True,timeout=180)
    evidence.append({'command':command,'code':process.returncode,'output':process.stdout+process.stderr})
    assert (process.returncode==0)==expect,evidence[-1]['output'][-2000:]
def hash(path):return hashlib.sha256(path.read_bytes()).hexdigest()
try:
    before=(hash(archive),hash(delivery))
    source.write_bytes(original+(b'\n// package dependency acceptance\n' if args.web else b'\n '))
    build();after=(hash(archive),hash(delivery))
    assert before[0]!=after[0] and before[1]!=after[1]
    source.rename(held);build(False)
    assert after==(hash(archive),hash(delivery))
finally:
    if held.exists():held.rename(source)
    source.write_bytes(original)
    build()
assert before==(hash(archive),hash(delivery))
(args.build/'package-build-check.json').write_text(json.dumps({'passed':True,'before':before,'after':after,'cases':evidence},indent=2))
print('Package build dependency checks passed')

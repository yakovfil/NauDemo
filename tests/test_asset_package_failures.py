"""Exercise native archive/entry failures against a relocated delivery."""
import argparse, json, pathlib, subprocess
parser=argparse.ArgumentParser()
parser.add_argument('--delivery',type=pathlib.Path,required=True)
parser.add_argument('--output',type=pathlib.Path,required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
archive=args.delivery/'NauDemo.nau_pack';original=archive.read_bytes()
end=original.index(b'\n\n')+2
length=int(original[:end].split(b'Content-Length: ')[1].splitlines()[0])
index=json.loads(original[end+1:end+1+length]);payload=original[end+1+length:]
checks=[]
try:
    for scenario,entry in [('missing-archive',None),('corrupt-archive',None),('missing-font','demo/fonts/Abel-Regular.ttf'),('missing-buffer','demo/cube.bin')]:
        if scenario=='missing-archive':archive.unlink()
        elif scenario=='corrupt-archive':archive.write_bytes(original[:100])
        else:
            changed={**index,'content':[x for x in index['content'] if x['filePath']!=entry]}
            raw=json.dumps(changed,separators=(',',':')).encode()
            header=f'NauContent-Kind: nau-vfs-pack\nContent-Type: application/json\nContent-Length: {len(raw)}\n\n\n'.encode()
            archive.write_bytes(header+raw+payload)
        result=subprocess.run([str((args.delivery/'NauDemo.exe').resolve())],cwd=args.output.resolve(),capture_output=True,text=True,timeout=25)
        (args.output/(scenario+'.log')).write_text(result.stdout+result.stderr)
        assert result.returncode!=0,scenario
        assert ('NauDemo.nau_pack' if entry is None else entry.removeprefix('demo/')) in result.stdout+result.stderr,scenario
        assert 'Executor must be specified' not in result.stdout+result.stderr
        checks.append({'scenario':scenario,'exitCode':result.returncode,'passed':True})
        archive.write_bytes(original)
finally:archive.write_bytes(original)
(args.output/'results.json').write_text(json.dumps(checks,indent=2))
print('Native package failures passed')

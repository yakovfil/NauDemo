"""Create isolated local checkouts and overlay this uncommitted change for validation."""
import json, pathlib, shutil, subprocess
demo=pathlib.Path(__file__).resolve().parents[1]
workspace=demo.parent
destination=demo/'build/fresh-checkout/source'
destination.mkdir(parents=True,exist_ok=True)
evidence=[]
for name in ('NauEngineLite','NauEngineModules','NauDemo'):
    source=workspace/name;target=destination/name
    if target.exists(): raise RuntimeError(f'Fresh-checkout target already exists: {target}')
    subprocess.run(['git','clone','--shared','--no-hardlinks',str(source),str(target)],check=True)
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    paths=subprocess.check_output(['git','-C',str(source),'diff','--name-only','HEAD'],text=True).splitlines()
    paths+=subprocess.check_output(['git','-C',str(source),'ls-files','--others','--exclude-standard'],text=True).splitlines()
    copied=[]
    for relative in paths:
        original=source/relative;output=target/relative
        if original.is_dir(): continue
        if original.exists():
            output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,output);copied.append(relative)
        elif output.exists():output.unlink();copied.append(relative)
    evidence.append({'project':name,'revision':revision,'changeOverlay':copied})
engine=destination/'NauEngineLite'
dependency='engine/3rdparty_libs/googletest'
subprocess.run(['git','clone','--shared',str(workspace/'NauEngineLite'/dependency),str(engine/dependency)],check=True)
revision=subprocess.check_output(['git','-C',str(engine),'ls-tree','HEAD',dependency],text=True).split()[2]
subprocess.run(['git','-C',str(engine/dependency),'checkout','--detach',revision],check=True)
evidence.append({'dependency':dependency,'recordedRevision':revision,'dirtyOriginalFilesCopied':False})
(demo/'build/fresh-checkout/source-snapshot.json').write_text(json.dumps(evidence,indent=2))
print(destination)

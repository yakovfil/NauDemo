"""Run a relocated web delivery while checkout asset directories are absent."""
import argparse, pathlib, subprocess
parser=argparse.ArgumentParser()
parser.add_argument('--package',type=pathlib.Path,required=True)
parser.add_argument('--output',type=pathlib.Path,required=True)
parser.add_argument('--native-root',type=pathlib.Path)
args=parser.parse_args();demo=pathlib.Path(__file__).resolve().parents[1];workspace=demo.parent
sources=[demo/'assets',workspace/'NauSamples/sceneBase/content',workspace/'NauSamples/sceneBase/resources',demo/'build/fresh-checkout/source']
moved=[]
try:
    for source in sources:
        held=source.with_name(source.name+'.package-validation-held')
        assert source.resolve().is_relative_to(workspace) and held.resolve().is_relative_to(workspace)
        assert source.exists() and not held.exists()
        source.rename(held);moved.append((source,held))
    if args.native_root:
        for configuration in ('Debug','Release'):
            delivery=(args.native_root/configuration).resolve()
            subprocess.run(['python',str(demo/'tests/test_application_host_native.py'),'--configuration',configuration,'--delivery',str(delivery),'--output',str((args.output/configuration).resolve())],check=True)
            subprocess.run(['python',str(demo/'tests/test_asset_package_failures.py'),'--delivery',str(delivery),'--output',str((args.output/(configuration+'-failures')).resolve())],check=True)
    subprocess.run(['python',str(demo/'web/test_package.py'),'--package',str(args.package.resolve()),'--output',str(args.output.resolve()),'--base-path','/nested/demo/','--scenario','success'],check=True)
finally:
    for source,held in reversed(moved):held.rename(source)
print('Source-inaccessible relocation passed; source directories restored')

"""Build both asset packages and check shared input/manifest dependencies.

Uses the native packer without compiling either renderer. Run after
cmake/build_asset_packer.ps1, or supply --packer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


demo = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--packer', type=Path,
                    default=demo / 'build/asset-pack-host/bin/Release/AssetPackToolCmd.exe')
args = parser.parse_args()
packer = args.packer.resolve(strict=True)


def run(command, success=True):
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    assert (result.returncode == 0) == success, result.stdout + result.stderr


with tempfile.TemporaryDirectory(prefix='asset-manifests-', dir=demo / 'build') as directory:
    source = Path(directory)
    build = source / 'build'
    shutil.copytree(demo / 'assets', source / 'assets')
    shutil.copytree(demo / 'cmake', source / 'cmake')
    # The native shader compiler is outside this packaging test's scope.
    (source / 'shader_cache.nsbc').write_bytes(b'packaging test shader cache')
    (source / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.24)
project(AssetManifestChecks NONE)
include(cmake/asset_packages.cmake)
set(SHADER_CACHE "${CMAKE_CURRENT_SOURCE_DIR}/shader_cache.nsbc")
foreach(platform native web)
  nau_demo_package("${CMAKE_CURRENT_SOURCE_DIR}/cmake/${platform}_assets.json.in"
    "${CMAKE_CURRENT_BINARY_DIR}/${platform}.json"
    "${CMAKE_CURRENT_BINARY_DIR}/${platform}.nau_pack")
  add_custom_target(${platform} ALL DEPENDS "${CMAKE_CURRENT_BINARY_DIR}/${platform}.nau_pack")
endforeach()
''')
    run(['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja',
         f'-DNAU_ASSET_PACKER={packer.as_posix()}',
         f'-DNAU_SAMPLES_SOURCE_DIR={(demo.parent / "NauSamples").as_posix()}'])
    command = ['cmake', '--build', str(build)]
    run(command)

    def manifests():
        return [json.loads((build / f'{platform}.json').read_text())['files']
                for platform in ('native', 'web')]

    def hashes():
        return [hashlib.sha256((build / f'{platform}.nau_pack').read_bytes()).hexdigest()
                for platform in ('native', 'web')]

    native, web = manifests()
    common_path = source / 'cmake/common_assets.json.in'
    common = json.loads(common_path.read_text())
    count = len(common['files'])
    assert native[:count] == web[:count]
    for platform, entries in zip(('native', 'web'), (native, web)):
        variants = json.loads((source / f'cmake/{platform}_assets.json.in').read_text())
        assert len(entries) == count + len(variants['files'])
        assert len({entry['path'] for entry in entries}) == len(entries)
        assert all(Path(entry['source']).is_file() for entry in entries)
        assert all(entry['source'].startswith('@DEMO@/assets/')
                   for entry in common['files'] + variants['files']
                   if entry['source'].startswith('@DEMO@/'))

    original = hashes()
    mesh = source / 'assets/cube.gltf'
    mesh_bytes = mesh.read_bytes()
    mesh.write_bytes(mesh_bytes + b'\n ')
    run(command)
    assert all(a != b for a, b in zip(original, hashes()))
    mesh.write_bytes(mesh_bytes)
    run(command)
    assert hashes() == original

    # Editing the common manifest must trigger CMake regeneration for both packages.
    common['files'].append({'source': '@DEMO@/assets/cube.gltf', 'path': 'demo/shared-copy.gltf'})
    common_path.write_text(json.dumps(common))
    run(command)
    assert all(any(entry['path'] == 'demo/shared-copy.gltf' for entry in entries)
               for entries in manifests())
    assert all(a != b for a, b in zip(original, hashes()))

    before_missing = hashes()
    mesh.unlink()
    run(command, success=False)
    assert hashes() == before_missing

print('Native/web manifest composition, shared asset rebuild, manifest regeneration, and missing-input checks passed')

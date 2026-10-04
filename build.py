"""Build the integrated NauDemo target from its generated engine configuration."""
import argparse
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def validate_engine_toolchain(cache, source):
    values = {line.split(':', 1)[0]: line.split('=', 1)[1]
              for line in cache.splitlines() if ':' in line and '=' in line and not line.startswith('//')}
    toolset = values.get('CMAKE_GENERATOR_TOOLSET', '').split(',')[0]
    projects = {node.text for node in source.iter() if node.tag.endswith('}PlatformToolset')}
    if (values.get('CMAKE_GENERATOR') != 'Visual Studio 18 2026' or toolset != 'v145'
            or values.get('CMAKE_GENERATOR_PLATFORM', '').split(',')[0] != 'x64'
            or projects != {'v145'}):
        raise ValueError('The integrated demo build requires a VS 2026/v145 x64 engine build. '
                         'Configure win_vs2026_x64 in a clean directory and build SceneBaseSample; '
                         f"detected {values.get('CMAKE_GENERATOR')}, {toolset}, project toolsets {projects}.")


def find_msbuild():
    vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    try:
        matches = subprocess.check_output([str(vswhere), '-latest', '-version', '[18.0,19.0)',
            '-products', '*', '-requires', 'Microsoft.Component.MSBuild',
            'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
            '-find', 'MSBuild/**/Bin/MSBuild.exe'], text=True).splitlines()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError('Unable to discover VS 2026. Install VS 2026 C++ tools and v145.') from error
    if not matches:
        raise ValueError('No VS 2026 MSBuild with C++ tools found. Install VS 2026 C++ tools and v145.')
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=Path(__file__).resolve().parent.parent / "NauEngineLite")
    parser.add_argument("--engine-build", type=Path)
    parser.add_argument("--samples", type=Path, help="NauSamples checkout; defaults to the configured engine cache")
    parser.add_argument("--config", choices=["Debug", "Release"], default="Debug")
    args = parser.parse_args()
    demo = Path(__file__).resolve().parent
    engine = args.engine.resolve()
    engine_build = (args.engine_build or demo / "build/native-text").resolve()
    integrated = engine_build / "external/NauDemo/NauDemo.vcxproj"
    if not integrated.is_file():
        parser.error("This cache does not contain the integrated NauDemo target with NauScreenText. "
                     "Configure the engine into NauDemo/build/native-text with "
                     "-DCMAKE_PROJECT_NauEngine_INCLUDE=<NauDemo>/cmake/attach_demo.cmake, "
                     "then use --engine-build <NauDemo>/build/native-text. See README.md.")
    if not engine_build.is_relative_to(demo):
        parser.error("Configure the demo build inside NauDemo; build artifacts must remain in the demo checkout.")
    try:
        cache=(engine_build/'CMakeCache.txt').read_text(encoding='utf-8')
        validate_engine_toolchain(cache,
                                  ET.parse(integrated).getroot())
    except ValueError as error:
        parser.error(str(error))
    home=next((line.split('=',1)[1] for line in cache.splitlines() if line.startswith('CMAKE_HOME_DIRECTORY:')),None)
    if not home or Path(home).resolve()!=engine:
        parser.error("The configured engine source differs from --engine; reconfigure the CMake cache for that checkout.")
    if args.samples:
        parser.error("Set NAU_SAMPLES_SOURCE_DIR when configuring the integrated CMake build; --samples cannot relocate a generated cache.")
    subprocess.run(["cmake", "--build", str(engine_build), "--config", args.config,
                    "--target", "NauDemo", "--parallel"], check=True)
    print(f"Built {demo / 'bin' / args.config / 'NauDemo.exe'}")


if __name__ == "__main__":
    main()

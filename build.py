"""Build just the demo against an existing VS2026/v145 static SceneBaseSample build."""
import argparse
import copy
import os
from pathlib import Path
import shutil
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
        raise ValueError('This fast build requires a VS 2026/v145 x64 engine build. '
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
    engine_build = (args.engine_build or engine / "build/win_vs2026_x64").resolve()
    sample = engine_build / "samples/sceneBase"
    project_file = sample / "SceneBaseSample.vcxproj"
    if not project_file.exists():
        parser.error(f"Missing {project_file}. Build the engine's static SceneBaseSample first; see README.md.")

    # Reuse the exact ABI, compiler flags, and transitive link list produced by
    # the engine's CMake. Generate a NEW project; never edit its generated files.
    ns = "http://schemas.microsoft.com/developer/msbuild/2003"
    ET.register_namespace("", ns)
    tag = lambda name: f"{{{ns}}}{name}"
    source = ET.parse(project_file).getroot()
    cache = (engine_build / "CMakeCache.txt").read_text(encoding="utf-8")
    try:
        validate_engine_toolchain(cache, source)
        msbuild = find_msbuild()
    except ValueError as error:
        parser.error(str(error))
    definition = next((node for node in source.findall(tag("ItemDefinitionGroup"))
                       if f"'{args.config}|x64'" in node.get("Condition", "")), None)
    if definition is None:
        parser.error(f"No {args.config}|x64 settings in {project_file}")
    definition = copy.deepcopy(definition)
    definitions = definition.find(f"{tag('ClCompile')}/{tag('PreprocessorDefinitions')}").text
    if "NAU_STATIC_RUNTIME=1" not in definitions:
        parser.error("This fast build needs a static engine build, not the DLL preset.")

    old_root = next(line.split("=", 1)[1] for line in cache.splitlines()
                    if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL="))
    old_samples = next((line.split("=", 1)[1] for line in cache.splitlines()
                        if line.startswith("NAU_SAMPLES_SOURCE_DIR:PATH=")), str(engine.parent / "NauSamples"))
    samples = (args.samples or Path(old_samples)).resolve()
    if not (samples / "sceneBase/CMakeLists.txt").is_file():
        parser.error(f"Missing NauSamples checkout: {samples}. Initialize it or pass --samples.")

    def relocate(value):
        return value.replace(old_samples.replace("/", "\\"), str(samples)).replace(old_samples, samples.as_posix()).replace(old_root.replace("/", "\\"), str(engine)).replace(old_root, engine.as_posix())

    for node in definition.iter():
        if node.text:
            node.text = relocate(node.text)

    output = demo / "bin" / args.config
    intermediates = demo / "build" / args.config
    output.mkdir(parents=True, exist_ok=True)
    intermediates.mkdir(parents=True, exist_ok=True)
    compile_settings = definition.find(tag("ClCompile"))
    for node in list(compile_settings):
        if node.tag.split("}")[-1] in {"PrecompiledHeader", "PrecompiledHeaderFile", "PrecompiledHeaderOutputFile", "ForcedIncludeFiles", "ProgramDataBaseFileName"}:
            compile_settings.remove(node)
    ET.SubElement(compile_settings, tag("PrecompiledHeader")).text = "NotUsing"
    defines = compile_settings.find(tag("PreprocessorDefinitions"))
    defines.text += f';NAU_DEMO_DIR="{demo.as_posix()}";NAU_ENGINE_DIR="{engine.as_posix()}";NAU_SAMPLES_DIR="{samples.as_posix()}"'

    link = definition.find(tag("Link"))
    libraries = link.find(tag("AdditionalDependencies"))
    resolved_libraries = []
    for library in libraries.text.split(";"):
        if "/" in library or "\\" in library:
            path = Path(library)
            if not path.is_absolute():
                path = sample / path
            path = path.resolve()
            if not path.exists():
                parser.error(f"Engine library is missing: {path}. Build SceneBaseSample in {args.config} first.")
            library = str(path)
        resolved_libraries.append(library)
    libraries.text = ";".join(resolved_libraries)
    for node in list(link):
        if node.tag.split("}")[-1] in {"OutputFile", "ImportLibrary", "ProgramDataBaseFile"}:
            link.remove(node)
    ET.SubElement(link, tag("OutputFile")).text = str(output / "NauDemo.exe")
    ET.SubElement(link, tag("ProgramDataBaseFile")).text = str(output / "NauDemo.pdb")
    for name in ["CustomBuildStep", "PreBuildEvent", "PostBuildEvent", "ProjectReference"]:
        for node in definition.findall(tag(name)):
            definition.remove(node)

    project = ET.Element(tag("Project"), DefaultTargets="Build", ToolsVersion="Current")
    group = ET.SubElement(project, tag("ItemGroup"), Label="ProjectConfigurations")
    conf = ET.SubElement(group, tag("ProjectConfiguration"), Include=f"{args.config}|x64")
    ET.SubElement(conf, tag("Configuration")).text = args.config
    ET.SubElement(conf, tag("Platform")).text = "x64"
    group = ET.SubElement(project, tag("PropertyGroup"), Label="Globals")
    ET.SubElement(group, tag("WindowsTargetPlatformVersion")).text = "10.0"
    ET.SubElement(project, tag("Import"), Project="$(VCTargetsPath)\\Microsoft.Cpp.Default.props")
    group = ET.SubElement(project, tag("PropertyGroup"), Label="Configuration")
    for key, value in {"ConfigurationType": "Application", "PlatformToolset": "v145",
                       "UseDebugLibraries": str(args.config == "Debug").lower()}.items():
        ET.SubElement(group, tag(key)).text = value
    ET.SubElement(project, tag("Import"), Project="$(VCTargetsPath)\\Microsoft.Cpp.props")
    group = ET.SubElement(project, tag("PropertyGroup"))
    for key, value in {"OutDir": str(output) + "\\", "IntDir": str(intermediates) + "\\",
                       "TargetName": "NauDemo"}.items():
        ET.SubElement(group, tag(key)).text = value
    project.append(definition)
    group = ET.SubElement(project, tag("ItemGroup"))
    for path in [demo / "src/main.cpp", sample / "generated_static_modules_initialization.cpp"]:
        ET.SubElement(group, tag("ClCompile"), Include=str(path))
    ET.SubElement(project, tag("Import"), Project="$(VCTargetsPath)\\Microsoft.Cpp.targets")
    generated = intermediates / "NauDemo.vcxproj"
    ET.indent(project)
    ET.ElementTree(project).write(generated, encoding="utf-8", xml_declaration=True)

    subprocess.run([msbuild, str(generated), f"/p:Configuration={args.config}", "/p:Platform=x64", "/m", "/verbosity:minimal"], check=True)
    for dll in (engine_build / "bin" / args.config).glob("*.dll"):
        shutil.copy2(dll, output / dll.name)
    print(f"Built {output / 'NauDemo.exe'}")


if __name__ == "__main__":
    main()

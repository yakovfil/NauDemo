"""Build just the demo against an existing VS2022 static SceneBaseSample build."""
import argparse
import copy
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=Path(__file__).resolve().parent.parent / "NauEngineLite")
    parser.add_argument("--engine-build", type=Path)
    parser.add_argument("--config", choices=["Debug", "Release"], default="Debug")
    args = parser.parse_args()
    demo = Path(__file__).resolve().parent
    engine = args.engine.resolve()
    engine_build = (args.engine_build or engine / "build/win_vs2022_x64").resolve()
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
    definition = next((node for node in source.findall(tag("ItemDefinitionGroup"))
                       if f"'{args.config}|x64'" in node.get("Condition", "")), None)
    if definition is None:
        parser.error(f"No {args.config}|x64 settings in {project_file}")
    definition = copy.deepcopy(definition)
    definitions = definition.find(f"{tag('ClCompile')}/{tag('PreprocessorDefinitions')}").text
    if "NAU_STATIC_RUNTIME=1" not in definitions:
        parser.error("This fast build needs a static engine build, not the DLL preset.")

    cache = (engine_build / "CMakeCache.txt").read_text(encoding="utf-8")
    old_root = next(line.split("=", 1)[1] for line in cache.splitlines()
                    if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL="))

    def relocate(value):
        return value.replace(old_root.replace("/", "\\"), str(engine)).replace(old_root, engine.as_posix())

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
    defines.text += f';NAU_DEMO_DIR="{demo.as_posix()}";NAU_ENGINE_DIR="{engine.as_posix()}"'

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

    project = ET.Element(tag("Project"), DefaultTargets="Build", ToolsVersion="17.0")
    group = ET.SubElement(project, tag("ItemGroup"), Label="ProjectConfigurations")
    conf = ET.SubElement(group, tag("ProjectConfiguration"), Include=f"{args.config}|x64")
    ET.SubElement(conf, tag("Configuration")).text = args.config
    ET.SubElement(conf, tag("Platform")).text = "x64"
    group = ET.SubElement(project, tag("PropertyGroup"), Label="Globals")
    ET.SubElement(group, tag("WindowsTargetPlatformVersion")).text = "10.0"
    ET.SubElement(project, tag("Import"), Project="$(VCTargetsPath)\\Microsoft.Cpp.Default.props")
    group = ET.SubElement(project, tag("PropertyGroup"), Label="Configuration")
    for key, value in {"ConfigurationType": "Application", "PlatformToolset": "v143",
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

    vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    msbuild = subprocess.check_output([str(vswhere), "-latest", "-products", "*", "-requires",
                                      "Microsoft.Component.MSBuild", "-find", "MSBuild/**/Bin/MSBuild.exe"], text=True).splitlines()[0]
    subprocess.run([msbuild, str(generated), f"/p:Configuration={args.config}", "/p:Platform=x64", "/m", "/verbosity:minimal"], check=True)
    for dll in (engine_build / "bin" / args.config).glob("*.dll"):
        shutil.copy2(dll, output / dll.name)
    print(f"Built {output / 'NauDemo.exe'}")


if __name__ == "__main__":
    main()

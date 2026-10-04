"""Toolchain provenance and discovery checks for the integrated native builder."""
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from build import find_msbuild, validate_engine_toolchain


class ToolchainTests(unittest.TestCase):
    def setUp(self):
        self.cache = ('CMAKE_GENERATOR:INTERNAL=Visual Studio 18 2026\n'
                      'CMAKE_GENERATOR_TOOLSET:INTERNAL=v145,host=x64\n'
                      'CMAKE_GENERATOR_PLATFORM:INTERNAL=x64\n')
        self.project = ET.fromstring('<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'
                                     '<PropertyGroup><PlatformToolset>v145</PlatformToolset></PropertyGroup></Project>')

    def test_supported_engine(self):
        validate_engine_toolchain(self.cache, self.project)

    def test_old_cache_and_project_are_rejected(self):
        for cache in (self.cache.replace('18 2026', '17 2022'), self.cache.replace('v145', 'v143'),
                      self.cache.replace('=x64', '=Win32'), ''):
            with self.subTest(cache=cache), self.assertRaisesRegex(ValueError, 'clean directory'):
                validate_engine_toolchain(cache, self.project)
        self.project.find('.//{*}PlatformToolset').text = 'v143'
        with self.assertRaises(ValueError):
            validate_engine_toolchain(self.cache, self.project)

    @patch('build.subprocess.check_output', return_value='C:/VS18/MSBuild.exe\n')
    def test_discovery_selects_vs18_cpp_tools(self, query):
        self.assertEqual(find_msbuild(), 'C:/VS18/MSBuild.exe')
        args = query.call_args.args[0]
        self.assertEqual(args[args.index('-version') + 1], '[18.0,19.0)')
        self.assertIn('Microsoft.VisualStudio.Component.VC.Tools.x86.x64', args)

    @patch('build.subprocess.check_output', return_value='')
    def test_missing_installation(self, query):
        with self.assertRaisesRegex(ValueError, 'Install VS 2026'):
            find_msbuild()


if __name__ == '__main__':
    unittest.main()

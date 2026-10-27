import argparse
import os
from pathlib import Path
import struct
import subprocess


def build(root, output):
    source = Path(__file__).with_name('window_focus.c')
    vswhere = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    installation = Path(subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-property', 'installationPath'], text=True).strip())
    toolset = max((installation / 'VC/Tools/MSVC').iterdir(), key=lambda path: tuple(map(int, path.name.split('.'))))
    sdk = Path(os.environ['ProgramFiles(x86)']) / 'Windows Kits/10'
    sdk_version = max((sdk / 'Include').iterdir(), key=lambda path: tuple(map(int, path.name.split('.')))).name
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.stem + '.building.pyd')
    arguments = [str(toolset / 'bin/Hostx64/x64/cl.exe'), '/nologo', '/LD', '/O2', '/MT', '/W4', '/wd4100',
                 '/I' + str(root / 'py27_dist/include'), '/I' + str(toolset / 'include')]
    arguments += ['/I' + str(sdk / 'Include' / sdk_version / folder) for folder in ('ucrt', 'shared', 'um')]
    arguments += [str(source), '/Fo' + str(output.with_suffix('.obj')), '/Fe' + str(temporary), '/link',
                  '/LIBPATH:' + str(root / 'py27_dist/libs'), '/LIBPATH:' + str(toolset / 'lib/x64'),
                  '/LIBPATH:' + str(sdk / 'Lib' / sdk_version / 'ucrt/x64'),
                  '/LIBPATH:' + str(sdk / 'Lib' / sdk_version / 'um/x64'), 'user32.lib', '/MANIFEST:NO',
                  '/IMPLIB:' + str(output.with_suffix('.lib'))]
    environment = dict(os.environ)
    environment['PATH'] = str(toolset / 'bin/Hostx64/x64') + os.pathsep + environment.get('PATH', '')
    subprocess.check_call(arguments, env=environment)
    binary = temporary.read_bytes()
    pe_offset = struct.unpack_from('<I', binary, 0x3c)[0]
    assert struct.unpack_from('<H', binary, pe_offset + 4)[0] == 0x8664
    dumpbin = str(toolset / 'bin/Hostx64/x64/dumpbin.exe')
    dependencies = subprocess.check_output([dumpbin, '/dependents', str(temporary)], text=True)
    exports = subprocess.check_output([dumpbin, '/exports', str(temporary)], text=True)
    assert 'msvcr90' not in dependencies.lower()
    assert 'init_ua_window_focus' in exports
    os.replace(temporary, output)
    print('NATIVE', output, 'IMPORTS', [line.strip() for line in dependencies.splitlines() if '.dll' in line.lower()])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('vendor') / '_ua_window_focus.pyd')
    options = parser.parse_args()
    build(options.game_root, options.output)

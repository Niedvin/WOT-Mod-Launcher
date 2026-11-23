import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree


SOURCE = Path(__file__).resolve().parent
VIEWS = {'MembersWindow': 1, 'PlatoonDropdown': 4}
UI = 'gui/gameface/_dist/production/lobby/platoon/'


def build(root):
    meta = json.loads((SOURCE / 'mod.json').read_text(encoding='utf-8'))
    client = re.search(r'v\.(\d+(?:\.\d+){3})', (root / 'version.xml').read_text()).group(1)
    directory = root / 'build' / 'mods' / client
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"ua.platoon_autostart_{meta['version']}.wotmod"
    metadata = ElementTree.Element('root')
    for name, value in (('id', 'ua.platoon_autostart'), ('version', meta['version']),
                        ('name', meta['title']), ('description', meta['description'])):
        ElementTree.SubElement(metadata, name).text = value
    resource = 'scripts/client/gui/mods/mod_platoon_autostart.py'
    with tempfile.TemporaryDirectory(dir=directory) as work:
        work = Path(work)
        compiled = work / 'platoon.pyc'
        subprocess.run([
            str(root / 'py27_dist' / 'python.exe'), '-B', '-c',
            'import py_compile,sys; py_compile.compile(sys.argv[1],sys.argv[2],sys.argv[3],doraise=True)',
            str(SOURCE / 'mod_platoon_autostart.py'), str(compiled), resource,
        ], check=True)
        package = work / output.name
        with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('meta.xml', ElementTree.tostring(metadata, encoding='utf-8'))
            archive.write(compiled, 'res/' + resource + 'c')
            for view, part in VIEWS.items():
                path = UI + view + '/' + view
                with zipfile.ZipFile(root / 'res' / 'packages' / f'gui-part{part}.pkg') as native:
                    archive.writestr('res/' + path + '.stock.js', native.read(path + '.js'))
                archive.write(SOURCE / 'bootstrap.js', 'res/' + path + '.js')
                archive.write(SOURCE / (view + '.js'), 'res/' + path + '.squad.js')
                archive.write(SOURCE / (view + '.css'), 'res/' + path + '.squad.css')
        with zipfile.ZipFile(package) as archive:
            if archive.testzip() is not None:
                raise ValueError('Corrupt Squad+ package')
        package.replace(output)
    print(output)
    return output


if __name__ == '__main__':
    build(Path.cwd())

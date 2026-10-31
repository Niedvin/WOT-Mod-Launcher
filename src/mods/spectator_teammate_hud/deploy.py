import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
NAME = 'ua.spectator_teammate_hud_1.0.9.wotmod'
SOURCE = ROOT / 'scratch/spectator_hud' / NAME


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def running_game():
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                             "$ErrorActionPreference = 'Stop'; if (Get-Process | Where-Object ProcessName -EQ 'WorldOfTanks') { exit 0 }; exit 1"],
                            capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError('Cannot verify game process state')
    return result.returncode == 0


def write_report(path, value):
    if path is not None:
        temporary = path.with_name(path.name + '.tmp')
        temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
        os.replace(temporary, path)


def deploy(target, expected_sha256=None, report=None):
    target = target.resolve()
    if target == ROOT and running_game():
        result = {'state': 'waiting_for_game_exit', 'version': '1.0.9'}
        write_report(report, result)
        return result
    version = re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', (target / 'version.xml').read_text(encoding='utf-8'))
    if not version or version.group(1) != '2.4.1.1':
        raise ValueError('Unexpected game version')
    source_hash = digest(SOURCE)
    if expected_sha256 and source_hash.lower() != expected_sha256.lower():
        raise ValueError('Prepared package changed')
    with zipfile.ZipFile(SOURCE) as package:
        assert package.testzip() is None
        assert all(info.compress_type == zipfile.ZIP_STORED for info in package.infolist())
        assert b'<version>1.0.9</version>' in package.read('meta.xml')
        assert struct.unpack('<H', package.read('res/scripts/client/gui/mods/mod_spectator_teammate_hud.pyc')[:2])[0] == 62211
    directory = target / 'mods' / version.group(1)
    directory.mkdir(parents=True, exist_ok=True)
    old = list(directory.glob('ua.spectator_teammate_hud_*.wotmod'))
    unrelated = {path.relative_to(target).as_posix(): digest(path) for path in (target / 'mods').rglob('*.wotmod') if path not in old}
    config = target / 'mods/configs/spectator_teammate_hud/config.json'
    config_hash = digest(config) if config.exists() else None
    destination = directory / NAME
    if len(old) == 1 and old[0] == destination and digest(destination) == source_hash:
        result = {'state': 'installed', 'version': '1.0.9', 'sha256': source_hash, 'config_preserved': True, 'already_installed': True}
        write_report(report, result)
        return result
    backup = target / '.backups' / ('spectator-install-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True)
    for path in old:
        shutil.copy2(path, backup / path.name)
        assert digest(path) == digest(backup / path.name)
    if config.exists():
        shutil.copy2(config, backup / 'config.json')
    temporary = directory / ('.' + NAME + '.installing')
    shutil.copy2(SOURCE, temporary)
    assert digest(temporary) == source_hash
    moved = []
    try:
        if target == ROOT and running_game():
            temporary.unlink()
            result = {'state': 'waiting_for_game_exit', 'version': '1.0.9'}
            write_report(report, result)
            return result
        for path in old:
            os.replace(path, backup / path.name)
            moved.append(path)
        os.replace(temporary, destination)
        assert digest(destination) == source_hash
        assert [path.name for path in directory.glob('ua.spectator_teammate_hud_*.wotmod')] == [NAME]
        assert (digest(config) if config.exists() else None) == config_hash
        assert all(digest(target / rel) == value for rel, value in unrelated.items())
    except Exception:
        for path in moved:
            shutil.copy2(backup / path.name, path)
        if destination not in old and destination.exists():
            destination.unlink()
        if temporary.exists():
            temporary.unlink()
        raise
    result = {'state': 'installed', 'version': '1.0.9', 'sha256': source_hash, 'backup': str(backup), 'config_preserved': True, 'unrelated_mods_preserved': True, 'unrelated_mod_count': len(unrelated)}
    write_report(report, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=Path, default=ROOT)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--report', type=Path)
    options = parser.parse_args()
    result = deploy(options.target, options.expected_sha256, options.report)
    print(json.dumps(result, indent=2))
    if result['state'] == 'waiting_for_game_exit':
        raise SystemExit(75)

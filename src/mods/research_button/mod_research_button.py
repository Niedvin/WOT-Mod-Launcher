from __future__ import absolute_import
import json
import os
from debug_utils import LOG_NOTE, LOG_CURRENT_EXCEPTION

_CONFIG_PATH = os.path.join('mods', 'configs', 'research_button', 'config.json')
_CONFIG = {'enabled': True}
_HOOKS = []
_REQUEST = 'ua.research'
_VERSION = '1.2.0'
_KNOWN_BUNDLE_HASHES = ('06faf1d78ababe0c81aec9a093bad96084dac4d10898aa0edbb1b7284788f8f9', '07979105c0c19ad22ae28b1b1f0987d904661adbe57ba0131427eed424e043a7', '1517f93026e78103183cbc764ff210707800a9c8912304273c1109743dfd50aa', '1bea21940e6a62874a2f326947aa44856c7422e40883ebd8e853b60ec818d62c')


def _ensure_packaged_file(mod_id, mod_version, member, target, accepted_sha256=None):
    import hashlib
    import re
    import shutil
    import time
    import zipfile
    with open('version.xml', 'rb') as stream:
        match = re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', stream.read())
    if match is None:
        raise ValueError('Game version not found')
    package = os.path.join('mods', match.group(1), '%s_%s.wotmod' % (mod_id, mod_version))
    with zipfile.ZipFile(package) as archive:
        data = archive.read(member)
    current = None
    state_path = target + '.ua-sha256'
    desired_sha256 = hashlib.sha256(data).hexdigest()
    if os.path.isfile(target):
        with open(target, 'rb') as stream:
            current = stream.read()
        if current == data:
            if accepted_sha256 is not None:
                with open(state_path, 'wb') as stream:
                    stream.write(desired_sha256)
            return True
        if accepted_sha256 is not None:
            accepted = set(accepted_sha256)
            if os.path.isfile(state_path):
                with open(state_path, 'rb') as stream:
                    accepted.add(stream.read().strip())
            if hashlib.sha256(current).hexdigest() not in accepted:
                LOG_NOTE('[%s] Existing override differs from known mod versions; preserving it' % mod_id)
                return False
    directory = os.path.dirname(target)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    saved = None
    if current is not None:
        backup = os.path.join('.backups', mod_id + '-' + time.strftime('%Y%m%d-%H%M%S'))
        if not os.path.isdir(backup):
            os.makedirs(backup)
        saved = os.path.join(backup, os.path.basename(target))
        shutil.copy2(target, saved)
    temporary = target + '.ua-updating'
    with open(temporary, 'wb') as stream:
        stream.write(data)
    with open(temporary, 'rb') as stream:
        if stream.read() != data:
            raise IOError('Payload copy verification failed')
    try:
        if os.path.isfile(target):
            os.remove(target)
        os.rename(temporary, target)
    except Exception:
        if saved is not None:
            shutil.copy2(saved, target)
        raise
    LOG_NOTE('[%s] Packaged resource installed: %s' % (mod_id, target))
    if accepted_sha256 is not None:
        with open(state_path, 'wb') as stream:
            stream.write(desired_sha256)
    return True


def _open_research(presenter, int_cd):
    if not _CONFIG.get('enabled', True) or int_cd <= 0:
        return
    try:
        from gui.shared.event_dispatcher import showVehicleHubModules
        if presenter.cameraController.isEnabled:
            return
        showVehicleHubModules(int_cd)
        LOG_NOTE('[ResearchButton] Opening vehicle modules directly intCD=%s' % int_cd)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _install():
    if _HOOKS:
        return
    from gui.impl.lobby.hangar.presenters.vehicle_menu_presenter import VehicleMenuPresenter
    name = '_VehicleMenuPresenter__onNavigate'
    original = getattr(VehicleMenuPresenter, name)

    def on_navigate(presenter, args):
        entry = args.get('entry')
        if isinstance(entry, basestring) and entry.startswith(_REQUEST + ':'):
            try:
                int_cd = int(entry[len(_REQUEST) + 1:])
            except (TypeError, ValueError):
                return
            return _open_research(presenter, int_cd)
        if entry in (_REQUEST, 'research'):
            from CurrentVehicle import g_currentVehicle
            if g_currentVehicle.isPresent():
                return _open_research(presenter, g_currentVehicle.item.intCD)
            return
        return original(presenter, args)

    setattr(VehicleMenuPresenter, name, on_navigate)
    _HOOKS.append((VehicleMenuPresenter, name, original, on_navigate))


def init():
    try:
        with open(_CONFIG_PATH, 'r') as stream:
            config = json.load(stream)
        if isinstance(config, dict):
            _CONFIG.update(config)
    except (IOError, ValueError):
        pass
    try:
        with open('version.xml', 'rb') as stream:
            import re
            version = re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', stream.read()).group(1)
        bundle = os.path.join('res_mods', version, 'gui', 'gameface', '_dist', 'production', 'mono', 'hangar', 'main', 'bundle.js')
        _ensure_packaged_file('ua.research_button', _VERSION, 'res/ua_mod_payloads/research_button/bundle.js', bundle, _KNOWN_BUNDLE_HASHES)
        _install()
        LOG_NOTE('[ResearchButton] Mod initialized version=1.2.0 enabled=%s' % _CONFIG.get('enabled', True))
    except Exception:
        LOG_CURRENT_EXCEPTION()


def fini():
    for cls, name, original, replacement in reversed(_HOOKS):
        if getattr(cls, name) is replacement:
            setattr(cls, name, original)
    del _HOOKS[:]
    LOG_NOTE('[ResearchButton] Mod unloaded')

# -*- coding: utf-8 -*-
from __future__ import absolute_import
import json
import os
import sys

import BigWorld
from debug_utils import LOG_NOTE, LOG_CURRENT_EXCEPTION

_CONFIG_DIR = os.path.abspath(os.path.join('mods', 'configs', 'background_fps_limiter'))
_CONFIG_PATH = os.path.join(_CONFIG_DIR, 'config.json')

_DEFAULT_CONFIG = {
    'enabled': True,
    'target_fps': 5,
    'focused_fps': 240,
    'enable_in_hangar': True,
    'enable_in_battle': True
}

_FOCUSED_FPS_DEFAULT = 240
_FOCUSED_FPS_MIN = 30
_FOCUSED_FPS_MAX = 240

_TICK_INTERVAL = 1.0
_WATCHDOG_INTERVAL = 3.0

_CONFIG = dict(_DEFAULT_CONFIG)


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


def _load_focus_probe():
    try:
        _ensure_packaged_file('ua.background_fps_limiter', '1.0.4', 'res/ua_mod_payloads/background_fps_limiter/_ua_window_focus.pyd', os.path.join(_CONFIG_DIR, '_ua_window_focus.pyd'))
        import imp
        probe = imp.load_dynamic('_ua_window_focus', os.path.join(_CONFIG_DIR, '_ua_window_focus.pyd'))
        LOG_NOTE('[BackgroundFpsLimiter] Native foreground detection loaded version=1.0.4')
        return probe
    except Exception:
        LOG_NOTE('[BackgroundFpsLimiter] Native focus probe unavailable; minimize detection only')
        LOG_CURRENT_EXCEPTION()
        return None


_focus_probe = _load_focus_probe()

_callback_id = None
_watchdog_id = None
_generation = 0
_last_limit = None
_applied_limit = None


def _load_config():
    global _CONFIG
    _CONFIG = dict(_DEFAULT_CONFIG)
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        if os.path.isfile(_CONFIG_PATH):
            with open(_CONFIG_PATH, 'rb') as fp:
                loaded = json.loads(fp.read())
            if isinstance(loaded, dict):
                _CONFIG.update(loaded)
        else:
            _save_config(_DEFAULT_CONFIG)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _save_config(settings=None):
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        with open(_CONFIG_PATH, 'wb') as fp:
            fp.write(json.dumps(settings if settings is not None else _CONFIG, indent=4))
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _is_window_focused():
    if _focus_probe is not None:
        return bool(_focus_probe.is_focused())
    try:
        return bool(BigWorld.isWindowVisible())
    except Exception:
        return True


def _is_in_battle():
    try:
        player = BigWorld.player()
        if player is None or player.__class__.__name__ != 'PlayerAvatar':
            return False
    except Exception:
        return False
    try:
        from gui.battle_control import avatar_getter
        return bool(avatar_getter.isPlayerOnArena())
    except Exception:
        return True


def _focused_limit():
    try:
        value = int(_CONFIG.get('focused_fps', _FOCUSED_FPS_DEFAULT))
    except (TypeError, ValueError):
        value = _FOCUSED_FPS_DEFAULT
    return max(_FOCUSED_FPS_MIN, min(_FOCUSED_FPS_MAX, value))


def _target_limit(focused):
    if not _CONFIG.get('enabled', True):
        return False, _focused_limit()
    in_battle = _is_in_battle()
    allowed = _CONFIG.get('enable_in_battle', True) if in_battle else _CONFIG.get('enable_in_hangar', True)
    if not allowed:
        return False, _focused_limit()
    if focused:
        return True, _focused_limit()
    try:
        target = int(_CONFIG.get('target_fps', 5))
    except (TypeError, ValueError):
        target = 5
    return True, max(1, min(30, target))


def _update_fps_limit(focused=None):
    global _last_limit, _applied_limit
    if focused is None:
        focused = _is_window_focused()
    active, limit = _target_limit(focused)
    if not active:
        if _applied_limit is not None:
            # Leaving the cap behind: release once, then stop touching the engine at all — 2026-10-31
            BigWorld.wg_setMaxFrameRate(limit)
            _applied_limit = None
            _last_limit = None
            LOG_NOTE('[BackgroundFpsLimiter] Disabled for this context; cap released once')
        return
    # Applied every tick: client can drop its own cap back to a stale value between ticks — 2026-10-31
    BigWorld.wg_setMaxFrameRate(limit)
    _applied_limit = limit
    if limit != _last_limit:
        _last_limit = limit
        LOG_NOTE('[BackgroundFpsLimiter] Frame rate limit -> %s' % ('off' if limit == 0 else '%d FPS' % limit))


def _cancel_tick():
    global _callback_id
    if _callback_id is not None:
        try:
            BigWorld.cancelCallback(_callback_id)
        except Exception:
            pass
        _callback_id = None


def _schedule_tick(delay):
    global _callback_id, _generation
    _cancel_tick()
    gen = _generation
    _callback_id = BigWorld.callback(delay, lambda: _check_focus_tick(gen))


def _check_focus_tick(gen):
    global _callback_id
    _callback_id = None
    if gen != _generation:
        return
    focused = True
    try:
        focused = _is_window_focused()
    except Exception:
        LOG_CURRENT_EXCEPTION()
    try:
        _update_fps_limit(focused)
    except Exception:
        LOG_CURRENT_EXCEPTION()
    try:
        _schedule_tick(_TICK_INTERVAL)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _cancel_watchdog():
    global _watchdog_id
    if _watchdog_id is not None:
        try:
            BigWorld.cancelCallback(_watchdog_id)
        except Exception:
            pass
        _watchdog_id = None


def _watchdog_tick(gen):
    global _watchdog_id
    _watchdog_id = None
    if gen != _generation:
        return
    if _callback_id is None:
        LOG_NOTE('[BackgroundFpsLimiter] Focus tick lost; rearming')
        try:
            _schedule_tick(0.0)
        except Exception:
            LOG_CURRENT_EXCEPTION()
    try:
        _watchdog_id = BigWorld.callback(_WATCHDOG_INTERVAL, lambda: _watchdog_tick(gen))
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_settings_changed(linkage, new_settings):
    if linkage != 'ua.background_fps_limiter':
        return
    if 'enabled' in new_settings:
        _CONFIG['enabled'] = bool(new_settings['enabled'])
    if 'target_fps' in new_settings:
        try:
            _CONFIG['target_fps'] = max(1, min(30, int(new_settings['target_fps'])))
        except (TypeError, ValueError):
            pass
    if 'focused_fps' in new_settings:
        try:
            _CONFIG['focused_fps'] = max(_FOCUSED_FPS_MIN, min(_FOCUSED_FPS_MAX, int(new_settings['focused_fps'])))
        except (TypeError, ValueError):
            pass
    if 'enable_in_hangar' in new_settings:
        _CONFIG['enable_in_hangar'] = bool(new_settings['enable_in_hangar'])
    if 'enable_in_battle' in new_settings:
        _CONFIG['enable_in_battle'] = bool(new_settings['enable_in_battle'])
    _save_config()
    try:
        _update_fps_limit()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _init_mods_settings(gen):
    if gen != _generation:
        return
    try:
        from gui.modsSettingsApi import g_modsSettingsApi, templates

        template = {
            'modDisplayName': 'Background FPS Limiter',
            'enabled': bool(_CONFIG.get('enabled', True)),
            'column1': [
                templates.createCheckbox(text='Увімкнути зниження FPS у фоні', varName='enabled', value=bool(_CONFIG.get('enabled', True))),
                templates.createSlider(text='FPS у фоновому режимі', varName='target_fps', value=max(1, min(30, int(_CONFIG.get('target_fps', 5)))), min=1, max=30, interval=1, format='{{value}} FPS'),
                templates.createSlider(text='FPS у фокусі', varName='focused_fps', value=_focused_limit(), min=_FOCUSED_FPS_MIN, max=_FOCUSED_FPS_MAX, interval=10, format='{{value}} FPS')
            ],
            'column2': [
                templates.createCheckbox(text='Знижувати FPS в ангарі', varName='enable_in_hangar', value=bool(_CONFIG.get('enable_in_hangar', True))),
                templates.createCheckbox(text='Знижувати FPS у бою', varName='enable_in_battle', value=bool(_CONFIG.get('enable_in_battle', True)))
            ]
        }
        saved = g_modsSettingsApi.setModTemplate('ua.background_fps_limiter', template, _on_settings_changed)
        if isinstance(saved, dict):
            _on_settings_changed('ua.background_fps_limiter', saved)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        from gui.modsListApi import g_modsListApi

        def _open_mod_settings():
            try:
                from gui.modsSettingsApi.view import loadView
                from gui.modsSettingsApi import g_modsSettingsApi
                loadView(g_modsSettingsApi)
            except Exception:
                LOG_CURRENT_EXCEPTION()

        g_modsListApi.addModification(
            id='ua.background_fps_limiter',
            name='Background FPS Limiter',
            description='Знижує FPS, коли вікно гри неактивне',
            icon='',
            enabled=True,
            login=False,
            lobby=True,
            callback=_open_mod_settings
        )
    except Exception:
        LOG_CURRENT_EXCEPTION()


def init():
    global _watchdog_id
    _load_config()
    gen = _generation
    BigWorld.callback(0.1, lambda: _init_mods_settings(gen))
    _schedule_tick(_TICK_INTERVAL)
    _watchdog_id = BigWorld.callback(_WATCHDOG_INTERVAL, lambda: _watchdog_tick(gen))
    LOG_NOTE('[BackgroundFpsLimiter] Mod initialized successfully (focus backend: %s)' % ('win32-foreground' if _focus_probe is not None else 'isWindowVisible-fallback'))


def fini():
    global _generation, _last_limit, _applied_limit
    _generation += 1
    _cancel_tick()
    _cancel_watchdog()
    try:
        BigWorld.wg_setMaxFrameRate(_focused_limit())
        _last_limit = None
        _applied_limit = None
    except Exception:
        pass

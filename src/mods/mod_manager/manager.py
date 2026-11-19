# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import errno
import io
import json
import logging
import math
import os
import re
import sys
import tempfile
import zipfile
from xml.etree import ElementTree

from . import bindings
from .catalog import BINDS, ALIASES, DEPENDENCIES, HIDDEN, LEGACY_MANAGERS, PROFILES, profile
from .openwg import SETTINGS as GRAPHICS_SETTINGS
from .openwg import controller_for, fields_for


OFF = '.manager-off'
EXT = '.wotmod'
LOGGER = logging.getLogger('Niedvin/ModManager')
try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)


def read_json(path, default=None):
    source = path if os.path.exists(path) else path + '.manager-previous'
    try:
        with io.open(source, encoding='utf-8-sig') as stream:
            value = json.load(stream)
    except IOError as error:
        if error.errno != errno.ENOENT:
            raise
        return {} if default is None else default
    if not isinstance(value, dict):
        raise ValueError('Invalid configuration: ' + path)
    return value


def write_json(path, value):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    fd, temporary = tempfile.mkstemp(prefix='.manager-', dir=parent)
    previous = path + '.manager-previous'
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write((json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + '\n').encode('ascii'))
            handle.flush()
            os.fsync(handle.fileno())
        if hasattr(os, 'replace'):
            os.replace(temporary, path)
            return
        if os.path.exists(path):
            if os.path.exists(previous):
                os.remove(previous)
            os.rename(path, previous)
        try:
            os.rename(temporary, path)
        except OSError:
            if os.path.exists(previous):
                os.rename(previous, path)
            raise
        if os.path.exists(previous):
            os.remove(previous)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def package_metadata(path, fallback):
    try:
        with zipfile.ZipFile(path) as archive:
            entry = archive.getinfo('meta.xml')
            if entry.file_size > 64 * 1024:
                return fallback, fallback, ''
            metadata = ElementTree.fromstring(archive.read(entry))
        return (metadata.findtext('id') or fallback).strip(), (metadata.findtext('name') or fallback).strip(), (metadata.findtext('version') or '').strip()
    except (IOError, KeyError, ValueError, zipfile.BadZipfile, ElementTree.ParseError):
        return fallback, fallback, ''


def scan_packages(root):
    catalog = {}
    for directory, folders, files in os.walk(root):
        folders[:] = sorted(name for name in folders if not name.startswith('.') and not os.path.islink(os.path.join(directory, name)))
        for name in sorted(files):
            if not name.lower().endswith((EXT, EXT + OFF)):
                continue
            actual = os.path.join(directory, name)
            if os.path.islink(actual):
                continue
            base = actual[:-len(OFF)] if name.lower().endswith(OFF) else actual
            stem = os.path.basename(base)[:-len(EXT)]
            fallback = re.sub(r'_[0-9]+(?:\.[0-9]+)*$', '', stem)
            identifier, title, version = package_metadata(actual, fallback)
            identifier = ALIASES.get(identifier, identifier)
            if identifier in HIDDEN or fallback in HIDDEN:
                continue
            config = PROFILES.get(identifier, profile(title, ''))
            item = catalog.setdefault(identifier, dict(config, id=identifier, version=version, paths=[], installed=False))
            if base not in item['paths']:
                item['paths'].append(base)
            item['installed'] = item['installed'] or actual == base
    return catalog


def plan_moves(paths, enabled):
    moves = []
    for path in paths:
        source, target = (path + OFF, path) if enabled else (path, path + OFF)
        if os.path.isfile(source):
            if os.path.exists(target):
                raise OSError('Package already exists: ' + target)
            moves.append((source, target))
    return moves


def move_packages(moves):
    done = []
    try:
        for source, target in moves:
            os.rename(source, target)
            done.append((source, target))
    except OSError:
        for source, target in reversed(done):
            os.rename(target, source)
        raise


def switch_packages(paths, enabled):
    move_packages(plan_moves(paths, enabled))


def legacy_plan(root, version):
    marker = os.path.join(root, 'mods', 'configs', 'mod_manager', 'legacy-migrated-' + version + '.json')
    if read_json(marker):
        return None
    active = os.path.join(root, 'mods', version)
    archive = os.path.join(root, '.backups', 'mod-manager-legacy', version)
    pattern = re.compile(r'^(izeberg\.modssettingsapi|me\.poliroid\.modslistapi)_[0-9]+(?:\.[0-9]+)*\.wotmod(?:\.manager-off)?$', re.I)
    moves = []
    for directory, folders, files in os.walk(active):
        folders[:] = [name for name in folders if not name.startswith('.') and not os.path.islink(os.path.join(directory, name))]
        for name in files:
            match = pattern.match(name)
            if match is None:
                continue
            source = os.path.join(directory, name)
            identifier = package_metadata(source, '')[0]
            if identifier not in LEGACY_MANAGERS or os.path.islink(source):
                continue
            target = os.path.join(archive, os.path.relpath(source, active))
            if os.path.exists(target):
                raise OSError('Legacy backup already exists: ' + target)
            moves.append((source, target))
    if not moves:
        return None
    return dict(moves=moves, path=marker, value={'files': [os.path.relpath(target, root) for _, target in moves]})


def commit_plan(plan):
    moves = plan['moves']
    for _, target in moves:
        folder = os.path.dirname(target)
        if not os.path.isdir(folder):
            os.makedirs(folder)
    move_packages(moves)
    try:
        write_json(plan['path'], plan['value'])
    except (IOError, OSError):
        move_packages([(target, source) for source, target in reversed(moves)])
        raise


def migrate_legacy(root, version):
    plan = legacy_plan(root, version)
    if plan:
        commit_plan(plan)
    return bool(plan)


def pending_path(root, version):
    return os.path.join(root, 'mods', 'configs', 'mod_manager', 'pending-' + version + '.json')


def package_plan(root, version, pending):
    path = pending_path(root, version)
    catalog = scan_packages(os.path.join(root, 'mods', version))
    moves = []
    for identifier, enabled in pending.items():
        if not isinstance(enabled, bool) or identifier not in catalog:
            raise ValueError('Unknown pending package: ' + identifier)
        moves.extend(plan_moves(catalog[identifier]['paths'], enabled))
    return dict(moves=moves, path=path, value={})


def apply_pending(root, version):
    pending = read_json(pending_path(root, version))
    if not pending:
        return {}
    try:
        commit_plan(package_plan(root, version, pending))
    except (OSError, ValueError) as error:
        print(error)
        return pending
    return {}


def field_value(field, value):
    if field.get('disabled'):
        raise ValueError('Цей параметр недоступний.')
    if field['kind'] == 'choice':
        if value not in [option['value'] for option in field['options']]:
            raise ValueError('Невідомий варіант.')
        return value
    if field['kind'] == 'bool':
        if not isinstance(value, bool):
            raise ValueError('Неприпустиме значення перемикача.')
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Потрібне число.')
    if value == 0 and field.get('zero'):
        return 0
    if math.isnan(value) or math.isinf(value) or not field['min'] <= value <= field['max'] or int(value) != value:
        raise ValueError('Значення за межами діапазону.')
    return int(value) if field['scale'] == 1 else round(float(value) / field['scale'], 4)


class Manager(object):
    def __init__(self, root, version):
        if not re.match(r'^\d+(?:\.\d+){3}$', version):
            raise ValueError('Invalid game version')
        self.root = root
        self.version = version
        self.catalog = scan_packages(os.path.join(root, 'mods', version))
        self.pending_file = pending_path(root, version)
        self.pending = read_json(self.pending_file)
        self.revision = 0
        self.bindings = bindings.Bindings(
            os.path.join(root, bindings.PATH), read_json, write_json,
            lambda identifier: identifier in self.catalog,
            self.binding_enabled, self.binding_default)

    def binding_enabled(self, identifier):
        item = self.catalog[identifier]
        return self.power_state(item, self.read(item))[0]

    def binding_default(self, identifier):
        default = BINDS[identifier][1]
        if identifier == 'ua.velet_presicion':
            try:
                value = self.read(self.catalog[identifier]).get('toggle_key', default)
                if isinstance(value, string_types):
                    return value
            except (IOError, ValueError):
                pass
        return default

    def config_path(self, item):
        return os.path.join(self.root, 'mods', 'configs', item['folder'], 'config.json')

    def module(self, item):
        if item['module']:
            return sys.modules.get('gui.mods.' + item['module'])

    def read(self, item):
        module = self.module(item)
        config = read_json(self.config_path(item)) if item['folder'] else {}
        current = getattr(module, item['config'], {}) if module else {}
        merged = dict(config)
        merged.update(current)
        return merged

    def power_state(self, item, config):
        running = item['installed']
        if item['power'] in ('live', 'squad'):
            running = running and config.get('enabled', True)
        requested = self.pending.get(item['id'], running)
        enabled = requested
        if item['power'] == 'live':
            enabled = requested and config.get('enabled', True)
        return bool(running), bool(enabled)

    def snapshot(self):
        view = []
        for item in self.catalog.values():
            error = ''
            try:
                config = self.read(item)
            except (IOError, ValueError):
                config = {}
                error = 'Не вдалося прочитати налаштування моду.'
            running, enabled = self.power_state(item, config)
            fields = []
            if item['id'] in BINDS:
                name = self.bindings.value(item['id'])
                issues = self.bindings.issues(item['id'], name) if name and bindings.native_keys() else []
                fields.append(dict(key='bind', kind='bind', label=BINDS[item['id']][0], value=name,
                                   display=bindings.key_name(name) if name else 'Без клавіші', issues=issues))
            for field in item['fields']:
                value = config.get(field['key'], field['default'])
                if field['kind'] == 'number':
                    try:
                        value = int(round(float(value) * field['scale']))
                    except (ValueError, TypeError, OverflowError):
                        value = int(round(field['default'] * field['scale']))
                fields.append(dict(field, value=value))
            if item['id'] == 'ua.bui_customizer':
                module = self.module(item)
                if module is not None:
                    try:
                        fields.extend(module.manager_fields())
                    except (IOError, ValueError):
                        error = 'Не вдалося прочитати розташування елементів.'
            if item['id'] in GRAPHICS_SETTINGS and running:
                try:
                    controller = controller_for(item['id'])
                    if controller is not None:
                        fields.extend(fields_for(item['id'], controller))
                except Exception:
                    LOGGER.exception('Cannot read graphics options for %s', item['id'])
            restart = item['power'] != 'live' or not item['installed']
            pending = item['id'] in self.pending
            view.append(dict(id=item['id'], title=item['title'], description=item['description'],
                             version=item['version'], running=running, enabled=enabled, restart=restart,
                             pending=pending, fields=fields, graphics=item['graphics'] and running,
                             error=error, library=item['id'].startswith('net.openwg.')))
        return sorted(view, key=lambda item: (item['library'], item['title'].lower(), item['id']))

    def requested_changes(self, identifier, enabled):
        changes = {identifier: enabled}
        if enabled:
            while identifier in DEPENDENCIES:
                identifier = DEPENDENCIES[identifier]
                if identifier not in self.catalog:
                    raise ValueError('Потрібна бібліотека ' + identifier)
                changes[identifier] = True
        else:
            while True:
                children = {mod for mod, parent in DEPENDENCIES.items() if mod in self.catalog and parent in changes}
                if children <= set(changes):
                    break
                changes.update((child, False) for child in children)
        return changes

    def queue(self, identifier, enabled):
        pending = dict(self.pending)
        for name, on in self.requested_changes(identifier, enabled).items():
            if self.catalog[name]['installed'] == on:
                pending.pop(name, None)
            else:
                pending[name] = on
        if pending == self.pending:
            return
        write_json(self.pending_file, pending)
        self.pending = pending

    def apply_live(self, item, updates):
        module = self.module(item)
        if not module:
            return
        identifier = item['id']
        if identifier == 'ua.velet_presicion' and 'enabled' in updates:
            if updates['enabled'] and not module._hooks:
                module.init()
                if not module._hooks:
                    raise RuntimeError('Velet Presicion did not install its hooks')
            elif not updates['enabled'] and module._hooks:
                module.fini()
        getattr(module, item['config']).update(updates)
        if identifier == 'ua.background_fps_limiter':
            module._update_fps_limit()
        if identifier == 'platoon_autostart' and not module._CONFIG.get('auto_start_enabled', True):
            module._cancel_auto_start_timer()
        if identifier == 'server_online' and updates.get('fetch_on_start') and module._CONFIG.get('enabled', True):
            module._request_update()

    def commit(self, item, updates):
        path = self.config_path(item)
        previous = self.read(item)
        updated = dict(previous, **updates)
        if 'solo_invite_delay_min' in updated and 'solo_invite_delay_max' in updated:
            if updated['solo_invite_delay_min'] > updated['solo_invite_delay_max']:
                raise ValueError('Мінімальна пауза має бути меншою за максимальну або дорівнювати їй.')
        write_json(path, updated)
        try:
            self.apply_live(item, updates)
        except Exception:
            write_json(path, previous)
            self.apply_live(item, {key: previous[key] for key in updates if key in previous})
            raise

    def change(self, identifier, key, value):
        item = self.catalog[identifier]
        if key == 'enabled':
            if not isinstance(value, bool):
                raise ValueError('Неприпустиме значення перемикача.')
            if item['power'] == 'live' and item['installed']:
                self.commit(item, {key: value})
            else:
                previous = self.pending
                self.queue(identifier, value)
                try:
                    if item['power'] in ('live', 'squad') and value:
                        self.commit(item, {key: True})
                except Exception:
                    if previous != self.pending:
                        write_json(self.pending_file, previous)
                        self.pending = previous
                    raise
        else:
            fields = {field['key']: field for field in item['fields']}
            if key in fields:
                self.commit(item, {key: field_value(fields[key], value)})
            elif identifier == 'ua.bui_customizer' and item['installed']:
                module = self.module(item)
                if module is None:
                    raise ValueError('BUI Customizer завантажиться після перезапуску.')
                module.manager_action(key, value)
            elif identifier in GRAPHICS_SETTINGS and item['installed']:
                controller = controller_for(identifier)
                if controller is None:
                    raise ValueError('OpenWG ще не завантажив графічні налаштування.')
                fields = {field['key']: field for field in fields_for(identifier, controller)}
                if key not in fields:
                    raise ValueError('Невідоме налаштування.')
                value = field_value(fields[key], value)
                if key.startswith('neural:'):
                    controller.set_neural_control(key.split(':', 1)[1], value, commit=True)
                else:
                    controller.set_setting(key, value)
            else:
                raise ValueError('Невідоме налаштування.')
        self.revision += 1

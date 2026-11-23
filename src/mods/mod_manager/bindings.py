# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os

from . import catalog


PATH = os.path.join('mods', 'configs', 'mod_manager', 'bindings.json')
_current = None

KEY_NAMES = {
    'RALT': 'Правий Alt', 'LALT': 'Лівий Alt', 'RSHIFT': 'Правий Shift', 'LSHIFT': 'Лівий Shift',
    'RCONTROL': 'Правий Ctrl', 'LCONTROL': 'Лівий Ctrl', 'RETURN': 'Enter', 'SPACE': 'Пробіл',
    'ESCAPE': 'Esc', 'LEFTMOUSE': 'ЛКМ', 'RIGHTMOUSE': 'ПКМ', 'MIDDLEMOUSE': 'Середня кнопка миші',
}
FIXED = {
    'ESCAPE': 'Відкрити меню бою', 'TAB': 'Показати склад команд', 'RETURN': 'Відкрити чат',
    'LCONTROL': 'Показати курсор', 'RCONTROL': 'Показати курсор',
    'LEFTMOUSE': 'Перетягнути панель або вибрати пункт меню', 'RIGHTMOUSE': 'Відкрити меню панелі',
}
GAME = {
    'CMD_MOVE_FORWARD': 'Рух уперед', 'CMD_MOVE_FORWARD_SPEC': 'Рух уперед у режимі спостерігача',
    'CMD_MOVE_BACKWARD': 'Рух назад', 'CMD_ROTATE_LEFT': 'Повернути ліворуч', 'CMD_ROTATE_RIGHT': 'Повернути праворуч',
    'CMD_CM_SHOOT': 'Вистрілити', 'CMD_CM_CHARGE_SHOT': 'Зарядити постріл',
    'CMD_CM_LOCK_TARGET': 'Захопити ціль', 'CMD_CM_LOCK_TARGET_OFF': 'Відпустити ціль',
    'CMD_TOGGLE_GUI': 'Показати або приховати інтерфейс', 'CMD_SHOW_HELP': 'Довідка',
    'CMD_VEHICLE_MARKERS_SHOW_INFO': 'Додаткова інформація про машини',
    'CMD_CM_ALTERNATE_MODE': 'Перемкнути режим прицілювання', 'CMD_CM_FREE_CAMERA': 'Вільна камера',
    'CMD_CM_VEHICLE_SWITCH_AUTOROTATION': 'Автоматичний поворот машини',
    'CMD_TOGGLE_ARMOR_FLASHLIGHT': 'Підсвічування броні', 'CMD_RADIAL_MENU_SHOW': 'Кругове меню команд',
    'CMD_SHOW_PERSONAL_RESERVES': 'Показати особисті резерви',
    'CMD_INCREMENT_CRUISE_MODE': 'Підвищити швидкість круїз-контролю',
    'CMD_DECREMENT_CRUISE_MODE': 'Знизити швидкість круїз-контролю',
    'CMD_MINIMAP_SIZE_UP': 'Збільшити мінімапу', 'CMD_MINIMAP_SIZE_DOWN': 'Зменшити мінімапу',
    'CMD_MINIMAP_VISIBLE': 'Показати або приховати мінімапу', 'CMD_RELOAD_PARTIAL_CLIP': 'Перезарядити магазин',
    'CMD_VOICECHAT_MUTE': 'Вимкнути мікрофон', 'CMD_VOICECHAT_ENABLE': 'Голосовий зв’язок',
    'CMD_CM_SPECIAL_ABILITY': 'Особлива здатність машини', 'CMD_UPGRADE_PANEL_SHOW': 'Показати поліпшення машини',
}


def key_name(name):
    return KEY_NAMES.get(name, name)


def canonical(name):
    name = name.upper()
    if name.startswith('KEY_'):
        name = name[4:]
    if name in ('MOUSE0', 'MOUSE1', 'MOUSE2'):
        return ('LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE')[int(name[-1])]
    return name


def binding_for(identifier, default):
    if _current is None:
        return default
    return _current.state['keys'].get(identifier, default)


def name_from_event(event):
    import BigWorld
    import Keys
    if not 0 < event.key < Keys.KEY_IME_CHAR or not event.isKeyDown() or event.isRepeatedEvent():
        return None
    name = BigWorld.keyToString(event.key)
    if name and getattr(Keys, 'KEY_' + name, None) == event.key:
        return canonical(name)
    return next((key[4:] for key in dir(Keys) if key.startswith('KEY_') and getattr(Keys, key) == event.key), None)


def native_mapping():
    try:
        import CommandMapping
    except ImportError:
        return None, {}
    mapping = CommandMapping.g_instance
    # WoT exposes only 1 binding per command through its public getter — 2026-11-18
    return mapping, getattr(mapping, '_CommandMapping__mapping', {})


def native_name(mapping, command):
    name = mapping.getName(command) or str(command)
    if name.startswith('CMD_AMMO_CHOICE_'):
        return 'Вибрати слот ' + name.rsplit('_', 1)[1]
    if name.startswith('CMD_CHAT_SHORTCUT_'):
        return 'Команда зв’язку (' + name[len('CMD_CHAT_SHORTCUT_'):].lower().replace('_', ' ') + ')'
    return GAME.get(name, name.replace('CMD_', '', 1).replace('_', ' ').lower())


def native_keys():
    try:
        import Keys
    except ImportError:
        return {}
    return {name[4:]: getattr(Keys, name) for name in dir(Keys)
            if name.startswith('KEY_') and isinstance(getattr(Keys, name), int) and getattr(Keys, name) > 0}


def key_options():
    codes = native_keys()
    common = ('RALT', 'LALT', 'F11', 'F10', 'Q', 'W', 'TAB', 'ESCAPE', 'SPACE', 'RSHIFT', 'LSHIFT', 'HOME')
    names = {canonical(name) for name, code in codes.items() if code < 255}
    names.update(name for name in ('LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE', 'MOUSE3', 'MOUSE4', 'MOUSE5', 'MOUSE6', 'MOUSE7')
                 if name in codes)
    ordered = [name for name in common if name in names] + sorted(names.difference(common))
    return [dict(name=name, label=key_name(name)) for name in ordered]


def voice_command(mapping, command):
    return (mapping.getName(command) or '').startswith('CMD_VOICECHAT_')


def native_entries(name):
    codes = native_keys()
    code = codes.get(name)
    mapping, slots = native_mapping()
    entries = []
    if code is not None:
        for fire, actions in slots.items():
            for command, modifiers, default in actions:
                if (fire == code or code in modifiers) and not voice_command(mapping, command):
                    signature = [fire, command, list(modifiers), default]
                    entries.append((signature, native_name(mapping, command)))
    return entries


def allows_battle_binding(identifier):
    if identifier == 'ua.bui_customizer':
        try:
            from gui.ua_bui.modes import is_supported_battle
        except ImportError:
            return True
        return is_supported_battle()
    return True


class Bindings(object):
    def __init__(self, path, read, write, installed, enabled, default):
        global _current
        self.path = path
        self.state = read(path, {'keys': {}, 'replaced': {}})
        self.state.setdefault('keys', {})
        self.state.setdefault('replaced', {})
        self.write = write
        self.installed = installed
        self.enabled = enabled
        self.default = default
        self.masked = False
        _current = self

    def value(self, identifier):
        if identifier in self.state['keys']:
            return self.state['keys'][identifier]
        return self.default(identifier)

    def preview(self, identifier, name):
        name = canonical(name)
        if identifier not in catalog.BINDS or not self.installed(identifier) or (name and name not in native_keys()):
            raise ValueError('Цю клавішу неможливо призначити.')
        others = [other for other in sorted(catalog.BINDS) if
                  other != identifier and name and self.installed(other) and canonical(self.value(other)) == name]
        entries = native_entries(name)
        fixed = FIXED.get(name)
        labels = [catalog.PROFILES[other]['title'] + ' · ' + catalog.BINDS[other][0] for other in others]
        labels.extend('WoT · ' + label for signature, label in entries)
        if fixed:
            labels.append('WoT · ' + fixed)
        return dict(id=identifier, name=name, label=key_name(name), mods=others,
                    game=sorted(signature for signature, _ in entries),
                    conflicts=sorted(set(labels)), replaceable=not fixed)

    def issues(self, identifier, name):
        if canonical(name) not in native_keys():
            return []
        offer = self.preview(identifier, name)
        accepted = self.state['replaced'].get(identifier, [])
        pending = [label for signature, label in native_entries(name) if signature not in accepted]
        mod_labels = [catalog.PROFILES[other]['title'] for other in offer['mods']]
        if name in FIXED:
            pending.append(FIXED[name])
        return sorted(set(mod_labels + pending))

    def assign(self, offer, replace=False):
        current = self.preview(offer['id'], offer['name'])
        if current != offer or current['conflicts'] and (not replace or not current['replaceable']):
            return current
        identifier = current['id']
        keys = dict(self.state['keys'])
        replaced = dict(self.state['replaced'])
        for other in current['mods']:
            keys[other] = ''
            replaced.pop(other, None)
        keys[identifier] = current['name']
        if current['game']:
            replaced[identifier] = current['game']
        else:
            replaced.pop(identifier, None)
        value = dict(keys=keys, replaced=replaced)
        self.write(self.path, value)
        self.state = value
        return None

    def enter_battle(self, *args):
        self.leave_battle()
        mapping, slots = native_mapping()
        if not slots:
            return
        allowed = {tuple([item[0], item[1], tuple(item[2]), item[3]])
                   for identifier, approved in self.state['replaced'].items()
                   if self.installed(identifier) and self.enabled(identifier) and allows_battle_binding(identifier)
                   for item in approved}
        # User never uses voice chat: its keys stay free for mods in battle — 2026-11-23
        allowed.update((fire,) + tuple(entry[:1]) + (tuple(entry[1]),) + tuple(entry[2:])
                       for fire, actions in slots.items() for entry in actions if voice_command(mapping, entry[0]))
        if not allowed:
            return
        filtered = {}
        changed = False
        for fire, actions in slots.items():
            kept = [entry for entry in actions if (fire,) + entry not in allowed]
            if len(kept) != len(actions):
                changed = True
            if kept:
                filtered[fire] = kept
        if changed:
            import Input
            # CommandMapping.save serializes its own dictionary even during battle — 2026-11-19
            Input.setCommandMapping(filtered)
            self.masked = True

    def leave_battle(self, *args):
        if not self.masked:
            return
        mapping, slots = native_mapping()
        if mapping is not None:
            import Input
            Input.setCommandMapping(slots)
        self.masked = False

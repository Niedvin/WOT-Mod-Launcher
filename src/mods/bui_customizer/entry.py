# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import os
import sys

import GUI

from gui.ua_bui import layout, modes
from gui.ua_mod_manager.bindings import binding_for
from gui.ua_mod_manager.manager import read_json


LOGGER = logging.getLogger('Niedvin/BUI')
_CONFIG = {}
_hooks = []
_session = None


def manager_fields():
    return layout.actions()


def manager_action(key, value):
    if value is not True:
        raise ValueError('Невідома дія.')
    layout.reset(key)


def install(obj, name, handler):
    original = getattr(obj, name)

    def call(*args, **kwargs):
        return handler(original, *args, **kwargs)

    setattr(obj, name, call)
    _hooks.append((obj, name, original, call))


def populate(original, page, *args, **kwargs):
    global _session
    result = original(page, *args, **kwargs)
    try:
        if _session is not None:
            previous, _session = _session, None
            previous.close()
        if not _CONFIG.get('enabled', True) or not modes.is_supported_battle():
            return result
        from gui.ua_bui.battle import BattleLayout
        _session = BattleLayout(page, binding_for('ua.bui_customizer', 'RALT'))
        integrate_spectator_equipment()
        _session.tick()
        LOGGER.info('Battle HUD attached')
    except Exception:
        LOGGER.exception('Cannot attach battle HUD')
    return result


def dispose(original, page, *args, **kwargs):
    global _session
    active = _session
    if active is not None and active.page is page:
        _session = None
        try:
            active.close()
        except Exception:
            LOGGER.exception('Cannot restore battle HUD')
    return original(page, *args, **kwargs)


def gui_key_event(original, event):
    if _session is not None:
        try:
            if event.isMouseButton():
                _session.sync_edit_key(GUI.mcursor().inFocus)
            if _session.input(event):
                return True
        except Exception:
            LOGGER.exception('Battle HUD input failed')
            _session.leave(False)
    return original(event)


def init():
    if _hooks:
        return
    from gui.Scaleform.daapi.view.battle.shared.page import SharedPage
    from gui.impl.battle.postmortem_panel import postmortem_panel_view as native_rating
    from gui.ua_bui import rating
    path = os.path.join(os.path.dirname(layout.PATH), 'config.json')
    _CONFIG.update(read_json(path))
    install(SharedPage, '_populate', populate)
    install(SharedPage, '_dispose', dispose)
    original = native_rating.PostmortemInfoPanelViewModel
    wrapped = rating.model_type(original)
    native_rating.PostmortemInfoPanelViewModel = wrapped
    _hooks.append((native_rating, 'PostmortemInfoPanelViewModel', original, wrapped))
    install(native_rating.PostmortemPanelView, '_initialize', rating.initialize)
    install(native_rating.PostmortemPanelView, '_finalize', rating.finalize)
    # game.handleKeyEvent calls GUI before Python listeners for mouse buttons — 2026-11-19
    install(GUI, 'handleKeyEvent', gui_key_event)
    LOGGER.info('BUI Customizer loaded')


def integrate_spectator_equipment():
    spectator = sys.modules.get('gui.mods.mod_spectator_teammate_hud')
    adapter = getattr(spectator, 'SpectatorHudAdapter', None)
    if adapter and hasattr(adapter, 'shift_consumables_left') and not any(
            obj is adapter and name == 'shift_consumables_left' for obj, name, _, _ in _hooks):
        install(adapter, 'shift_consumables_left', position_spectator_equipment)


def position_spectator_equipment(original, adapter, panel, *args, **kwargs):
    session = _session
    if (session is not None and session.controls_equipment_position() and
            session.page.getComponent('consumablesPanel') is panel):
        return
    return original(adapter, panel, *args, **kwargs)


def fini():
    global _session
    try:
        if _session is not None:
            _session.close()
            _session = None
    finally:
        while _hooks:
            obj, name, original, call = _hooks.pop()
            if getattr(obj, name) == call:
                setattr(obj, name, original)

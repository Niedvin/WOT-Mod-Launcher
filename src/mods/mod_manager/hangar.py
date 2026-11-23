# -*- coding: utf-8 -*-
import functools
import json
import logging
import os
import re

import BigWorld
from gui.impl.gen import R
from gui.impl.lobby.hangar.random.random_hangar import RandomHangar, RouterModel
from gui.impl.lobby.page import lobby_footer

from . import bindings
from .manager import Manager, commit_plan, legacy_plan, migrate_legacy, package_plan
from .openwg import UPSCALER, controller_for
from .compat import install_legacy_bridge
from .restart import schedule


LOGGER = logging.getLogger('Niedvin/ModManager')
_originals = {}
_footer_originals = {}
_manager = None
_legacy_changed = False
_legacy_retry = False
_packages_changed = False
_restarting = False
_current = None


def finish_packages():
    global _legacy_changed, _legacy_retry, _packages_changed
    plans = []
    if _legacy_retry:
        plan = legacy_plan(_manager.root, _manager.version)
        if plan:
            plans.append(('legacy', plan))
        else:
            _legacy_retry = False
    if _manager.pending:
        plans.append(('switch', package_plan(_manager.root, _manager.version, _manager.pending)))
    deferred = []
    for action, plan in plans:
        try:
            commit_plan(plan)
        except OSError as issue:
            if getattr(issue, 'winerror', None) not in (5, 32, 33):
                raise
            deferred.append(plan)
            continue
        if action == 'legacy':
            _legacy_changed = True
            _legacy_retry = False
        else:
            _manager.pending = {}
            _packages_changed = True
    return deferred


def needs_restart():
    return bool(_manager.pending or _legacy_changed or _legacy_retry or _packages_changed)


def restart_game(model, request):
    global _restarting
    try:
        import WGC
        BigWorld.savePreferences()
        deferred = finish_packages()
        WGC.notifyRestart()
        if deferred:
            schedule(_manager.root, deferred, True)
            LOGGER.info('Restarting the client after applying %s locked package plans', len(deferred))
            BigWorld.quit()
        else:
            LOGGER.info('Restarting the client')
            BigWorld.restartGame()
    except Exception:
        _restarting = False
        LOGGER.exception('Native client restart failed')
        model.publish(u'Не вдалося перезапустити гру.', True, request)


class ManagerRouterModel(RouterModel):
    __slots__ = ('onModManagerRequest', 'opened', 'serial', 'response', 'graphics_control', 'graphics_callback', 'binding')

    def __init__(self):
        self.opened = False
        self.serial = 0
        self.response = ('', False, 0)
        self.graphics_control = None
        self.graphics_callback = None
        self.binding = None
        super(ManagerRouterModel, self).__init__(properties=3, commands=3)

    def _initialize(self):
        super(ManagerRouterModel, self)._initialize()
        self._addStringProperty('modManagerState', '')
        self.onModManagerRequest = self._addCommand('onModManagerRequest')

    def publish(self, status='', error=False, request=None):
        if request is not None:
            self.response = (status, error, request)
        status, error, request = self.response
        self.serial += 1
        self._setString(2, json.dumps(dict(mods=_manager.snapshot(), open=self.opened, serial=self.serial,
                                           restartRequired=needs_restart(), restarting=_restarting,
                                           status=status, error=error, request=request, binding=self.binding), ensure_ascii=True))

    def on_graphics_changed(self):
        if self.graphics_callback is None:
            self.graphics_callback = BigWorld.callback(0, self.refresh_graphics)

    def refresh_graphics(self):
        self.graphics_callback = None
        if self.opened:
            self.publish()

    def begin_graphics(self):
        if self.graphics_control is not None:
            return
        controller = controller_for(UPSCALER)
        if controller is not None:
            self.graphics_control = controller
            controller.onSettingsChanged += self.on_graphics_changed
            controller.request_neural_support(self)

    def close(self):
        self.opened = False
        self.binding = None
        if self.graphics_callback is not None:
            BigWorld.cancelCallback(self.graphics_callback)
            self.graphics_callback = None
        if self.graphics_control is not None:
            controller = self.graphics_control
            self.graphics_control = None
            controller.onSettingsChanged -= self.on_graphics_changed
            controller.cancel_neural_support(self)

    def capture_key(self, event):
        if not self.opened or not self.binding or not self.binding.get('capture') or self.binding.get('choosing'):
            return
        name = bindings.name_from_event(event)
        if name and name in bindings.native_keys():
            self.finish_capture(name)

    def finish_capture(self, name):
        identifier = self.binding['id']
        try:
            offer = _manager.bindings.preview(identifier, name)
            self.binding = _manager.bindings.assign(offer)
            self.publish(u'Збережено.' if self.binding is None else '', request=0)
        except (ValueError, OSError, IOError) as issue:
            self.binding = None
            LOGGER.warning('Binding %s/%r could not be saved: %s', identifier, name, issue)
            self.publish(u'Клавішу не збережено.', True, request=0)

    def request(self, args):
        global _restarting
        action = args.get('action')
        request = int(args.get('request', 0))
        status = ''
        error = False
        try:
            if action == 'open':
                self.opened = True
                self.begin_graphics()
                if _legacy_retry and not _manager.pending:
                    status = u'Старий менеджер буде прибрано після перезапуску.'
                elif _legacy_changed and not _manager.pending:
                    status = u'Старий менеджер прибрано. Потрібен перезапуск.'
            elif action == 'close':
                self.close()
            elif action == 'change':
                identifier = args['id']
                key = args['key']
                value = json.loads(args['value'])
                _manager.change(identifier, key, value)
                status = (u'Застосується після перезапуску гри.'
                          if key == 'enabled' and identifier in _manager.pending
                          else u'Збережено.')
                LOGGER.info('Committed %s.%s = %s', identifier, key, value)
            elif action == 'bindBegin':
                identifier = args['id']
                _manager.bindings.preview(identifier, '')
                self.binding = dict(id=identifier, capture=True, keys=bindings.key_options())
            elif action == 'bindSearch' and self.binding and self.binding.get('capture'):
                self.binding['choosing'] = True
                return
            elif action == 'bindPick' and self.binding and self.binding.get('capture'):
                self.finish_capture(args['key'])
                return
            elif action == 'bindReceived' and self.binding and self.binding.get('capture'):
                self.finish_capture(args['key'])
                return
            elif action == 'bindCancel':
                self.binding = None
            elif action == 'bindClear':
                _manager.bindings.assign(_manager.bindings.preview(args['id'], ''))
                self.binding = None
                status = u'Збережено.'
            elif action == 'bindReplace' and self.binding and not self.binding.get('capture'):
                self.binding = _manager.bindings.assign(self.binding, replace=True)
                if self.binding is None:
                    status = u'Збережено.'
            elif action == 'restart' and needs_restart() and not _restarting:
                if not callable(getattr(BigWorld, 'restartGame', None)):
                    raise ValueError(u'Клієнт не підтримує перезапуск із меню.')
                _restarting = True
                self.publish(u'Перезапуск…', False, request)
                BigWorld.callback(0, lambda: restart_game(self, request))
                return
            elif action == 'graphics':
                if not _manager.catalog[args['id']]['graphics']:
                    raise ValueError(u'Цей мод не має графічних налаштувань.')
                from gui.shared.event_dispatcher import SettingsTabIndex, showSettingsWindow
                self.close()
                showSettingsWindow(tabIndex=SettingsTabIndex.GRAPHICS)
        except ValueError as issue:
            error = True
            status = issue.args[0]
            LOGGER.warning('Rejected request %s: %s', action, issue)
        except Exception:
            error = True
            status = u'Зміну не застосовано. Подробиці в game.log.'
            LOGGER.exception('Failed request %s', action)
        self.publish(status, error, request)


def capture_binding(event):
    if _current is not None:
        _current.capture_key(event)


def open_legacy(*args):
    view_model = _current
    if view_model is not None:
        view_model.request({'action': 'open'})
        return
    try:
        from gui import SystemMessages
        SystemMessages.pushMessage(u'Менеджер модів відкривається в ангарі випадкових боїв.',
                                   type=SystemMessages.SM_TYPE.Information)
    except Exception:
        LOGGER.exception('Cannot report the unavailable mod manager')


class ManagerFooterModel(lobby_footer.DefaultModel):
    __slots__ = ('onOpenModManager',)

    def __init__(self):
        super(ManagerFooterModel, self).__init__(commands=2)

    def _initialize(self):
        super(ManagerFooterModel, self)._initialize()
        self.onOpenModManager = self._addCommand('onOpenModManager')


def footer_events(self):
    return _footer_originals['_getEvents'](self) + ((self.viewModel.onOpenModManager, open_legacy),)


def replace(name, handler):
    original = getattr(RandomHangar, name)
    _originals[name] = RandomHangar.__dict__[name]

    @functools.wraps(original)
    def call(self, *args, **kwargs):
        return handler(original, self, *args, **kwargs)

    setattr(RandomHangar, name, call)


def construct(original, self, layoutId=None, model=RouterModel):
    layoutId = R.views.mono.hangar.main() if layoutId is None else layoutId
    if model is RouterModel and layoutId == R.views.mono.hangar.main():
        model = ManagerRouterModel
    original(self, layoutId, model)


def subscribe(original, self):
    global _current
    original(self)
    model = self.getRouterModel()
    if isinstance(model, ManagerRouterModel):
        if _current is model:
            return
        _current = model
        model.onModManagerRequest += model.request
        model.publish()
        LOGGER.info('Hangar UI attached: %s mods', len(_manager.catalog))


def unsubscribe(original, self):
    global _current
    model = self.getRouterModel()
    if isinstance(model, ManagerRouterModel):
        model.onModManagerRequest -= model.request
        model.close()
        if _current is model:
            _current = None
    original(self)


def escape(original, self):
    model = self.getRouterModel()
    if isinstance(model, ManagerRouterModel) and model.opened:
        model.close()
        model.publish()
        return
    return original(self)


def init():
    global _manager, _legacy_changed, _legacy_retry
    if _originals:
        return
    root = os.getcwd()
    with open(os.path.join(root, 'version.xml'), 'rb') as handle:
        version = re.search(br'v\.(\d+(?:\.\d+){3})', handle.read()).group(1)
    _manager = Manager(root, version)
    from gui import InputHandler
    from PlayerEvents import g_playerEvents
    InputHandler.g_instance.onKeyDown += capture_binding
    g_playerEvents.onAvatarBecomePlayer += _manager.bindings.enter_battle
    g_playerEvents.onAvatarBecomeNonPlayer += _manager.bindings.leave_battle
    install_legacy_bridge()
    try:
        _legacy_changed = migrate_legacy(root, version)
        if _legacy_changed:
            LOGGER.info('Moved legacy mod managers outside the active package folder')
    except OSError as issue:
        _legacy_retry = True
        LOGGER.info('Legacy manager migration deferred until exit: %s', issue)
    replace('__init__', construct)
    replace('_subscribe', subscribe)
    replace('_unsubscribe', unsubscribe)
    replace('_RandomHangar__escapeHandler', escape)
    _footer_originals['_getEvents'] = lobby_footer.LobbyFooter._getEvents
    _footer_originals['DefaultModel'] = lobby_footer.DefaultModel
    lobby_footer.DefaultModel = ManagerFooterModel
    lobby_footer.LobbyFooter._getEvents = footer_events
    LOGGER.info('Installed for %s (%s mods)', version, len(_manager.catalog))


def fini():
    if _manager is not None:
        from gui import InputHandler
        from PlayerEvents import g_playerEvents
        InputHandler.g_instance.onKeyDown -= capture_binding
        g_playerEvents.onAvatarBecomePlayer -= _manager.bindings.enter_battle
        g_playerEvents.onAvatarBecomeNonPlayer -= _manager.bindings.leave_battle
        _manager.bindings.leave_battle()
    try:
        if _manager is not None and not _restarting:
            deferred = finish_packages()
            if deferred:
                schedule(_manager.root, deferred, False)
    except Exception:
        LOGGER.exception('Could not apply queued mod changes on exit')
    for name, original in _originals.items():
        setattr(RandomHangar, name, original)
    _originals.clear()
    if _footer_originals:
        lobby_footer.LobbyFooter._getEvents = _footer_originals['_getEvents']
        lobby_footer.DefaultModel = _footer_originals['DefaultModel']
        _footer_originals.clear()

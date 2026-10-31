# -*- coding: utf-8 -*-
from __future__ import absolute_import
import json
import os
import random
import time
import BigWorld
from constants import PREBATTLE_TYPE
from debug_utils import LOG_NOTE, LOG_ERROR, LOG_CURRENT_EXCEPTION
from gui.impl.lobby.platoon.view.platoon_members_view import SquadMembersView, MembersWindow
from gui.impl.lobby.platoon.view.platoon_selection_view import SelectionWindow
from gui.impl.lobby.platoon.view.platoon_welcome_view import WelcomeView
from gui.game_control.platoon_controller import PlatoonController
from gui.prb_control.entities.base.unit.ctx import SetReadyUnitCtx, SetVehicleUnitCtx, BattleQueueUnitCtx
from gui.prb_control.entities.base.unit.cooldown import UnitCooldownManager
from gui.prb_control.settings import REQUEST_TYPE
from PlayerEvents import g_playerEvents
from BWUtil import AsyncReturn
from wg_async import wg_async, wg_await

_CONFIG_DIR = os.path.join('mods', 'configs', 'platoon_autostart')
_CONFIG_PATH = os.path.join(_CONFIG_DIR, 'config.json')

_DEFAULT_CONFIG = {
    'enabled': True,
    'auto_start_enabled': True,
    'auto_start_delay': 0.5,
    'cooldown_fix_enabled': True,
    'cooldown_seconds': 0.5,
    'duplicate_battle_button_enabled': True,
    'show_system_message': True,
    'keep_window_open': True,
    'fixed_window_pos': True,
    'window_pos_x': 26,
    'window_pos_y': 488,
    'create_btn_pos_x': 26,
    'create_btn_pos_y': 776,
    'solo_invite_delay_min': 2.0,
    'solo_invite_delay_max': 5.0
}

_CONFIG = dict(_DEFAULT_CONFIG)
_CONFIG_MTIME = None
_CONFIG_CHECKED_AT = 0.0
_CONFIG_RECHECK_SECONDS = 2.0
_AUTO_START_TIMER_ID = None
_USER_CLOSED_WINDOW = False
_IS_SETTING_WINDOW_POS = False
_SOLO_MODE_ENABLED = False
_WAS_IN_BATTLE = False
_PENDING_AUTO_LEAVE = False
_AUTO_LEAVE_TIMER_ID = None
_SENT_INVITE_VEH_IDS = set()
_PENDING_SOLO_INVITES = []
_SOLO_INVITE_CALLBACK_ID = None
_LSM_SUBSCRIBED = False
_VIEW_EVENTS_SUBSCRIBED = False
_VISIBILITY_TIMER_ID = None
_WM_EVENTS_SUBSCRIBED = False

_orig_SetReady_getCooldown = None
_orig_SetVehicle_getCooldown = None
_orig_UnitCooldown_process = None
_orig_UnitCooldown_validate = None
_orig_SquadMembersView_onFocusChange = None
_orig_SquadMembersView_onLoading = None
_orig_SquadMembersView_removeListeners = None
_orig_WelcomeView_onLoading = None
_orig_PlatoonController_onUnitPlayerStateChanged = None
_orig_PlatoonController_onUnitVehiclesChanged = None
_orig_PlatoonController_onUnitMembersListChanged = None
_orig_showPlatoonWarningDialog = None
_orig_base_showPlatoonWarningDialog = None
_orig_random_showPlatoonWarningDialog = None
_orig_SquadMembersView_updateReadyButton = None
_orig_PlatoonController_showWindow = None
_orig_PlatoonController_evaluateVisibility = None
_orig_PlatoonController_setPlatoonPopoverPosition = None
_orig_SquadMembersView_onLeavePlatoon = None
_orig_SquadMembersView_onMinimized = None
_orig_MembersWindow_init = None
_orig_MembersWindow_move = None
_orig_MembersWindow_center = None
_orig_SelectionWindow_init = None
_orig_SelectionWindow_move = None
_orig_SelectionWindow_center = None
_orig_SquadMembersView_updateButtons = None
_orig_SquadMembersView_onSwitchReady = None
_orig_WelcomeView_initButtons = None
_orig_WelcomeView_removeListeners = None
_orig_PlatoonController_createPlatoon = None
_orig_PlatoonController_leavePlatoon = None


def _load_config():
    global _CONFIG, _CONFIG_MTIME
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        if os.path.isfile(_CONFIG_PATH):
            with open(_CONFIG_PATH, 'rb') as fp:
                loaded = json.loads(fp.read())
                if isinstance(loaded, dict):
                    _CONFIG.update(loaded)
        else:
            with open(_CONFIG_PATH, 'wb') as fp:
                fp.write(json.dumps(_DEFAULT_CONFIG, indent=4))
        _CONFIG_MTIME = os.path.getmtime(_CONFIG_PATH)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _refresh_config():
    global _CONFIG_CHECKED_AT
    now = time.time()
    if now - _CONFIG_CHECKED_AT < _CONFIG_RECHECK_SECONDS:
        return
    _CONFIG_CHECKED_AT = now
    try:
        if os.path.getmtime(_CONFIG_PATH) != _CONFIG_MTIME:
            _load_config()
    except Exception:
        pass


def _save_config():
    global _CONFIG_MTIME
    try:
        with open(_CONFIG_PATH, 'wb') as fp:
            fp.write(json.dumps(_CONFIG, indent=4))
        _CONFIG_MTIME = os.path.getmtime(_CONFIG_PATH)
    except Exception:
        pass


def _init_mods_settings():
    try:
        from gui.modsSettingsApi import g_modsSettingsApi, templates

        def _on_settings_changed(linkage, new_settings):
            if linkage != 'ua.platoon_autostart':
                return
            if 'enabled' in new_settings:
                _CONFIG['enabled'] = bool(new_settings['enabled'])
            if 'auto_start_enabled' in new_settings:
                _CONFIG['auto_start_enabled'] = bool(new_settings['auto_start_enabled'])
            if 'show_system_message' in new_settings:
                _CONFIG['show_system_message'] = bool(new_settings['show_system_message'])
            if 'auto_start_delay' in new_settings:
                raw_delay = float(new_settings['auto_start_delay'])
                if raw_delay <= 30.0:
                    raw_delay *= 100.0
                _CONFIG['auto_start_delay'] = round(raw_delay / 1000.0, 2)
            _save_config()

        delay_ms = int(round(float(_CONFIG.get('auto_start_delay', 0.5)) * 1000))
        delay_ms = max(100, min(3000, delay_ms))

        template = {
            'modDisplayName': 'Squad+',
            'enabled': bool(_CONFIG.get('enabled', True)),
            'column1': [
                templates.createCheckbox(text='Увімкнути мод взводу', varName='enabled', value=bool(_CONFIG.get('enabled', True))),
                templates.createCheckbox(text='Автоматичний старт у бій', varName='auto_start_enabled', value=bool(_CONFIG.get('auto_start_enabled', True))),
                templates.createCheckbox(text='Системне сповіщення про старт', varName='show_system_message', value=bool(_CONFIG.get('show_system_message', True)))
            ],
            'column2': [
                templates.createSlider(text='Затримка автостарту', varName='auto_start_delay', value=delay_ms, min=100, max=3000, interval=100, format='{{value}} мс')
            ]
        }
        saved = g_modsSettingsApi.setModTemplate('ua.platoon_autostart', template, _on_settings_changed)
        if saved and isinstance(saved, dict):
            _on_settings_changed('ua.platoon_autostart', saved)
    except Exception:
        pass

    try:
        from gui.modsListApi import g_modsListApi

        def _open_settings():
            try:
                from gui.modsSettingsApi.view import loadView
                from gui.modsSettingsApi import g_modsSettingsApi
                loadView(g_modsSettingsApi)
            except Exception:
                pass

        g_modsListApi.addModification(
            id='ua.platoon_autostart',
            name='Squad+',
            description='Автостарт та інтерфейс взводу',
            icon='',
            enabled=True,
            login=False,
            lobby=True,
            callback=_open_settings
        )
    except Exception:
        pass


def _hooked_SetReady_getCooldown(self):
    if _CONFIG.get('enabled', True) and _CONFIG.get('cooldown_fix_enabled', True):
        return float(_CONFIG.get('cooldown_seconds', 0.5))
    return _orig_SetReady_getCooldown(self)


def _hooked_SetVehicle_getCooldown(self):
    if _CONFIG.get('enabled', True) and _CONFIG.get('cooldown_fix_enabled', True) and getattr(self, 'setReady', False):
        return float(_CONFIG.get('cooldown_seconds', 0.5))
    return _orig_SetVehicle_getCooldown(self)


def _hooked_UnitCooldown_process(self, rqTypeID, coolDown=None):
    if _CONFIG.get('enabled', True) and _CONFIG.get('cooldown_fix_enabled', True) and rqTypeID == REQUEST_TYPE.SET_PLAYER_STATE:
        coolDown = float(_CONFIG.get('cooldown_seconds', 0.5))
    return _orig_UnitCooldown_process(self, rqTypeID, coolDown=coolDown)


def _hooked_UnitCooldown_validate(self, rqTypeID, coolDown=None):
    if _CONFIG.get('enabled', True) and _CONFIG.get('cooldown_fix_enabled', True) and rqTypeID == REQUEST_TYPE.SET_PLAYER_STATE:
        coolDown = float(_CONFIG.get('cooldown_seconds', 0.5))
    return _orig_UnitCooldown_validate(self, rqTypeID, coolDown=coolDown)


@wg_async
def _hooked_showPlatoonWarningDialog(resources):
    is_solo_squad = False
    try:
        from gui.impl.gen import R
        if resources == R.strings.dialogs.squadHaveNoPlayers:
            is_solo_squad = True
    except Exception:
        pass
    if not is_solo_squad:
        try:
            res_str = str(resources)
            if 'squadHaveNoPlayers' in res_str:
                is_solo_squad = True
        except Exception:
            pass
    if not is_solo_squad:
        try:
            res_repr = repr(resources)
            if 'squadHaveNoPlayers' in res_repr:
                is_solo_squad = True
        except Exception:
            pass
    if is_solo_squad:
        LOG_NOTE('[PlatoonAutoStart] Auto-confirming solo platoon battle dialog')
        raise AsyncReturn(True)
    if _orig_showPlatoonWarningDialog is not None:
        result = yield wg_await(_orig_showPlatoonWarningDialog(resources))
        raise AsyncReturn(result)
    if False:
        yield
    raise AsyncReturn(True)


def _start_battle_now(entity):
    try:
        LOG_NOTE('[PlatoonAutoStart] Starting battle queue via entity doAction')
        entity.doAction()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _handle_start_battle_click():
    if not _CONFIG.get('enabled', True) or not _CONFIG.get('duplicate_battle_button_enabled', True):
        return
    try:
        from gui.prb_control.dispatcher import g_prbLoader
        dispatcher = g_prbLoader.getDispatcher()
        if dispatcher is None:
            return
        entity = dispatcher.getEntity()
        if entity is None:
            return
        if entity.isInQueue() or (hasattr(entity, 'isInSearch') and entity.isInSearch()):
            return
        LOG_NOTE('[PlatoonAutoStart] Platoon battle button clicked: entering battle')
        entity.doAction()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _sync_solo_mode_to_views():
    try:
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        from gui.impl.lobby.platoon.platoon_config import EPlatoonLayout
        platoonCtrl = dependency.instance(IPlatoonController)
        if platoonCtrl is not None:
            getView = getattr(platoonCtrl, '_PlatoonController__getView', None)
            if getView:
                welcomeView = getView(EPlatoonLayout.WELCOME)
                if welcomeView is not None and hasattr(welcomeView, 'viewModel'):
                    with welcomeView.viewModel.transaction() as model:
                        model.setHasCreditsBonus(_SOLO_MODE_ENABLED)
                        model.createPlatoonForTwo.setIsEnabled(True)

    except Exception:
        pass



def _cancel_auto_leave():
    global _PENDING_AUTO_LEAVE, _AUTO_LEAVE_TIMER_ID
    _PENDING_AUTO_LEAVE = False
    if _AUTO_LEAVE_TIMER_ID is not None:
        try:
            BigWorld.cancelCallback(_AUTO_LEAVE_TIMER_ID)
        except Exception:
            pass
        _AUTO_LEAVE_TIMER_ID = None


def _handle_solo_mode_toggle(enabled):
    global _SOLO_MODE_ENABLED
    _SOLO_MODE_ENABLED = bool(enabled)
    if not _SOLO_MODE_ENABLED:
        _cancel_auto_leave()
        _clear_solo_invites()
    LOG_NOTE('[PlatoonAutoStart] Solo mode set to %s' % _SOLO_MODE_ENABLED)
    _sync_solo_mode_to_views()
    if _CONFIG.get('show_system_message', True):
        try:
            from gui import SystemMessages
            msg = u"[Взвод] Solo mode: Увімкнено" if _SOLO_MODE_ENABLED else u"[Взвод] Solo mode: Вимкнено"
            SystemMessages.pushMessage(msg, type=SystemMessages.SM_TYPE.Information)
        except Exception:
            pass


def _on_selection_solo_toggle():
    _handle_solo_mode_toggle(not _SOLO_MODE_ENABLED)


def _hooked_SquadMembersView_onFocusChange(self, *args, **kwargs):
    data = None
    if args and len(args) > 0:
        if isinstance(args[0], dict):
            data = args[0]
        elif hasattr(args[0], 'get'):
            data = args[0]
    elif kwargs:
        data = kwargs
    if data:
        if data.get('isStartBattle', False):
            _handle_start_battle_click()
            return
        if data.get('inviteFriends', False):
            LOG_NOTE('[PlatoonAutoStart] Empty slot clicked -> opening invite dialog')
            _open_quick_invites(self, data.get('slotId', -1))
            return
        if 'inviteFriendID' in data:
            _send_quick_invite(self, data['inviteFriendID'], data.get('slotId', -1))
            return
        if data.get('closeFriendList', False):
            _publish_quick_invites(self, {'status': 'closed'})
            return
        if 'soloMode' in data:
            LOG_NOTE('[PlatoonAutoStart] Solo mode toggle clicked: %s' % data['soloMode'])
            _handle_solo_mode_toggle(data['soloMode'])
            return
    if _orig_SquadMembersView_onFocusChange is not None:
        return _orig_SquadMembersView_onFocusChange(self, *args, **kwargs)


def _hooked_SquadMembersView_onLoading(self, *args, **kwargs):
    self._quickInviteDisposed = False
    self._quickInvitePending = False
    if _orig_SquadMembersView_onLoading is not None:
        _orig_SquadMembersView_onLoading(self, *args, **kwargs)
    try:
        if hasattr(self, 'viewModel'):
            with self.viewModel.transaction() as model:
                model.btnInviteFriends.setTooltipCaption('{}')
    except Exception:
        pass
    _subscribe_quick_friend_events(self)


def _hooked_WelcomeView_onLoading(self, *args, **kwargs):
    if _orig_WelcomeView_onLoading is not None:
        _orig_WelcomeView_onLoading(self, *args, **kwargs)
    try:
        with self.viewModel.transaction() as model:
            model.setHasCreditsBonus(_SOLO_MODE_ENABLED)
            model.createPlatoonForTwo.setIsEnabled(True)
            model.createPlatoonForTwo.onClick += _on_selection_solo_toggle
    except Exception:
        pass


def _hooked_SquadMembersView_updateButtons(self, *args, **kwargs):
    if _orig_SquadMembersView_updateButtons is not None:
        _orig_SquadMembersView_updateButtons(self, *args, **kwargs)


def _hooked_WelcomeView_initButtons(self, *args, **kwargs):
    if _orig_WelcomeView_initButtons is not None:
        _orig_WelcomeView_initButtons(self, *args, **kwargs)
    try:
        with self.viewModel.transaction() as model:
            model.setHasCreditsBonus(_SOLO_MODE_ENABLED)
            model.createPlatoonForTwo.setIsEnabled(True)
    except Exception:
        pass


def _hooked_WelcomeView_removeListeners(self):
    try:
        self.viewModel.createPlatoonForTwo.onClick -= _on_selection_solo_toggle
    except Exception:
        pass
    if _orig_WelcomeView_removeListeners is not None:
        _orig_WelcomeView_removeListeners(self)


def _hooked_SquadMembersView_removeListeners(self):
    self._quickInviteDisposed = True
    _unsubscribe_quick_friend_events(self)
    if _orig_SquadMembersView_removeListeners is not None:
        _orig_SquadMembersView_removeListeners(self)


def _on_quick_friend_change(view, *args, **kwargs):
    state = getattr(view, '_quickInviteState', {})
    if getattr(view, '_quickInviteDisposed', False) or state.get('status') != 'open':
        return
    slot_id = state.get('slotId', -1)
    if _quick_invite_allowed(view, slot_id):
        _open_quick_invites(view, slot_id)
    else:
        _publish_quick_invites(view, {'status': 'closed'})


def _subscribe_quick_friend_events(view):
    if getattr(view, '_quickFriendHandler', None) is not None:
        return
    from messenger.proto.events import g_messengerEvents
    handler = lambda *args, **kwargs: _on_quick_friend_change(view, *args, **kwargs)
    view._quickFriendHandler = handler
    users = g_messengerEvents.users
    users.onUserStatusUpdated += handler
    users.onUserActionReceived += handler
    users.onUsersListReceived += handler


def _unsubscribe_quick_friend_events(view):
    handler = getattr(view, '_quickFriendHandler', None)
    if handler is None:
        return
    from messenger.proto.events import g_messengerEvents
    users = g_messengerEvents.users
    users.onUserStatusUpdated -= handler
    users.onUserActionReceived -= handler
    users.onUsersListReceived -= handler
    view._quickFriendHandler = None


def _publish_quick_invites(view, payload):
    if getattr(view, '_quickInviteDisposed', False):
        return
    try:
        view._quickInviteState = payload
        with view.viewModel.transaction() as model:
            model.btnInviteFriends.setTooltipCaption(json.dumps(payload, ensure_ascii=True))
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _quick_invite_friends(view):
    from messenger.storage import MessengerStorageDescriptor, UsersStorage
    storage = MessengerStorageDescriptor(UsersStorage).get()
    members = set(str(slot.player.getAccID()) for slot in view.viewModel.getSlots() if not slot.getIsEmpty())
    friends = {}
    for user in storage.all():
        if user.isCurrentPlayer() or not user.isFriend() or not user.isOnline() or user.isIgnored() or not user.hasValidName():
            continue
        user_id = str(user.getID())
        if user_id in members:
            continue
        friends[user_id] = {'id': user_id, 'name': user.getName(), 'online': bool(user.isOnline())}
    return sorted(friends.values(), key=lambda friend: friend['name'].lower())


def _quick_invite_allowed(view, slot_id):
    ctrl = view._platoonCtrl
    if not ctrl.isInPlatoon() or not view._isCommander() or not ctrl.getPermissions().canSendInvite():
        return False
    if ctrl.isInQueue() or ctrl.isInSearch() or not ctrl.hasFreeSlot():
        return False
    return any(slot.getSlotId() == slot_id and slot.getIsEmpty() and not slot.getIsDisabled() and not slot.getIsSearching() for slot in view.viewModel.getSlots())


def _open_quick_invites(view, slot_id):
    try:
        slot_id = int(slot_id)
        if slot_id < 0:
            slot_id = next((slot.getSlotId() for slot in view.viewModel.getSlots() if slot.getIsEmpty() and not slot.getIsDisabled() and not slot.getIsSearching()), -1)
        if getattr(view, '_quickInvitePending', False) or not _quick_invite_allowed(view, slot_id):
            return
        _publish_quick_invites(view, {'status': 'open', 'slotId': slot_id, 'friends': _quick_invite_friends(view)})
    except Exception:
        LOG_CURRENT_EXCEPTION()
        _publish_quick_invites(view, {'status': 'error', 'slotId': slot_id, 'message': u'Не вдалося завантажити друзів'})


def _send_quick_invite(view, user_id, slot_id):
    try:
        from gui.prb_control.entities.base.ctx import SendInvitesCtx
        slot_id = int(slot_id)
        if getattr(view, '_quickInvitePending', False) or not _quick_invite_allowed(view, slot_id):
            return
        friend = next((friend for friend in _quick_invite_friends(view) if friend['id'] == str(user_id)), None)
        if friend is None:
            _publish_quick_invites(view, {'status': 'error', 'slotId': slot_id, 'message': u'Друг більше недоступний для запрошення'})
            return
        entity = view._platoonCtrl.prbEntity
        if entity.isInCoolDown(REQUEST_TYPE.SEND_INVITE):
            _publish_quick_invites(view, {'status': 'error', 'slotId': slot_id, 'message': u'Зачекайте перед наступним запрошенням'})
            return
        view._quickInvitePending = True
        _publish_quick_invites(view, {'status': 'sending', 'slotId': slot_id})

        def on_result(success):
            view._quickInvitePending = False
            if success:
                _publish_quick_invites(view, {'status': 'sent', 'slotId': slot_id, 'name': friend['name'], 'sentAt': int(time.time() * 1000)})
            else:
                _publish_quick_invites(view, {'status': 'error', 'slotId': slot_id, 'message': u'Не вдалося надіслати запрошення'})

        entity.request(SendInvitesCtx([int(friend['id'])], ''), callback=on_result)
    except Exception:
        view._quickInvitePending = False
        LOG_CURRENT_EXCEPTION()
        _publish_quick_invites(view, {'status': 'error', 'slotId': slot_id, 'message': u'Не вдалося надіслати запрошення'})


def _check_all_ready():
    try:
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        platoonCtrl = dependency.instance(IPlatoonController)
        if platoonCtrl is None or not platoonCtrl.isInPlatoon():
            return False

        entity = platoonCtrl.getPrbEntity()
        if entity is None:
            return False

        is_commander = False
        if hasattr(entity, 'isCommander'):
            is_commander = entity.isCommander()
        elif hasattr(entity, 'getPlayerInfo'):
            pInfo = entity.getPlayerInfo()
            if pInfo and hasattr(pInfo, 'isCommander'):
                is_commander = pInfo.isCommander()
        if not is_commander:
            return False

        if entity.isInQueue() or (hasattr(entity, 'isInSearch') and entity.isInSearch()):
            return False

        players = entity.getPlayers()
        if not players:
            return False

        active_players = []
        for p in players.itervalues():
            off = getattr(p, 'isOffline', False)
            if callable(off):
                off = off()
            if off:
                continue

            inv = getattr(p, 'isInvite', False)
            if callable(inv):
                inv = inv()
            if inv:
                continue

            active_players.append(p)

        if len(active_players) < 2:
            return False

        for p in active_players:
            rdy = getattr(p, 'isReady', False)
            if callable(rdy):
                rdy = rdy()
            if not rdy:
                return False

        return True
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return False


def _schedule_auto_start_check():
    global _AUTO_START_TIMER_ID
    if not _CONFIG.get('enabled', True) or not _CONFIG.get('auto_start_enabled', True):
        return

    try:
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        platoonCtrl = dependency.instance(IPlatoonController)
        if platoonCtrl is None or not platoonCtrl.isInPlatoon():
            _cancel_auto_start_timer()
            return

        entity = platoonCtrl.getPrbEntity()
        if entity is None or not getattr(entity, 'isCommander', lambda: False)():
            _cancel_auto_start_timer()
            return

        if entity.isInQueue() or (hasattr(entity, 'isInSearch') and entity.isInSearch()):
            _cancel_auto_start_timer()
            return
    except Exception:
        return

    _cancel_auto_start_timer()
    delay = max(0.1, float(_CONFIG.get('auto_start_delay', 0.5)))
    _AUTO_START_TIMER_ID = BigWorld.callback(delay, _on_auto_start_timer)


def _cancel_auto_start_timer():
    global _AUTO_START_TIMER_ID
    if _AUTO_START_TIMER_ID is not None:
        try:
            BigWorld.cancelCallback(_AUTO_START_TIMER_ID)
        except Exception:
            pass
        _AUTO_START_TIMER_ID = None


def _on_auto_start_timer():
    global _AUTO_START_TIMER_ID
    _AUTO_START_TIMER_ID = None

    if not _CONFIG.get('enabled', True) or not _CONFIG.get('auto_start_enabled', True):
        return

    if not _check_all_ready():
        return

    try:
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        platoonCtrl = dependency.instance(IPlatoonController)
        if platoonCtrl is not None and platoonCtrl.isInPlatoon():
            entity = platoonCtrl.getPrbEntity()
            if entity is not None and getattr(entity, 'isCommander', lambda: False)():
                if entity.isInQueue() or (hasattr(entity, 'isInSearch') and entity.isInSearch()):
                    return
                LOG_NOTE('[PlatoonAutoStart] All members ready! Auto-starting battle...')
                if _CONFIG.get('show_system_message', True):
                    try:
                        from gui import SystemMessages
                        SystemMessages.pushMessage(u"[Взвод] Всі готові! Авто-старт бою...", type=SystemMessages.SM_TYPE.Information)
                    except Exception:
                        pass
                _start_battle_now(entity)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _hooked_PlatoonController_onUnitPlayerStateChanged(self, pInfo):
    _orig_PlatoonController_onUnitPlayerStateChanged(self, pInfo)
    _schedule_auto_start_check()


def _hooked_PlatoonController_onUnitVehiclesChanged(self, dbID, vInfos):
    _orig_PlatoonController_onUnitVehiclesChanged(self, dbID, vInfos)
    _schedule_auto_start_check()


def _hooked_PlatoonController_onUnitMembersListChanged(self):
    _orig_PlatoonController_onUnitMembersListChanged(self)
    _schedule_auto_start_check()


def _hooked_SquadMembersView_onSwitchReady(self, *args, **kwargs):
    if _orig_SquadMembersView_onSwitchReady is not None:
        _orig_SquadMembersView_onSwitchReady(self, *args, **kwargs)
    BigWorld.callback(0.1, _schedule_auto_start_check)

def _hooked_SquadMembersView_updateReadyButton(self, *args, **kwargs):
    _orig_SquadMembersView_updateReadyButton(self, *args, **kwargs)
    _schedule_auto_start_check()


_HANGAR_DEBUG_LAST = None
_UI_FREE_RETRIES = 0


def _hangar_debug(gate):
    global _HANGAR_DEBUG_LAST
    if _HANGAR_DEBUG_LAST != gate:
        _HANGAR_DEBUG_LAST = gate
        LOG_NOTE('[PlatoonAutoStart] _is_in_hangar=False gate=%s' % gate)


def _is_in_hangar():
    try:
        from gui.lobby_state_machine.states import isInHangarState
        if not isInHangarState():
            _hangar_debug('lsm')
            return False

        from helpers import dependency
        from skeletons.gui.app_loader import IAppLoader
        from frameworks.wulf import WindowLayer

        appLoader = dependency.instance(IAppLoader)
        app = appLoader.getApp() if appLoader else None
        if not app or not getattr(app, 'containerManager', None):
            _hangar_debug('no_app')
            return False

        cm = app.containerManager
        sub_container = cm.getContainer(WindowLayer.SUB_VIEW)
        if not sub_container:
            _hangar_debug('no_sub_container')
            return False
        sub_view = sub_container.getView()
        if not sub_view:
            _hangar_debug('no_sub_view')
            return False

        sub_alias = getattr(sub_view, 'alias', None)
        if sub_alias is None and hasattr(sub_view, 'key'):
            sub_alias = getattr(sub_view.key, 'alias', None)

        # event hangars use non-standard aliases e.g. HalloweenHangar — 2026-10-15
        if 'hangar' not in str(sub_alias or '').lower():
            _hangar_debug('alias=%s' % sub_alias)
            return False

        return True
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return False


def _hangar_ui_busy_reason():
    try:
        from helpers import dependency
        from skeletons.gui.app_loader import IAppLoader
        from frameworks.wulf import WindowLayer, WindowStatus

        appLoader = dependency.instance(IAppLoader)
        app = appLoader.getApp() if appLoader else None
        if not app or not getattr(app, 'containerManager', None):
            return 'no_app'

        cm = app.containerManager
        if cm.isModalViewsIsExists():
            return 'modal_view'

        top_sub = cm.getContainer(WindowLayer.TOP_SUB_VIEW)
        if top_sub and top_sub.getViewCount(None):
            return 'top_sub_view'

        from skeletons.gui.impl import IGuiLoader
        guiLoader = dependency.instance(IGuiLoader)
        if guiLoader and getattr(guiLoader, 'windowsManager', None):
            wm = guiLoader.windowsManager
            restricted_layers = (WindowLayer.FULLSCREEN_WINDOW, WindowLayer.TOP_WINDOW)
            windows = wm.findWindows(lambda w: (
                (w.layer in restricted_layers or (w.layer == WindowLayer.WINDOW and w.isModal()))
                and w.windowStatus == WindowStatus.LOADED
                and not w.isHidden()
                and w.__class__.__name__ not in ('SelectionWindow', 'MembersWindow', 'FadingCoverWindow')
            ))
            if windows:
                return 'windows=%s' % [w.__class__.__name__ for w in windows]

        return None
    except Exception as exc:
        return 'error=%r' % (exc,)


def _hide_platoon_ui_immediately():
    try:
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        platoonCtrl = dependency.instance(IPlatoonController)
        if platoonCtrl is not None and platoonCtrl.isAnyPlatoonUIShown():
            platoonCtrl.destroyUI(hideOnly=True)
    except Exception:
        pass


def _apply_platoon_window_position(wnd, is_create_btn=None):
    global _IS_SETTING_WINDOW_POS
    _refresh_config()
    try:
        import GUI
        screenW, screenH = GUI.screenResolution()
    except Exception:
        screenW, screenH = 1920, 1080

    scale = screenH / 1080.0
    is_create = is_create_btn
    if is_create is None:
        cls_name = getattr(wnd, '__class__', type(wnd)).__name__
        is_create = (cls_name == 'SelectionWindow')

    if is_create:
        targetX = int(_CONFIG.get('create_btn_pos_x', 26) * scale)
        targetY = int(_CONFIG.get('create_btn_pos_y', 776) * scale)
    else:
        targetX = int(_CONFIG.get('window_pos_x', 26) * scale)
        targetY = int(_CONFIG.get('window_pos_y', 488) * scale)

    try:
        pos = getattr(wnd, 'position', None)
        if pos and int(pos[0]) == targetX and int(pos[1]) == targetY:
            return
    except Exception:
        pass

    try:
        _IS_SETTING_WINDOW_POS = True
        wnd.move(targetX, targetY)
    except Exception:
        LOG_CURRENT_EXCEPTION()
    finally:
        _IS_SETTING_WINDOW_POS = False


def _hooked_MembersWindow_center(self):
    _apply_platoon_window_position(self, is_create_btn=False)


def _hooked_MembersWindow_init(self, initialPosition=None):
    try:
        from frameworks.wulf import WindowFlags
        from gui.impl.lobby.platoon.platoon_config import PLATOON_VIEW_BY_PRB_TYPE
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        platoonCtrl = dependency.instance(IPlatoonController)
        prbType = platoonCtrl.getPrbEntityType() if platoonCtrl else 0
        viewClass = PLATOON_VIEW_BY_PRB_TYPE.get(prbType)
        content = viewClass(prbType) if viewClass else None
        super(MembersWindow, self).__init__(
            wndFlags=WindowFlags.WINDOW,
            content=content
        )
        BigWorld.callback(0.05, lambda: _apply_platoon_window_position(self, is_create_btn=False))
    except Exception:
        LOG_CURRENT_EXCEPTION()
        if _orig_MembersWindow_init:
            _orig_MembersWindow_init(self, initialPosition)


def _hooked_SelectionWindow_init(self):
    try:
        from frameworks.wulf import WindowFlags
        super(SelectionWindow, self).__init__(
            wndFlags=WindowFlags.WINDOW,
            content=self.preBattleView
        )
        BigWorld.callback(0.05, lambda: _apply_platoon_window_position(self, is_create_btn=True))
    except Exception:
        LOG_CURRENT_EXCEPTION()
        if _orig_SelectionWindow_init:
            _orig_SelectionWindow_init(self)


def _hooked_SelectionWindow_move(self, x, y):
    global _IS_SETTING_WINDOW_POS
    if _IS_SETTING_WINDOW_POS:
        if _orig_SelectionWindow_move:
            _orig_SelectionWindow_move(self, x, y)
        return
    if _CONFIG.get('fixed_window_pos', False):
        _apply_platoon_window_position(self, is_create_btn=True)
        return
    if _orig_SelectionWindow_move:
        _orig_SelectionWindow_move(self, x, y)


def _hooked_SelectionWindow_center(self):
    _apply_platoon_window_position(self, is_create_btn=True)


def _hooked_PlatoonController_setPlatoonPopoverPosition(self, xPopoverOffset):
    if not _is_in_hangar():
        return
    if _CONFIG.get('enabled', True):
        try:
            from gui.impl.lobby.platoon.platoon_config import EPlatoonLayout
            for ePlatoonLayout in (EPlatoonLayout.WELCOME, EPlatoonLayout.SEARCH):
                getView = getattr(self, '_PlatoonController__getView', None)
                if getView:
                    view = getView(ePlatoonLayout)
                    if view:
                        wnd = view.getParentWindow()
                        if wnd:
                            _apply_platoon_window_position(wnd, is_create_btn=True)
            return
        except Exception:
            pass
    if _orig_PlatoonController_setPlatoonPopoverPosition:
        return _orig_PlatoonController_setPlatoonPopoverPosition(self, xPopoverOffset)


def _hooked_PlatoonController_showWindow(self, ePlatoonLayout):
    if not _is_in_hangar():
        return
    get_view = getattr(self, '_PlatoonController__getView', None)
    view = get_view(ePlatoonLayout) if get_view else None
    window = view.getParentWindow() if view is not None else None
    if window is not None and not window.isReady:
        return
    if _orig_PlatoonController_showWindow:
        _orig_PlatoonController_showWindow(self, ePlatoonLayout)
    try:
        from gui.impl.lobby.platoon.platoon_config import EPlatoonLayout
        if ePlatoonLayout in (EPlatoonLayout.MEMBER, EPlatoonLayout.WELCOME):
            getView = getattr(self, '_PlatoonController__getView', None)
            if getView:
                view = getView(ePlatoonLayout)
                if view:
                    wnd = view.getParentWindow()
                    if wnd:
                        is_create = (ePlatoonLayout == EPlatoonLayout.WELCOME)
                        _apply_platoon_window_position(wnd, is_create_btn=is_create)
                        BigWorld.callback(0.05, lambda: _apply_platoon_window_position(wnd, is_create_btn=is_create))
                        BigWorld.callback(0.15, lambda: _apply_platoon_window_position(wnd, is_create_btn=is_create))
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _schedule_visibility_check(delay=0.1):
    global _VISIBILITY_TIMER_ID
    if _VISIBILITY_TIMER_ID is not None:
        try:
            BigWorld.cancelCallback(_VISIBILITY_TIMER_ID)
        except Exception:
            pass
        _VISIBILITY_TIMER_ID = None
    _VISIBILITY_TIMER_ID = BigWorld.callback(delay, _run_scheduled_visibility)


def _run_scheduled_visibility():
    global _VISIBILITY_TIMER_ID
    _VISIBILITY_TIMER_ID = None
    _update_visibility()


def _update_visibility():
    global _UI_FREE_RETRIES
    if not _CONFIG.get('enabled', True):
        return
    try:
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        platoonCtrl = dependency.instance(IPlatoonController)
        if platoonCtrl is None:
            return

        in_hangar = _is_in_hangar()

        if not in_hangar:
            _UI_FREE_RETRIES = 0
            if platoonCtrl.isAnyPlatoonUIShown():
                platoonCtrl.destroyUI(hideOnly=True)
            return

        # event promo windows at login block first checks → retry — 2026-10-15
        busy = _hangar_ui_busy_reason()
        if busy and _UI_FREE_RETRIES < 5:
            _UI_FREE_RETRIES += 1
            LOG_NOTE('[PlatoonAutoStart] Hangar UI busy (%s), auto-show retry %d' % (busy, _UI_FREE_RETRIES))
            BigWorld.callback(1.0, _update_visibility)
            return
        if busy:
            LOG_NOTE('[PlatoonAutoStart] Hangar UI still busy (%s), showing anyway' % busy)

        _UI_FREE_RETRIES = 0

        if not in_hangar:
            if platoonCtrl.isAnyPlatoonUIShown():
                platoonCtrl.destroyUI(hideOnly=True)
            return

        if not platoonCtrl.isInPlatoon():
            from gui.impl.lobby.platoon.platoon_config import EPlatoonLayout
            show_window = getattr(platoonCtrl, '_PlatoonController__showWindow', None)
            if show_window is not None:
                show_window(EPlatoonLayout.WELCOME)
            BigWorld.callback(0.2, _sync_solo_mode_to_views)
            return

        if platoonCtrl.isInPlatoon() and _CONFIG.get('keep_window_open', True):
            if not _USER_CLOSED_WINDOW and not platoonCtrl.isAnyPlatoonUIShown():
                from gui.impl.lobby.platoon.platoon_config import EPlatoonLayout
                from frameworks.wulf import WindowStatus
                membersView = getattr(platoonCtrl, '_PlatoonController__getView', lambda x: None)(EPlatoonLayout.MEMBER)
                if membersView is not None:
                    wnd = membersView.getParentWindow()
                    if wnd is not None and (getattr(wnd, 'windowStatus', None) != WindowStatus.LOADED or not wnd.isReady):
                        return
                platoonCtrl.evaluateVisibility(toggleUI=False)
                BigWorld.callback(0.2, _sync_solo_mode_to_views)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _hooked_PlatoonController_createPlatoon(self, *args, **kwargs):
    global _USER_CLOSED_WINDOW
    _USER_CLOSED_WINDOW = False
    _cancel_auto_leave()
    _clear_solo_invites()
    if _orig_PlatoonController_createPlatoon is not None:
        return _orig_PlatoonController_createPlatoon(self, *args, **kwargs)


def _hooked_PlatoonController_leavePlatoon(self, *args, **kwargs):
    global _USER_CLOSED_WINDOW
    _USER_CLOSED_WINDOW = False
    _clear_solo_invites()
    if _orig_PlatoonController_leavePlatoon is not None:
        return _orig_PlatoonController_leavePlatoon(self, *args, **kwargs)


def _hooked_PlatoonController_evaluateVisibility(self, toggleUI=False):
    global _USER_CLOSED_WINDOW
    if not _is_in_hangar():
        if self.isAnyPlatoonUIShown():
            self.destroyUI(hideOnly=True)
        return

    if not self.isInPlatoon():
        if toggleUI:
            _clear_solo_invites()
            LOG_NOTE('[PlatoonAutoStart] Platoon button clicked while not in platoon: immediately creating platoon')
            self.createPlatoon(startAutoSearchOnUnitJoin=False)
            return
        return _orig_PlatoonController_evaluateVisibility(self, toggleUI=False)

    if toggleUI:
        _USER_CLOSED_WINDOW = False
        if _CONFIG.get('keep_window_open', True) and self.isAnyPlatoonUIShown():
            return
    return _orig_PlatoonController_evaluateVisibility(self, toggleUI=toggleUI)


def _hooked_SquadMembersView_onLeavePlatoon(self):
    global _USER_CLOSED_WINDOW
    _USER_CLOSED_WINDOW = False
    _clear_solo_invites()
    try:
        if hasattr(self, '_platoonCtrl') and self._platoonCtrl is not None:
            self._platoonCtrl.leavePlatoon(ignoreConfirmation=True)
            BigWorld.callback(0.3, _update_visibility)
            BigWorld.callback(0.5, _sync_solo_mode_to_views)
            return
    except Exception:
        LOG_CURRENT_EXCEPTION()
    return _orig_SquadMembersView_onLeavePlatoon(self)


def _hooked_SquadMembersView_onMinimized(self, *args, **kwargs):
    global _USER_CLOSED_WINDOW
    _USER_CLOSED_WINDOW = True
    if _orig_SquadMembersView_onMinimized:
        return _orig_SquadMembersView_onMinimized(self, *args, **kwargs)


def _hooked_MembersWindow_move(self, x, y):
    global _IS_SETTING_WINDOW_POS
    if _IS_SETTING_WINDOW_POS:
        if _orig_MembersWindow_move:
            _orig_MembersWindow_move(self, x, y)
        return

    try:
        import GUI
        screenW, screenH = GUI.screenResolution()
        scale = screenH / 1080.0
    except Exception:
        scale = 1.0

    if _CONFIG.get('fixed_window_pos', False):
        targetX = int(_CONFIG.get('window_pos_x', 26) * scale)
        targetY = int(_CONFIG.get('window_pos_y', 488) * scale)
        if x != targetX or y != targetY:
            _apply_platoon_window_position(self, is_create_btn=False)
        return

    if _orig_MembersWindow_move:
        _orig_MembersWindow_move(self, x, y)

    _CONFIG['window_pos_x'] = int(x / scale)
    _CONFIG['window_pos_y'] = int(y / scale)
    _save_config()


def _on_route_changed(*args, **kwargs):
    global _WAS_IN_BATTLE
    if _is_in_hangar():
        if _WAS_IN_BATTLE:
            _WAS_IN_BATTLE = False
            if _SOLO_MODE_ENABLED:
                _trigger_auto_leave_platoon()
    else:
        _hide_platoon_ui_immediately()
    _schedule_visibility_check(0.1)


def _on_view_lifecycle_event(*args, **kwargs):
    if not _CONFIG.get('enabled', True):
        return
    _schedule_visibility_check(0.15)


def _on_platoon_members_update(*args, **kwargs):
    if _PENDING_AUTO_LEAVE and _SOLO_MODE_ENABLED:
        _do_auto_leave_attempt(attempt=1)
        return
    _schedule_auto_start_check()
    _schedule_visibility_check(0.15)


def _try_subscribe_lsm():
    global _LSM_SUBSCRIBED
    if _LSM_SUBSCRIBED:
        return
    try:
        from gui.Scaleform.lobby_entry import getLobbyStateMachine
        lsm = getLobbyStateMachine()
        if lsm is not None and hasattr(lsm, 'onVisibleRouteChanged'):
            lsm.onVisibleRouteChanged += _on_route_changed
            _LSM_SUBSCRIBED = True
            LOG_NOTE('[PlatoonAutoStart] Subscribed to LSM onVisibleRouteChanged')
    except Exception:
        pass


def _unsubscribe_lsm():
    global _LSM_SUBSCRIBED
    if not _LSM_SUBSCRIBED:
        return
    try:
        from gui.Scaleform.lobby_entry import getLobbyStateMachine
        lsm = getLobbyStateMachine()
        if lsm is not None and hasattr(lsm, 'onVisibleRouteChanged'):
            lsm.onVisibleRouteChanged -= _on_route_changed
            _LSM_SUBSCRIBED = False
    except Exception:
        pass


def _subscribe_view_events():
    global _VIEW_EVENTS_SUBSCRIBED
    if _VIEW_EVENTS_SUBSCRIBED:
        return
    try:
        from gui.shared import g_eventBus, EVENT_BUS_SCOPE
        from gui.shared.events import ViewEventType
        g_eventBus.addListener(ViewEventType.LOAD_VIEW, _on_view_lifecycle_event, scope=EVENT_BUS_SCOPE.LOBBY)
        g_eventBus.addListener(ViewEventType.LOAD_GUI_IMPL_VIEW, _on_view_lifecycle_event, scope=EVENT_BUS_SCOPE.LOBBY)
        g_eventBus.addListener(ViewEventType.DESTROY_VIEW, _on_view_lifecycle_event, scope=EVENT_BUS_SCOPE.LOBBY)
        g_eventBus.addListener(ViewEventType.DESTROY_GUI_IMPL_VIEW, _on_view_lifecycle_event, scope=EVENT_BUS_SCOPE.LOBBY)
        _VIEW_EVENTS_SUBSCRIBED = True
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _unsubscribe_view_events():
    global _VIEW_EVENTS_SUBSCRIBED
    if not _VIEW_EVENTS_SUBSCRIBED:
        return
    try:
        from gui.shared import g_eventBus, EVENT_BUS_SCOPE
        from gui.shared.events import ViewEventType
        g_eventBus.removeListener(ViewEventType.LOAD_VIEW, _on_view_lifecycle_event, scope=EVENT_BUS_SCOPE.LOBBY)
        g_eventBus.removeListener(ViewEventType.LOAD_GUI_IMPL_VIEW, _on_view_lifecycle_event, scope=EVENT_BUS_SCOPE.LOBBY)
        g_eventBus.removeListener(ViewEventType.DESTROY_VIEW, _on_view_lifecycle_event, scope=EVENT_BUS_SCOPE.LOBBY)
        g_eventBus.removeListener(ViewEventType.DESTROY_GUI_IMPL_VIEW, _on_view_lifecycle_event, scope=EVENT_BUS_SCOPE.LOBBY)
        _VIEW_EVENTS_SUBSCRIBED = False
    except Exception:
        pass


def _subscribe_windows_manager():
    global _WM_EVENTS_SUBSCRIBED
    if _WM_EVENTS_SUBSCRIBED:
        return
    try:
        from helpers import dependency
        from skeletons.gui.impl import IGuiLoader
        guiLoader = dependency.instance(IGuiLoader)
        if guiLoader and getattr(guiLoader, 'windowsManager', None):
            wm = guiLoader.windowsManager
            if hasattr(wm, 'onWindowStatusChanged'):
                wm.onWindowStatusChanged += _on_view_lifecycle_event
            if hasattr(wm, 'onWindowShowingStatusChanged'):
                wm.onWindowShowingStatusChanged += _on_view_lifecycle_event
            _WM_EVENTS_SUBSCRIBED = True
    except Exception:
        pass


def _unsubscribe_windows_manager():
    global _WM_EVENTS_SUBSCRIBED
    if not _WM_EVENTS_SUBSCRIBED:
        return
    try:
        from helpers import dependency
        from skeletons.gui.impl import IGuiLoader
        guiLoader = dependency.instance(IGuiLoader)
        if guiLoader and getattr(guiLoader, 'windowsManager', None):
            wm = guiLoader.windowsManager
            if hasattr(wm, 'onWindowStatusChanged'):
                wm.onWindowStatusChanged -= _on_view_lifecycle_event
            if hasattr(wm, 'onWindowShowingStatusChanged'):
                wm.onWindowShowingStatusChanged -= _on_view_lifecycle_event
            _WM_EVENTS_SUBSCRIBED = False
    except Exception:
        pass


def _solo_invite_delay():
    try:
        low = max(0.5, float(_CONFIG.get('solo_invite_delay_min', 2.0)))
        high = max(low, float(_CONFIG.get('solo_invite_delay_max', 5.0)))
    except (TypeError, ValueError):
        low, high = 2.0, 5.0
    return round(random.uniform(low, high), 3)


def _clear_solo_invites():
    global _SOLO_INVITE_CALLBACK_ID, _PENDING_SOLO_INVITES
    if _SOLO_INVITE_CALLBACK_ID is not None:
        try:
            BigWorld.cancelCallback(_SOLO_INVITE_CALLBACK_ID)
        except Exception:
            pass
        _SOLO_INVITE_CALLBACK_ID = None
    _PENDING_SOLO_INVITES = []


def _try_start_solo_mode_invites():
    global _PENDING_SOLO_INVITES, _SOLO_INVITE_CALLBACK_ID
    if not _SOLO_MODE_ENABLED:
        return
    if _SOLO_INVITE_CALLBACK_ID is not None:
        return

    try:
        from helpers import dependency
        from skeletons.gui.battle_session import IBattleSessionProvider
        sessionProvider = dependency.instance(IBattleSessionProvider)
        if sessionProvider is None:
            return

        arenaDP = sessionProvider.getArenaDP()
        if arenaDP is None:
            return

        try:
            playerVehID = arenaDP.getPlayerVehicleID()
            playerVInfo = arenaDP.getVehicleInfo(playerVehID)
            if playerVInfo and playerVInfo.isSquadMan():
                squadID = getattr(playerVInfo, 'squadIndex', 0)
                if squadID > 0:
                    squad_count = sum(1 for v in arenaDP.getVehiclesInfoIterator() if getattr(v, 'squadIndex', 0) == squadID)
                    if squad_count >= 3:
                        return
        except Exception:
            pass

        queued_veh_ids = set(vehID for (vehID, _) in _PENDING_SOLO_INVITES)
        for vInfo in arenaDP.getAllyVehiclesInfoIterator():
            vehID = getattr(vInfo, 'vehicleID', None)
            if not vehID or vehID in _SENT_INVITE_VEH_IDS or vehID in queued_veh_ids:
                continue

            if vInfo.isPlayerVehicle():
                continue

            isBot = getattr(vInfo, 'isBot', False)
            if not isBot and hasattr(vInfo, 'player'):
                isBot = getattr(vInfo.player, 'isBot', False)
            if isBot:
                continue

            if vInfo.isSquadMan():
                continue

            sessionID = getattr(vInfo.player, 'avatarSessionID', None) if hasattr(vInfo, 'player') else None
            _PENDING_SOLO_INVITES.append((vehID, sessionID))
            queued_veh_ids.add(vehID)

        if _PENDING_SOLO_INVITES and _SOLO_INVITE_CALLBACK_ID is None:
            _process_next_solo_invite()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _process_next_solo_invite():
    global _SOLO_INVITE_CALLBACK_ID, _PENDING_SOLO_INVITES
    _SOLO_INVITE_CALLBACK_ID = None

    if not _SOLO_MODE_ENABLED:
        _clear_solo_invites()
        return

    try:
        from helpers import dependency
        from skeletons.gui.battle_session import IBattleSessionProvider
        sessionProvider = dependency.instance(IBattleSessionProvider)
        if sessionProvider is None:
            _clear_solo_invites()
            return

        arenaDP = sessionProvider.getArenaDP()
        if arenaDP is None:
            _clear_solo_invites()
            return

        try:
            playerVehID = arenaDP.getPlayerVehicleID()
            playerVInfo = arenaDP.getVehicleInfo(playerVehID)
            if playerVInfo and playerVInfo.isSquadMan():
                squadID = getattr(playerVInfo, 'squadIndex', 0)
                if squadID > 0:
                    squad_count = sum(1 for v in arenaDP.getVehiclesInfoIterator() if getattr(v, 'squadIndex', 0) == squadID)
                    if squad_count >= 3:
                        LOG_NOTE('[PlatoonAutoStart] Squad is full (3 members), stopping solo mode invites')
                        _clear_solo_invites()
                        return
        except Exception:
            pass

        invitations = getattr(sessionProvider, 'invitations', None)

        while _PENDING_SOLO_INVITES:
            vehID, sessionID = _PENDING_SOLO_INVITES.pop(0)
            if vehID in _SENT_INVITE_VEH_IDS:
                continue

            vInfo = arenaDP.getVehicleInfo(vehID)
            if vInfo and vInfo.isSquadMan():
                continue

            _SENT_INVITE_VEH_IDS.add(vehID)
            sent = False
            try:
                if invitations is not None and hasattr(invitations, 'send') and sessionID:
                    invitations.send(sessionID)
                    sent = True
                elif hasattr(sessionProvider, 'sendRequest'):
                    from gui.battle_control.requests.context import SendInvitesCtx
                    sessionProvider.sendRequest(SendInvitesCtx(playerIDs=(vehID,)))
                    sent = True
            except Exception:
                LOG_CURRENT_EXCEPTION()

            if sent:
                LOG_NOTE('[PlatoonAutoStart] Solo mode: Sent platoon invite to vehID=%s (%d remaining in queue)' % (
                    vehID, len(_PENDING_SOLO_INVITES)))
                if _PENDING_SOLO_INVITES:
                    _SOLO_INVITE_CALLBACK_ID = BigWorld.callback(_solo_invite_delay(), _process_next_solo_invite)
                return

        _clear_solo_invites()
    except Exception:
        LOG_CURRENT_EXCEPTION()
        _clear_solo_invites()


def _on_avatar_become_player(*args, **kwargs):
    global _WAS_IN_BATTLE, _SENT_INVITE_VEH_IDS
    _cancel_auto_leave()
    _WAS_IN_BATTLE = True
    _SENT_INVITE_VEH_IDS = set()
    _clear_solo_invites()
    if _SOLO_MODE_ENABLED:
        BigWorld.callback(_solo_invite_delay(), _try_start_solo_mode_invites)


def _on_arena_period_change(period, *args, **kwargs):
    if _SOLO_MODE_ENABLED and period in (2, 3):
        BigWorld.callback(0.5, _try_start_solo_mode_invites)


def _trigger_auto_leave_platoon():
    global _PENDING_AUTO_LEAVE, _AUTO_LEAVE_TIMER_ID
    if not _SOLO_MODE_ENABLED:
        _PENDING_AUTO_LEAVE = False
        return
    _PENDING_AUTO_LEAVE = True
    if _AUTO_LEAVE_TIMER_ID is not None:
        try:
            BigWorld.cancelCallback(_AUTO_LEAVE_TIMER_ID)
        except Exception:
            pass
        _AUTO_LEAVE_TIMER_ID = None
    _do_auto_leave_attempt(attempt=1)


def _do_auto_leave_attempt(attempt=1):
    global _PENDING_AUTO_LEAVE, _AUTO_LEAVE_TIMER_ID
    if _AUTO_LEAVE_TIMER_ID is not None:
        try:
            BigWorld.cancelCallback(_AUTO_LEAVE_TIMER_ID)
        except Exception:
            pass
        _AUTO_LEAVE_TIMER_ID = None
    if not _PENDING_AUTO_LEAVE or not _SOLO_MODE_ENABLED:
        _cancel_auto_leave()
        return

    try:
        from gui.lobby_state_machine.states import isInHangarState
        if not isInHangarState():
            if attempt < 20:
                _AUTO_LEAVE_TIMER_ID = BigWorld.callback(0.5, lambda: _do_auto_leave_attempt(attempt + 1))
            else:
                _cancel_auto_leave()
            return
    except Exception:
        pass

    try:
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        platoonCtrl = dependency.instance(IPlatoonController)
        if platoonCtrl is not None and platoonCtrl.isInPlatoon():
            LOG_NOTE('[PlatoonAutoStart] Solo mode: Auto-leaving platoon after battle (attempt %d)' % attempt)
            platoonCtrl.leavePlatoon(ignoreConfirmation=True)
            _PENDING_AUTO_LEAVE = False
            _clear_solo_invites()
            BigWorld.callback(0.4, _update_visibility)
            BigWorld.callback(0.8, _sync_solo_mode_to_views)
            return
    except Exception:
        LOG_CURRENT_EXCEPTION()

    if attempt < 20:
        _AUTO_LEAVE_TIMER_ID = BigWorld.callback(0.5, lambda: _do_auto_leave_attempt(attempt + 1))
    else:
        LOG_NOTE('[PlatoonAutoStart] Solo mode: Auto-leave finished polling')
        _PENDING_AUTO_LEAVE = False
        _clear_solo_invites()
        BigWorld.callback(0.4, _sync_solo_mode_to_views)


def _on_account_show_gui(*args, **kwargs):
    global _WAS_IN_BATTLE
    _clear_solo_invites()
    try:
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        platoonCtrl = dependency.instance(IPlatoonController)
        if platoonCtrl is not None:
            platoonCtrl.onMembersUpdate += _on_platoon_members_update
    except Exception:
        LOG_CURRENT_EXCEPTION()

    _try_subscribe_lsm()
    _subscribe_windows_manager()

    if _WAS_IN_BATTLE:
        _WAS_IN_BATTLE = False
        if _SOLO_MODE_ENABLED:
            _trigger_auto_leave_platoon()
        else:
            BigWorld.callback(1.2, _update_visibility)
    else:
        BigWorld.callback(1.2, _update_visibility)


def _install_invites_none_guard():
    try:
        from collections import defaultdict
        from gui.prb_control.invites import InvitesManager, _getNewInvites, _InviteVersion
        from shared_utils.account_helpers.ClientInvitations import UniqueId
        from skeletons.gui.app_loader import GuiGlobalSpaceID

        if getattr(InvitesManager, '_uaInvitesNoneGuard', False):
            return

        def onUserNamesReceived(self, names):
            updated = defaultdict(list)
            rosterGetter = self.usersStorage.getUser
            inviteMaker = self._getNewInviteMaker(rosterGetter)
            prebattleInvitations = _getNewInvites()
            for invite in self.getInvites(version=_InviteVersion.NEW, withIgnored=True):
                if invite.creatorID in names or invite.receiverID in names:
                    senderID = invite.creatorID
                    if self.appLoader.getSpaceID() == GuiGlobalSpaceID.BATTLE:
                        senderID = invite.creatorVehID
                    inviteUniqueId = UniqueId(id=invite.id, senderID=senderID)
                    inviteData = prebattleInvitations.get(inviteUniqueId)
                    if inviteData is None:
                        LOG_NOTE('[PlatoonAutoStart] Skipped stale invite entry (game bug WG: inviteData=None)')
                        continue
                    inviteID, invite = inviteMaker(inviteData)
                    if self._updateInvite(invite):
                        updated[invite.isIncoming()].append(inviteID)
            for isIncoming, event in ((True, self.onReceivedInviteListModified),
             (
              False, self.onSentInviteListModified)):
                if updated[isIncoming]:
                    event([], updated[isIncoming], [])

            return

        InvitesManager.onUserNamesReceived = onUserNamesReceived
        InvitesManager._uaInvitesNoneGuard = True
        LOG_NOTE('[PlatoonAutoStart] Installed invites None-guard (WG bug fix)')
    except Exception:
        LOG_CURRENT_EXCEPTION()


def init():
    global _orig_SetReady_getCooldown, _orig_SetVehicle_getCooldown
    global _orig_UnitCooldown_process, _orig_UnitCooldown_validate
    global _orig_SquadMembersView_onFocusChange, _orig_SquadMembersView_onLoading, _orig_SquadMembersView_removeListeners
    global _orig_WelcomeView_onLoading
    global _orig_PlatoonController_onUnitPlayerStateChanged
    global _orig_PlatoonController_onUnitVehiclesChanged
    global _orig_PlatoonController_onUnitMembersListChanged
    global _orig_showPlatoonWarningDialog, _orig_base_showPlatoonWarningDialog, _orig_random_showPlatoonWarningDialog
    global _orig_SquadMembersView_updateReadyButton
    global _orig_PlatoonController_showWindow
    global _orig_PlatoonController_evaluateVisibility
    global _orig_PlatoonController_setPlatoonPopoverPosition
    global _orig_SquadMembersView_onLeavePlatoon
    global _orig_SquadMembersView_onMinimized
    global _orig_MembersWindow_init, _orig_MembersWindow_move, _orig_MembersWindow_center
    global _orig_SelectionWindow_init, _orig_SelectionWindow_move, _orig_SelectionWindow_center
    global _orig_SquadMembersView_updateButtons, _orig_WelcomeView_initButtons, _orig_WelcomeView_removeListeners
    global _orig_SquadMembersView_onSwitchReady
    global _orig_PlatoonController_createPlatoon, _orig_PlatoonController_leavePlatoon

    _load_config()

    _orig_SetReady_getCooldown = SetReadyUnitCtx.getCooldown
    SetReadyUnitCtx.getCooldown = _hooked_SetReady_getCooldown

    _orig_SetVehicle_getCooldown = SetVehicleUnitCtx.getCooldown
    SetVehicleUnitCtx.getCooldown = _hooked_SetVehicle_getCooldown

    _orig_UnitCooldown_process = UnitCooldownManager.process
    UnitCooldownManager.process = _hooked_UnitCooldown_process

    _orig_UnitCooldown_validate = UnitCooldownManager.validate
    UnitCooldownManager.validate = _hooked_UnitCooldown_validate

    _orig_SquadMembersView_onFocusChange = getattr(SquadMembersView, '_SquadMembersView__onFocusChange', None)
    setattr(SquadMembersView, '_SquadMembersView__onFocusChange', _hooked_SquadMembersView_onFocusChange)

    _orig_SquadMembersView_removeListeners = SquadMembersView._removeListeners
    SquadMembersView._removeListeners = _hooked_SquadMembersView_removeListeners

    _orig_SquadMembersView_onLoading = getattr(SquadMembersView, '_onLoading', None)
    setattr(SquadMembersView, '_onLoading', _hooked_SquadMembersView_onLoading)

    _orig_WelcomeView_onLoading = getattr(WelcomeView, '_onLoading', None)
    setattr(WelcomeView, '_onLoading', _hooked_WelcomeView_onLoading)

    _orig_PlatoonController_onUnitPlayerStateChanged = PlatoonController.onUnitPlayerStateChanged
    PlatoonController.onUnitPlayerStateChanged = _hooked_PlatoonController_onUnitPlayerStateChanged

    _orig_PlatoonController_onUnitVehiclesChanged = PlatoonController.onUnitVehiclesChanged
    PlatoonController.onUnitVehiclesChanged = _hooked_PlatoonController_onUnitVehiclesChanged

    _orig_PlatoonController_onUnitMembersListChanged = PlatoonController.onUnitMembersListChanged
    PlatoonController.onUnitMembersListChanged = _hooked_PlatoonController_onUnitMembersListChanged

    try:
        import gui.shared.event_dispatcher as shared_event_dispatcher
        _orig_showPlatoonWarningDialog = getattr(shared_event_dispatcher, 'showPlatoonWarningDialog', None)
        if _orig_showPlatoonWarningDialog is not None:
            setattr(shared_event_dispatcher, 'showPlatoonWarningDialog', _hooked_showPlatoonWarningDialog)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        import gui.prb_control.entities.base.squad.actions_handler as base_squad_actions_handler
        _orig_base_showPlatoonWarningDialog = getattr(base_squad_actions_handler, 'showPlatoonWarningDialog', None)
        if _orig_base_showPlatoonWarningDialog is not None:
            setattr(base_squad_actions_handler, 'showPlatoonWarningDialog', _hooked_showPlatoonWarningDialog)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        import gui.prb_control.entities.random.squad.actions_handler as random_squad_actions_handler
        _orig_random_showPlatoonWarningDialog = getattr(random_squad_actions_handler, 'showPlatoonWarningDialog', None)
        if _orig_random_showPlatoonWarningDialog is not None:
            setattr(random_squad_actions_handler, 'showPlatoonWarningDialog', _hooked_showPlatoonWarningDialog)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    _orig_SquadMembersView_updateReadyButton = SquadMembersView._updateReadyButton
    SquadMembersView._updateReadyButton = _hooked_SquadMembersView_updateReadyButton

    _orig_PlatoonController_showWindow = getattr(PlatoonController, '_PlatoonController__showWindow', None)
    if _orig_PlatoonController_showWindow:
        setattr(PlatoonController, '_PlatoonController__showWindow', _hooked_PlatoonController_showWindow)

    _orig_PlatoonController_evaluateVisibility = PlatoonController.evaluateVisibility
    PlatoonController.evaluateVisibility = _hooked_PlatoonController_evaluateVisibility

    _orig_PlatoonController_setPlatoonPopoverPosition = getattr(PlatoonController, 'setPlatoonPopoverPosition', None)
    if _orig_PlatoonController_setPlatoonPopoverPosition:
        setattr(PlatoonController, 'setPlatoonPopoverPosition', _hooked_PlatoonController_setPlatoonPopoverPosition)

    _orig_SquadMembersView_onLeavePlatoon = SquadMembersView._onLeavePlatoon
    SquadMembersView._onLeavePlatoon = _hooked_SquadMembersView_onLeavePlatoon

    _orig_SquadMembersView_onMinimized = getattr(SquadMembersView, '_SquadMembersView__onMinimized', None)
    if _orig_SquadMembersView_onMinimized:
        setattr(SquadMembersView, '_SquadMembersView__onMinimized', _hooked_SquadMembersView_onMinimized)

    _orig_MembersWindow_init = getattr(MembersWindow, '__init__', None)
    if _orig_MembersWindow_init:
        MembersWindow.__init__ = _hooked_MembersWindow_init

    _orig_MembersWindow_move = getattr(MembersWindow, 'move', None)
    if _orig_MembersWindow_move:
        MembersWindow.move = _hooked_MembersWindow_move

    _orig_MembersWindow_center = getattr(MembersWindow, 'center', None)
    if _orig_MembersWindow_center:
        MembersWindow.center = _hooked_MembersWindow_center

    _orig_SelectionWindow_init = getattr(SelectionWindow, '__init__', None)
    if _orig_SelectionWindow_init:
        SelectionWindow.__init__ = _hooked_SelectionWindow_init

    _orig_SelectionWindow_move = getattr(SelectionWindow, 'move', None)
    if _orig_SelectionWindow_move:
        SelectionWindow.move = _hooked_SelectionWindow_move

    _orig_SelectionWindow_center = getattr(SelectionWindow, 'center', None)
    if _orig_SelectionWindow_center:
        SelectionWindow.center = _hooked_SelectionWindow_center

    global _orig_SquadMembersView_onSwitchReady
    _orig_SquadMembersView_onSwitchReady = getattr(SquadMembersView, '_onSwitchReady', None)
    if _orig_SquadMembersView_onSwitchReady:
        SquadMembersView._onSwitchReady = _hooked_SquadMembersView_onSwitchReady

    _orig_SquadMembersView_updateButtons = getattr(SquadMembersView, '_updateButtons', None)
    if _orig_SquadMembersView_updateButtons:
        SquadMembersView._updateButtons = _hooked_SquadMembersView_updateButtons

    _orig_WelcomeView_removeListeners = WelcomeView._removeListeners
    WelcomeView._removeListeners = _hooked_WelcomeView_removeListeners

    _orig_WelcomeView_initButtons = getattr(WelcomeView, '_initButtons', None)
    if _orig_WelcomeView_initButtons:
        WelcomeView._initButtons = _hooked_WelcomeView_initButtons

    _orig_PlatoonController_createPlatoon = getattr(PlatoonController, 'createPlatoon', None)
    if _orig_PlatoonController_createPlatoon:
        PlatoonController.createPlatoon = _hooked_PlatoonController_createPlatoon

    _orig_PlatoonController_leavePlatoon = getattr(PlatoonController, 'leavePlatoon', None)
    if _orig_PlatoonController_leavePlatoon:
        PlatoonController.leavePlatoon = _hooked_PlatoonController_leavePlatoon

    _subscribe_view_events()
    _subscribe_windows_manager()

    _install_invites_none_guard()

    g_playerEvents.onAccountShowGUI += _on_account_show_gui
    g_playerEvents.onAvatarBecomePlayer += _on_avatar_become_player
    g_playerEvents.onArenaPeriodChange += _on_arena_period_change
    try:
        BigWorld.callback(0.1, _init_mods_settings)
    except Exception:
        _init_mods_settings()

    LOG_NOTE('[PlatoonAutoStart] Mod initialized successfully')


def fini():
    global _orig_SetReady_getCooldown, _orig_SetVehicle_getCooldown
    global _orig_UnitCooldown_process, _orig_UnitCooldown_validate
    global _orig_SquadMembersView_onFocusChange, _orig_SquadMembersView_onLoading, _orig_SquadMembersView_removeListeners
    global _orig_WelcomeView_onLoading
    global _orig_PlatoonController_onUnitPlayerStateChanged
    global _orig_PlatoonController_onUnitVehiclesChanged
    global _orig_PlatoonController_onUnitMembersListChanged
    global _orig_showPlatoonWarningDialog, _orig_base_showPlatoonWarningDialog, _orig_random_showPlatoonWarningDialog
    global _orig_SquadMembersView_updateReadyButton
    global _orig_PlatoonController_showWindow
    global _orig_PlatoonController_evaluateVisibility
    global _orig_PlatoonController_setPlatoonPopoverPosition
    global _orig_SquadMembersView_onLeavePlatoon
    global _orig_SquadMembersView_onMinimized
    global _orig_MembersWindow_init, _orig_MembersWindow_move, _orig_MembersWindow_center
    global _orig_SelectionWindow_init, _orig_SelectionWindow_move, _orig_SelectionWindow_center
    global _orig_SquadMembersView_updateButtons, _orig_WelcomeView_initButtons, _orig_WelcomeView_removeListeners
    global _orig_SquadMembersView_onSwitchReady
    if _orig_SquadMembersView_onSwitchReady is not None:
        SquadMembersView._onSwitchReady = _orig_SquadMembersView_onSwitchReady
    global _orig_PlatoonController_createPlatoon, _orig_PlatoonController_leavePlatoon

    _clear_solo_invites()
    _cancel_auto_start_timer()
    global _AUTO_LEAVE_TIMER_ID, _PENDING_AUTO_LEAVE
    _PENDING_AUTO_LEAVE = False
    if _AUTO_LEAVE_TIMER_ID is not None:
        try:
            BigWorld.cancelCallback(_AUTO_LEAVE_TIMER_ID)
        except Exception:
            pass
        _AUTO_LEAVE_TIMER_ID = None
    global _VISIBILITY_TIMER_ID
    if _VISIBILITY_TIMER_ID is not None:
        try:
            BigWorld.cancelCallback(_VISIBILITY_TIMER_ID)
        except Exception:
            pass
        _VISIBILITY_TIMER_ID = None
    _unsubscribe_lsm()
    _unsubscribe_view_events()
    _unsubscribe_windows_manager()

    try:
        g_playerEvents.onAccountShowGUI -= _on_account_show_gui
    except Exception:
        pass

    try:
        g_playerEvents.onAvatarBecomePlayer -= _on_avatar_become_player
    except Exception:
        pass

    try:
        g_playerEvents.onArenaPeriodChange -= _on_arena_period_change
    except Exception:
        pass

    try:
        from helpers import dependency
        from skeletons.gui.game_control import IPlatoonController
        platoonCtrl = dependency.instance(IPlatoonController)
        if platoonCtrl is not None:
            platoonCtrl.onMembersUpdate -= _on_platoon_members_update
    except Exception:
        pass

    if _orig_SetReady_getCooldown is not None:
        SetReadyUnitCtx.getCooldown = _orig_SetReady_getCooldown
    if _orig_SetVehicle_getCooldown is not None:
        SetVehicleUnitCtx.getCooldown = _orig_SetVehicle_getCooldown
    if _orig_UnitCooldown_process is not None:
        UnitCooldownManager.process = _orig_UnitCooldown_process
    if _orig_UnitCooldown_validate is not None:
        UnitCooldownManager.validate = _orig_UnitCooldown_validate
    if _orig_SquadMembersView_onFocusChange is not None:
        setattr(SquadMembersView, '_SquadMembersView__onFocusChange', _orig_SquadMembersView_onFocusChange)
    if _orig_SquadMembersView_removeListeners is not None:
        SquadMembersView._removeListeners = _orig_SquadMembersView_removeListeners
    if _orig_SquadMembersView_onLoading is not None:
        setattr(SquadMembersView, '_onLoading', _orig_SquadMembersView_onLoading)
    if _orig_WelcomeView_onLoading is not None:
        setattr(WelcomeView, '_onLoading', _orig_WelcomeView_onLoading)
    if _orig_PlatoonController_onUnitPlayerStateChanged is not None:
        PlatoonController.onUnitPlayerStateChanged = _orig_PlatoonController_onUnitPlayerStateChanged
    if _orig_PlatoonController_onUnitVehiclesChanged is not None:
        PlatoonController.onUnitVehiclesChanged = _orig_PlatoonController_onUnitVehiclesChanged
    if _orig_PlatoonController_onUnitMembersListChanged is not None:
        PlatoonController.onUnitMembersListChanged = _orig_PlatoonController_onUnitMembersListChanged

    if _orig_showPlatoonWarningDialog is not None:
        try:
            import gui.shared.event_dispatcher as shared_event_dispatcher
            setattr(shared_event_dispatcher, 'showPlatoonWarningDialog', _orig_showPlatoonWarningDialog)
        except Exception:
            pass

    if _orig_base_showPlatoonWarningDialog is not None:
        try:
            import gui.prb_control.entities.base.squad.actions_handler as base_squad_actions_handler
            setattr(base_squad_actions_handler, 'showPlatoonWarningDialog', _orig_base_showPlatoonWarningDialog)
        except Exception:
            pass

    if _orig_random_showPlatoonWarningDialog is not None:
        try:
            import gui.prb_control.entities.random.squad.actions_handler as random_squad_actions_handler
            setattr(random_squad_actions_handler, 'showPlatoonWarningDialog', _orig_random_showPlatoonWarningDialog)
        except Exception:
            pass
    if _orig_SquadMembersView_updateReadyButton is not None:
        SquadMembersView._updateReadyButton = _orig_SquadMembersView_updateReadyButton
    if _orig_PlatoonController_showWindow is not None:
        setattr(PlatoonController, '_PlatoonController__showWindow', _orig_PlatoonController_showWindow)
    if _orig_PlatoonController_evaluateVisibility is not None:
        PlatoonController.evaluateVisibility = _orig_PlatoonController_evaluateVisibility
    if _orig_PlatoonController_setPlatoonPopoverPosition is not None:
        setattr(PlatoonController, 'setPlatoonPopoverPosition', _orig_PlatoonController_setPlatoonPopoverPosition)
    if _orig_SquadMembersView_onLeavePlatoon is not None:
        SquadMembersView._onLeavePlatoon = _orig_SquadMembersView_onLeavePlatoon
    if _orig_SquadMembersView_onMinimized is not None:
        setattr(SquadMembersView, '_SquadMembersView__onMinimized', _orig_SquadMembersView_onMinimized)
    if _orig_MembersWindow_init is not None:
        MembersWindow.__init__ = _orig_MembersWindow_init
    if _orig_MembersWindow_move is not None:
        MembersWindow.move = _orig_MembersWindow_move
    if _orig_MembersWindow_center is not None:
        MembersWindow.center = _orig_MembersWindow_center
    if _orig_SelectionWindow_init is not None:
        SelectionWindow.__init__ = _orig_SelectionWindow_init
    if _orig_SelectionWindow_move is not None:
        SelectionWindow.move = _orig_SelectionWindow_move
    if _orig_SelectionWindow_center is not None:
        SelectionWindow.center = _orig_SelectionWindow_center
    if _orig_SquadMembersView_updateButtons is not None:
        SquadMembersView._updateButtons = _orig_SquadMembersView_updateButtons
    if _orig_WelcomeView_removeListeners is not None:
        WelcomeView._removeListeners = _orig_WelcomeView_removeListeners
    if _orig_WelcomeView_initButtons is not None:
        WelcomeView._initButtons = _orig_WelcomeView_initButtons
    if _orig_PlatoonController_createPlatoon is not None:
        PlatoonController.createPlatoon = _orig_PlatoonController_createPlatoon
    if _orig_PlatoonController_leavePlatoon is not None:
        PlatoonController.leavePlatoon = _orig_PlatoonController_leavePlatoon

    LOG_NOTE('[PlatoonAutoStart] Mod unloaded successfully')

# -*- coding: utf-8 -*-
from __future__ import absolute_import
import json
import os
import ssl
import threading
import urllib2
import BigWorld
from debug_utils import LOG_NOTE, LOG_ERROR, LOG_CURRENT_EXCEPTION
from predefined_hosts import g_preDefinedHosts, AUTO_LOGIN_QUERY_URL
from gui.Scaleform.daapi.view.servers_data_provider import ServersDataProvider
from gui.Scaleform.daapi.view.login.LoginView import LoginView
from gui.Scaleform.daapi.view.lobby.ServerStats import ServerStats
from gui.login.Manager import Manager as LoginManager
from PlayerEvents import g_playerEvents

_CONFIG_DIR = os.path.join('mods', 'configs', 'server_online')
_CONFIG_PATH = os.path.join(_CONFIG_DIR, 'config.json')
_CACHE_PATH = os.path.join(_CONFIG_DIR, 'cache.json')

_DEFAULT_CONFIG = {
    'enabled': True,
    'auto_connect_max_online': True,
    'show_online_in_dropdown': True,
    'dropdown_menu_width': 250,
    'strip_wot_prefix': True,
    'post_battle_relogin_enabled': True,
    'relogin_ratio_threshold': 1.5,
    'fetch_on_start': True,
    'api_url': 'https://api.wgstatus.com/api/data/wot'
}

_CONFIG = dict(_DEFAULT_CONFIG)
_SERVER_ONLINE_MAP = {}
_ACTIVE_LOGIN_VIEW = None
_POST_BATTLE_CALLBACK_ID = None
_POST_BATTLE_FRESH = False
_POST_BATTLE_WAITS = 0
_IS_FETCHING = False
_WAS_IN_BATTLE = False

_orig_makeVO = None
_orig_determineRecommendHost = None
_orig_tryWgcLogin = None
_orig_onLogin = None
_orig_LoginView_populate = None
_orig_LoginView_dispose = None
_orig_ServerStats_populate = None
_orig_ServerStats_updateServersList = None


def _format_online(online):
    try:
        return '{:,}'.format(int(online)).replace(',', ' ')
    except Exception:
        return str(online)


def _load_config():
    global _CONFIG
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
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _save_config():
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        with open(_CONFIG_PATH, 'wb') as fp:
            fp.write(json.dumps(_CONFIG, indent=4))
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _init_mods_settings():
    try:
        from gui.modsSettingsApi import g_modsSettingsApi, templates

        def _on_settings_changed(linkage, new_settings):
            if linkage != 'ua.server_online_autoconnect':
                return
            if 'enabled' in new_settings:
                _CONFIG['enabled'] = bool(new_settings['enabled'])
            if 'auto_connect_max_online' in new_settings:
                _CONFIG['auto_connect_max_online'] = bool(new_settings['auto_connect_max_online'])
            if 'show_online_in_dropdown' in new_settings:
                _CONFIG['show_online_in_dropdown'] = bool(new_settings['show_online_in_dropdown'])
            if 'post_battle_relogin_enabled' in new_settings:
                _CONFIG['post_battle_relogin_enabled'] = bool(new_settings['post_battle_relogin_enabled'])
            if 'relogin_ratio_threshold' in new_settings:
                raw_val = float(new_settings['relogin_ratio_threshold'])
                if raw_val <= 30.0:
                    raw_val *= 10.0
                _CONFIG['relogin_ratio_threshold'] = round(raw_val / 100.0, 2)
            _save_config()

        ratio_pct = int(round(float(_CONFIG.get('relogin_ratio_threshold', 1.5)) * 100))
        ratio_pct = max(110, min(300, ratio_pct))

        template = {
            'modDisplayName': 'Smart Server',
            'enabled': bool(_CONFIG.get('enabled', True)),
            'column1': [
                templates.createCheckbox(text='Увімкнути мод', varName='enabled', value=bool(_CONFIG.get('enabled', True))),
                templates.createCheckbox(text='Автопідключення до макс. онлайну', varName='auto_connect_max_online', value=bool(_CONFIG.get('auto_connect_max_online', True))),
                templates.createCheckbox(text='Показувати онлайн у списку', varName='show_online_in_dropdown', value=bool(_CONFIG.get('show_online_in_dropdown', True))),
                templates.createCheckbox(text='Авто-релоґін після бою', varName='post_battle_relogin_enabled', value=bool(_CONFIG.get('post_battle_relogin_enabled', True)))
            ],
            'column2': [
                templates.createSlider(text='Поріг різниці онлайну', varName='relogin_ratio_threshold', value=ratio_pct, min=110, max=300, interval=10, format='{{value}}%')
            ]
        }
        saved = g_modsSettingsApi.setModTemplate('ua.server_online_autoconnect', template, _on_settings_changed)
        if saved and isinstance(saved, dict):
            _on_settings_changed('ua.server_online_autoconnect', saved)
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
            id='ua.server_online_autoconnect',
            name='Smart Server',
            description='Автопідключення та онлайн',
            icon='',
            enabled=True,
            login=False,
            lobby=True,
            callback=_open_settings
        )
    except Exception:
        pass


def _load_cache():
    global _SERVER_ONLINE_MAP
    try:
        if os.path.isfile(_CACHE_PATH):
            with open(_CACHE_PATH, 'rb') as fp:
                cached = json.loads(fp.read())
                if isinstance(cached, dict):
                    _SERVER_ONLINE_MAP.update(cached)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _save_cache():
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        with open(_CACHE_PATH, 'wb') as fp:
            fp.write(json.dumps(_SERVER_ONLINE_MAP, indent=4))
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _extract_online_data(raw_json):
    result = {}
    def _scan(node):
        if isinstance(node, dict):
            if 'name' in node and 'online' in node and node['online'] is not None:
                try:
                    name = node['name'].strip()
                    val = int(node['online'])
                    if name:
                        result[name] = val
                except (ValueError, TypeError):
                    pass
            for v in node.itervalues() if hasattr(node, 'itervalues') else node.values():
                _scan(v)
        elif isinstance(node, list):
            for item in node:
                _scan(item)
    _scan(raw_json)
    return result


def _fetch_worker(url):
    global _IS_FETCHING
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        req = urllib2.Request(url, headers=headers)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            resp = urllib2.urlopen(req, timeout=6, context=ctx)
        except (AttributeError, TypeError):
            resp = urllib2.urlopen(req, timeout=6)

        content = resp.read()
        resp.close()
        parsed = json.loads(content)
        data = _extract_online_data(parsed)
        if data:
            # UI updates must dispatch onto BigWorld main thread — 2026-10-11
            BigWorld.callback(0.0, lambda: _on_fetch_success(data))
    except Exception:
        LOG_CURRENT_EXCEPTION()
    finally:
        _IS_FETCHING = False


def _request_update():
    global _IS_FETCHING
    if not _CONFIG.get('enabled', True):
        return
    if _IS_FETCHING:
        return
    _IS_FETCHING = True
    url = _CONFIG.get('api_url', _DEFAULT_CONFIG['api_url'])
    try:
        worker = threading.Thread(target=_fetch_worker, args=(url,))
        worker.daemon = True
        worker.start()
    except Exception:
        _IS_FETCHING = False
        LOG_CURRENT_EXCEPTION()


def _get_server_online(host):
    if not host or not _SERVER_ONLINE_MAP:
        return None
    short_name = getattr(host, 'shortName', None)
    if short_name and short_name in _SERVER_ONLINE_MAP:
        return _SERVER_ONLINE_MAP[short_name]

    name = getattr(host, 'name', None)
    if name and name in _SERVER_ONLINE_MAP:
        return _SERVER_ONLINE_MAP[name]

    if name:
        tokens = set(name.replace('-', ' ').replace('_', ' ').split())
        for k, v in _SERVER_ONLINE_MAP.iteritems():
            if k and (k in tokens or ' %s ' % name in ' %s ' % k):
                return v

    url = getattr(host, 'url', None)
    if url:
        for i in range(1, 10):
            if ('.p%d.' % i) in url:
                target = 'EU%d' % i
                if target in _SERVER_ONLINE_MAP:
                    return _SERVER_ONLINE_MAP[target]

    periphery_id = getattr(host, 'peripheryID', 0)
    if 201 <= periphery_id <= 209:
        target = 'EU%d' % (periphery_id - 200)
        if target in _SERVER_ONLINE_MAP:
            return _SERVER_ONLINE_MAP[target]

    return None


def _get_best_online_host():
    best_host = None
    max_online = -1
    conn_mgr = None
    try:
        from helpers import dependency
        from skeletons.connection_mgr import IConnectionManager
        conn_mgr = dependency.instance(IConnectionManager)
    except Exception:
        pass

    candidates = g_preDefinedHosts.peripheries()
    avail_group = getattr(g_preDefinedHosts, '_PreDefinedHostList__availablePeripheriesByRoutingGroup', None)
    if avail_group:
        candidates = [h for h in candidates if h.peripheryID in avail_group]

    for host in candidates:
        if not host.peripheryID:
            continue
        if conn_mgr and not conn_mgr.isAvailablePeriphery(host.peripheryID):
            continue
        online = _get_server_online(host)
        if online is not None and online > max_online:
            max_online = online
            best_host = host

    return best_host, max_online


def _apply_best_server_selection():
    if not _CONFIG.get('auto_connect_max_online', True):
        return
    best_host, max_online = _get_best_online_host()
    if not best_host or max_online <= 0:
        return
    try:
        from helpers import dependency
        from skeletons.gui.login_manager import ILoginManager
        login_mgr = dependency.instance(ILoginManager)
        if not login_mgr or not login_mgr.servers:
            return
        servers = login_mgr.servers
        target_idx = -1
        for idx, item in enumerate(servers.serverList):
            if item.get('data') == best_host.url:
                target_idx = idx
                break
        if target_idx != -1:
            servers._selectedServerIdx = target_idx
            if hasattr(servers, 'setServerPreselection') and getattr(best_host, 'peripheryID', None):
                servers.setServerPreselection(best_host.peripheryID)
            elif hasattr(servers, '_loginPreferences') and isinstance(servers._loginPreferences, dict):
                servers._loginPreferences['server_name'] = best_host.url
            if _ACTIVE_LOGIN_VIEW and hasattr(_ACTIVE_LOGIN_VIEW, 'as_setSelectedServerIndexS'):
                _ACTIVE_LOGIN_VIEW.as_setSelectedServerIndexS(target_idx)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _apply_stats_dropdown_width(stats_view):
    try:
        if not _CONFIG.get('enabled', True):
            return
        width = int(_CONFIG.get('dropdown_menu_width', 250))
        fo = getattr(stats_view, 'flashObject', None)
        if fo is not None:
            region_dd = getattr(fo, 'regionDD', None)
            if region_dd is not None:
                region_dd.menuWidth = width
    except Exception:
        pass


def _apply_login_dropdown_width(login_view):
    try:
        if not _CONFIG.get('enabled', True):
            return
        width = int(_CONFIG.get('dropdown_menu_width', 250))
        fo = getattr(login_view, 'flashObject', None)
        if fo is not None:
            for attr in ('server', 'regionDD'):
                comp = getattr(fo, attr, None)
                if comp is not None:
                    comp.menuWidth = width
            form = getattr(fo, 'form', None)
            if form is not None:
                comp = getattr(form, 'server', None)
                if comp is not None:
                    comp.menuWidth = width
    except Exception:
        pass


def _on_fetch_success(data):
    global _POST_BATTLE_FRESH
    _SERVER_ONLINE_MAP.update(data)
    _POST_BATTLE_FRESH = True
    _save_cache()
    try:
        g_preDefinedHosts.onCsisQueryComplete({})
    except Exception:
        LOG_CURRENT_EXCEPTION()
    if _ACTIVE_LOGIN_VIEW is None:
        return
    _apply_best_server_selection()
    try:
        from helpers import dependency
        from skeletons.gui.login_manager import ILoginManager
        login_mgr = dependency.instance(ILoginManager)
        if login_mgr and login_mgr.servers:
            login_mgr.servers.onServersStatusChanged(login_mgr.servers.serverList)
    except Exception:
        pass


def _hooked_makeVO(self, index, item):
    vo = _orig_makeVO(self, index, item)
    if not vo or not isinstance(vo, dict):
        return vo
    if not _CONFIG.get('enabled', True) or not _CONFIG.get('show_online_in_dropdown', True):
        return vo
    try:
        label = vo.get('label', u'')
        if _CONFIG.get('strip_wot_prefix', True) and label.startswith(u'WOT '):
            label = label[4:]
        host_url = vo.get('data')
        if host_url == AUTO_LOGIN_QUERY_URL:
            best_host, max_online = _get_best_online_host()
            if max_online > 0:
                vo['label'] = u'%s (%s)' % (label, _format_online(max_online))
        elif host_url:
            host = g_preDefinedHosts.byUrl(host_url)
            if host:
                online = _get_server_online(host)
                if online is not None and online >= 0:
                    vo['label'] = u'%s (%s)' % (label, _format_online(online))
                elif _CONFIG.get('strip_wot_prefix', True):
                    vo['label'] = label
    except Exception:
        LOG_CURRENT_EXCEPTION()
    return vo


def _hooked_determineRecommendHost(self):
    if _CONFIG.get('enabled', True) and _CONFIG.get('auto_connect_max_online', True):
        best_host, max_online = _get_best_online_host()
        if best_host is not None and max_online > 0:
            LOG_NOTE('[ServerOnline] Auto-connecting to highest population server: %s (%d online)' % (best_host.name, max_online))
            return best_host
    return _orig_determineRecommendHost(self)


def _hooked_tryWgcLogin(self, serverName=None):
    if _CONFIG.get('enabled', True) and _CONFIG.get('auto_connect_max_online', True):
        best_host, max_online = _get_best_online_host()
        if best_host and max_online > 0:
            if serverName is None or serverName == AUTO_LOGIN_QUERY_URL:
                serverName = best_host.url
                if hasattr(self, '_preferences') and isinstance(self._preferences, dict):
                    self._preferences['server_name'] = best_host.url
                LOG_NOTE('[ServerOnline] WGC auto-connect selected server: %s' % best_host.name)
    return _orig_tryWgcLogin(self, serverName)


def _hooked_onLogin(self, userName, password, serverName, isSocialToken2Login):
    if _CONFIG.get('enabled', True) and _CONFIG.get('auto_connect_max_online', True):
        best_host, max_online = _get_best_online_host()
        if best_host and max_online > 0 and serverName == AUTO_LOGIN_QUERY_URL:
            serverName = best_host.url
            LOG_NOTE('[ServerOnline] LoginView auto-connect selected server: %s' % best_host.name)
    return _orig_onLogin(self, userName, password, serverName, isSocialToken2Login)


def _hooked_LoginView_populate(self):
    global _ACTIVE_LOGIN_VIEW
    _orig_LoginView_populate(self)
    _ACTIVE_LOGIN_VIEW = self
    _apply_best_server_selection()
    _apply_login_dropdown_width(self)


def _hooked_LoginView_dispose(self):
    global _ACTIVE_LOGIN_VIEW
    if _ACTIVE_LOGIN_VIEW is self:
        _ACTIVE_LOGIN_VIEW = None
    _orig_LoginView_dispose(self)


def _hooked_ServerStats_populate(self):
    _orig_ServerStats_populate(self)
    _apply_stats_dropdown_width(self)


def _hooked_ServerStats_updateServersList(self):
    _orig_ServerStats_updateServersList(self)
    _apply_stats_dropdown_width(self)


def _on_avatar_become_player(*args, **kwargs):
    global _WAS_IN_BATTLE
    _WAS_IN_BATTLE = True


def _on_account_show_gui(*args, **kwargs):
    global _WAS_IN_BATTLE, _POST_BATTLE_CALLBACK_ID, _POST_BATTLE_FRESH, _POST_BATTLE_WAITS
    if _WAS_IN_BATTLE:
        _WAS_IN_BATTLE = False
        _POST_BATTLE_FRESH = False
        _POST_BATTLE_WAITS = 0
        _request_update()
        if _POST_BATTLE_CALLBACK_ID is not None:
            try:
                BigWorld.cancelCallback(_POST_BATTLE_CALLBACK_ID)
            except Exception:
                pass
        _POST_BATTLE_CALLBACK_ID = BigWorld.callback(2.0, _post_battle_check_timer)


def _post_battle_check_timer():
    global _POST_BATTLE_CALLBACK_ID, _POST_BATTLE_WAITS
    if not _IS_FETCHING and not _POST_BATTLE_FRESH:
        _POST_BATTLE_WAITS += 1
    if _IS_FETCHING or (not _POST_BATTLE_FRESH and _POST_BATTLE_WAITS < 3):
        _POST_BATTLE_CALLBACK_ID = BigWorld.callback(1.0, _post_battle_check_timer)
        return
    _POST_BATTLE_CALLBACK_ID = None
    if not _POST_BATTLE_FRESH:
        LOG_NOTE('[ServerOnline] Post-battle fetch failed; relogin check skipped')
        return
    _check_post_battle_relogin()


def _check_post_battle_relogin():
    if not _CONFIG.get('enabled', True) or not _CONFIG.get('post_battle_relogin_enabled', True):
        return
    try:
        import constants
        from helpers import dependency
        from skeletons.connection_mgr import IConnectionManager
        from skeletons.gui.game_control import IReloginController

        conn_mgr = dependency.instance(IConnectionManager)
        relogin_ctrl = dependency.instance(IReloginController)
        is_conn = conn_mgr.isConnected() if callable(getattr(conn_mgr, 'isConnected', None)) else getattr(conn_mgr, 'isConnected', False)
        if not conn_mgr or not is_conn:
            return
        if not relogin_ctrl or relogin_ctrl.isActive:
            return

        try:
            from gui.prb_control.dispatcher import g_prbLoader
            dispatcher = g_prbLoader.getDispatcher()
            if dispatcher and dispatcher.getEntity().hasLockedState():
                return
        except Exception:
            pass

        current_periphery_id = conn_mgr.peripheryID
        if not current_periphery_id or current_periphery_id == constants.STANDALONE_CLUSTER_ID:
            return

        current_host = g_preDefinedHosts.periphery(current_periphery_id)
        if not current_host and conn_mgr.url:
            current_host = g_preDefinedHosts.byUrl(conn_mgr.url)

        current_online = _get_server_online(current_host)
        if current_online is None or current_online <= 0:
            LOG_NOTE('[ServerOnline] Current server online unknown; post-battle check skipped')
            return

        best_host, max_online = _get_best_online_host()
        if not best_host or max_online <= 0 or best_host.peripheryID == current_periphery_id:
            return

        threshold = float(_CONFIG.get('relogin_ratio_threshold', 1.5))
        ratio = float(max_online) / float(current_online)
        if ratio >= threshold:
            current_name = getattr(current_host, 'name', str(current_periphery_id))
            LOG_NOTE('[ServerOnline] Post-battle relogin: %s (%d) -> %s (%d), ratio %.2f >= %.2f' % (
                current_name, current_online, best_host.name, max_online, ratio, threshold
            ))
            try:
                from gui import SystemMessages
                msg_text = u'[ServerOnline] Автоперехід на %s: онлайн %s проти %s (у %.1f× більше)' % (
                    getattr(best_host, 'name', u'сервер'),
                    _format_online(max_online),
                    _format_online(current_online),
                    ratio
                )
                SystemMessages.pushMessage(msg_text, type=SystemMessages.SM_TYPE.Information)
            except Exception:
                pass
            # ReloginController leaves prebattle queue before cluster switch — 2026-10-11
            relogin_ctrl.doRelogin(best_host.peripheryID)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def init():
    global _orig_makeVO, _orig_determineRecommendHost, _orig_tryWgcLogin
    global _orig_onLogin, _orig_LoginView_populate, _orig_LoginView_dispose
    global _orig_ServerStats_populate, _orig_ServerStats_updateServersList

    _load_config()
    _load_cache()

    _orig_makeVO = ServersDataProvider._makeVO
    ServersDataProvider._makeVO = _hooked_makeVO

    _orig_determineRecommendHost = g_preDefinedHosts.__class__._determineRecommendHost
    g_preDefinedHosts.__class__._determineRecommendHost = _hooked_determineRecommendHost

    _orig_tryWgcLogin = LoginManager.tryWgcLogin
    LoginManager.tryWgcLogin = _hooked_tryWgcLogin

    _orig_onLogin = LoginView.onLogin
    LoginView.onLogin = _hooked_onLogin

    _orig_LoginView_populate = LoginView._populate
    LoginView._populate = _hooked_LoginView_populate

    _orig_LoginView_dispose = LoginView._dispose
    LoginView._dispose = _hooked_LoginView_dispose

    _orig_ServerStats_populate = ServerStats._populate
    ServerStats._populate = _hooked_ServerStats_populate

    _orig_ServerStats_updateServersList = ServerStats._updateServersList
    ServerStats._updateServersList = _hooked_ServerStats_updateServersList

    g_playerEvents.onAvatarBecomePlayer += _on_avatar_become_player
    g_playerEvents.onAccountShowGUI += _on_account_show_gui

    if _CONFIG.get('fetch_on_start', True):
        _request_update()
    try:
        BigWorld.callback(0.1, _init_mods_settings)
    except Exception:
        _init_mods_settings()
    LOG_NOTE('[ServerOnline] Mod initialized successfully')


def fini():
    global _POST_BATTLE_CALLBACK_ID
    if _POST_BATTLE_CALLBACK_ID is not None:
        try:
            BigWorld.cancelCallback(_POST_BATTLE_CALLBACK_ID)
        except Exception:
            pass
        _POST_BATTLE_CALLBACK_ID = None

    try:
        g_playerEvents.onAvatarBecomePlayer -= _on_avatar_become_player
    except Exception:
        pass
    try:
        g_playerEvents.onAccountShowGUI -= _on_account_show_gui
    except Exception:
        pass

    if _orig_makeVO is not None:
        ServersDataProvider._makeVO = _orig_makeVO
    if _orig_determineRecommendHost is not None:
        g_preDefinedHosts.__class__._determineRecommendHost = _orig_determineRecommendHost
    if _orig_tryWgcLogin is not None:
        LoginManager.tryWgcLogin = _orig_tryWgcLogin
    if _orig_onLogin is not None:
        LoginView.onLogin = _orig_onLogin
    if _orig_LoginView_populate is not None:
        LoginView._populate = _orig_LoginView_populate
    if _orig_LoginView_dispose is not None:
        LoginView._dispose = _orig_LoginView_dispose
    if _orig_ServerStats_populate is not None:
        ServerStats._populate = _orig_ServerStats_populate
    if _orig_ServerStats_updateServersList is not None:
        ServerStats._updateServersList = _orig_ServerStats_updateServersList

    LOG_NOTE('[ServerOnline] Mod unloaded successfully')

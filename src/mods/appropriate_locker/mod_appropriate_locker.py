# -*- coding: utf-8 -*-
from __future__ import absolute_import

import logging
import math
import random
import weakref

import AvatarInputHandler as _input_handler
import BattleReplay
import BigWorld
import Keys
import Math
import TriggersManager
from AimSound import AimSound
from Avatar import PlayerAvatar
from AvatarInputHandler import cameras
from TriggersManager import TRIGGER_TYPE
from Vehicle import Vehicle
from VehicleGunRotator import VehicleGunRotator
from arena_bonus_type_caps import ARENA_BONUS_TYPE_CAPS
from constants import AIMING_MODE


VERSION = '1.2.2'
_MODES = ('arcade', 'sniper', 'dualgun', 'twinGun')
_DEATH_MODES = ('postmortem', 'deathfreecam', 'respawn', 'killcam', 'lookAtKiller')
_RAY_LENGTH = 100000.0
# > MagneticAimSettings.KEY_DELAY_SEC (0.5 s) blocks RMB-up magnetic re-lock. — 2026-11-01
_MAGNETIC_COOLDOWN = 0.6
_SWAY_MOVE = 0.07
_SWAY_IDLE = 0.014
_STOP_DELAY = 0.25
_MOVE_FLOOR_SQ = 4e-06
_MOVE_SPEED_SQ = 4e-04
_SNAP_DIST = 0.0005
_TAU_MOVE = 0.22
_TAU_DECAY = 0.10
_TAU_IDLE = 0.35
_TWO_PI = 2.0 * math.pi
_INDICATOR_SEC = 2.0
_TEXT_PRECISE = u'ЗАХОПЛЕННЯ ПРИЦІЛУ: ТОЧНЕ'
_TEXT_STANDARD = u'ЗАХОПЛЕННЯ ПРИЦІЛУ: СТАНДАРТНЕ'
# Priority below every native hint so battle tips still win the single hint slot. — 2026-11-01
_HINT_PRIORITY = 100
_HINT_ID = 'ua.appropriate_locker.mode'
_logger = logging.getLogger('AppropriateLocker')
_active = None
_unlock_until = 0.0
_hooks = []
_native_auto_aim = PlayerAvatar.autoAim
_enabled = False
_panel_ref = None
_hint_factory = None
_hide_id = None


def _finite(point):
    x, y, z = point.x, point.y, point.z
    return (x - x) == 0.0 and (y - y) == 0.0 and (z - z) == 0.0


def _aim_offset(handler):
    ctrl = getattr(handler, 'ctrl', None)
    offset = getattr(ctrl, '_aimOffset', None)
    if offset is None:
        return (0.0, 0.0)
    x = offset.x if hasattr(offset, 'x') else offset[0]
    y = offset.y if hasattr(offset, 'y') else offset[1]
    if (x - x) != 0.0 or (y - y) != 0.0:
        return None
    return (x, y)


def _in_cooldown():
    rem = _unlock_until - BigWorld.time()
    return 0.0 < rem <= _MAGNETIC_COOLDOWN


def _clear_target_lock(handler):
    if handler is None:
        return
    cur = getattr(handler, 'ctrl', None)
    # MapCaseMode.setAimingMode indexes prevCtlMode=None when never activated. — 2026-11-01
    if cur is not None and getattr(cur, 'prevCtlMode', True) is not None:
        try:
            handler.setAimingMode(False, AIMING_MODE.TARGET_LOCK)
        except (AttributeError, TypeError):
            pass
    elif cur is None and hasattr(handler, 'setAimingMode'):
        try:
            handler.setAimingMode(False, AIMING_MODE.TARGET_LOCK)
        except (AttributeError, TypeError):
            pass
    ctrls = getattr(handler, '_AvatarInputHandler__ctrls', None)
    if isinstance(ctrls, dict):
        for ctrl in ctrls.values():
            if (ctrl is not None and hasattr(ctrl, 'setAimingMode')
                    and getattr(ctrl, 'prevCtlMode', True) is not None):
                try:
                    ctrl.setAimingMode(False, AIMING_MODE.TARGET_LOCK)
                except (AttributeError, TypeError):
                    pass


def _can_control(avatar):
    if BigWorld.player() is not avatar or BattleReplay.g_replayCtrl.isPlaying:
        return False
    if not avatar.isOnArena or avatar.isObserver():
        return False
    handler = avatar.inputHandler
    if handler is None or handler.ctrlModeName not in _MODES:
        return False
    own = BigWorld.entity(avatar.playerVehicleID)
    return (own is not None and own.isStarted and own.isAlive()
            and avatar.getVehicleAttached() is own)


def _enemy(avatar, target):
    return (isinstance(target, Vehicle) and target.id != avatar.playerVehicleID
            and target.publicInfo['team'] != avatar.team
            and target.isStarted and not target.isHidden and target.isAlive())


class AppropriateLocker(object):

    def __init__(self, avatar, target, collisions, part_index, local_point):
        self.avatar = weakref.ref(avatar)
        self.target = weakref.ref(target)
        self.target_id = target.id
        self.own_id = avatar.playerVehicleID
        self.rotator = avatar.gunRotator
        self.collisions = collisions
        self.part_index = part_index
        self.local_point = local_point
        self.previous_source = self.rotator.shotPointSourceFunctor
        now = BigWorld.time()
        init_base = collisions.getPartTransform(part_index).applyPoint(local_point)
        own = BigWorld.entity(self.own_id)
        self._rng = random.Random()
        self._last_time = now
        self._last_move = now - _STOP_DELAY
        self._prev_base = (init_base.x, init_base.y, init_base.z)
        self._prev_own = (
            (own.position.x, own.position.y, own.position.z) if own is not None else None)
        self._cx = 0.0
        self._cy = 0.0
        self._tx = 0.0
        self._ty = 0.0
        self._hold = self._rng.uniform(0.3, 0.6)
        self._moving = False
        self._decaying = False

    def _pick_target(self, radius, min_frac=0.15, min_step=0.0):
        rng = self._rng
        tx, ty = 0.0, 0.0
        for _ in range(6):
            angle = rng.uniform(0.0, _TWO_PI)
            mag = radius * math.sqrt(rng.uniform(min_frac, 1.0))
            tx = mag * math.cos(angle)
            ty = mag * math.sin(angle)
            if math.hypot(tx - self._cx, ty - self._cy) >= min_step:
                self._tx, self._ty = tx, ty
                return
        self._tx, self._ty = tx, ty

    def _apply_sway(self, base, own_pos):
        now = BigWorld.time()
        dt = now - self._last_time
        bx, by, bz = base.x, base.y, base.z
        ox, oy, oz = own_pos.x, own_pos.y, own_pos.z
        if dt < 0.0:
            self._last_time = now
            self._last_move = now - _STOP_DELAY
            self._prev_base = (bx, by, bz)
            self._prev_own = (ox, oy, oz)
        elif dt > 0.0:
            self._last_time = now
            eps_sq = max(_MOVE_FLOOR_SQ, _MOVE_SPEED_SQ * dt * dt)
            pbx, pby, pbz = self._prev_base
            moved = (bx - pbx) ** 2 + (by - pby) ** 2 + (bz - pbz) ** 2 > eps_sq
            if not moved and self._prev_own is not None:
                pox, poy, poz = self._prev_own
                moved = (ox - pox) ** 2 + (oy - poy) ** 2 + (oz - poz) ** 2 > eps_sq
            self._prev_base = (bx, by, bz)
            self._prev_own = (ox, oy, oz)
            if moved:
                self._last_move = now
            moving = (now - self._last_move) < _STOP_DELAY
            if moving:
                if not self._moving:
                    self._moving = True
                    self._decaying = False
                    self._pick_target(_SWAY_MOVE, 0.2, 0.015)
                    self._hold = self._rng.uniform(0.2, 0.6)
                if math.hypot(self._tx - self._cx, self._ty - self._cy) <= 0.006:
                    self._hold -= dt
                    if self._hold <= 0.0:
                        self._pick_target(_SWAY_MOVE, 0.2, 0.015)
                        self._hold = self._rng.uniform(0.2, 0.6)
                alpha = 1.0 - math.exp(-dt / _TAU_MOVE)
                self._cx += (self._tx - self._cx) * alpha
                self._cy += (self._ty - self._cy) * alpha
            else:
                if self._moving:
                    self._moving = False
                    self._decaying = True
                    self._pick_target(_SWAY_IDLE * 0.5, 0.0, 0.0)
                    self._hold = self._rng.uniform(0.8, 2.0)
                if self._decaying:
                    alpha = 1.0 - math.exp(-dt / _TAU_DECAY)
                    self._cx += (self._tx - self._cx) * alpha
                    self._cy += (self._ty - self._cy) * alpha
                    if math.hypot(self._cx, self._cy) <= _SWAY_IDLE:
                        self._decaying = False
                        if math.hypot(self._tx - self._cx, self._ty - self._cy) <= _SNAP_DIST:
                            self._cx, self._cy = self._tx, self._ty
                elif self._cx == self._tx and self._cy == self._ty:
                    self._hold -= dt
                    if self._hold <= 0.0:
                        self._pick_target(_SWAY_IDLE, 0.2, 0.004)
                else:
                    alpha = 1.0 - math.exp(-dt / _TAU_IDLE)
                    self._cx += (self._tx - self._cx) * alpha
                    self._cy += (self._ty - self._cy) * alpha
                    if math.hypot(self._tx - self._cx, self._ty - self._cy) <= _SNAP_DIST:
                        self._cx, self._cy = self._tx, self._ty
                        self._hold = self._rng.uniform(0.8, 2.0)
        cx, cy = self._cx, self._cy
        if cx == 0.0 and cy == 0.0:
            return base
        dx, dy, dz = bx - ox, by - oy, bz - oz
        horiz_sq = dx * dx + dz * dz
        if horiz_sq > 1e-08:
            horiz = math.sqrt(horiz_sq)
            dist = math.sqrt(horiz_sq + dy * dy)
            rx = dz / horiz
            rz = -dx / horiz
            inv = 1.0 / (dist * horiz)
            ux = -dx * dy * inv
            uy = horiz / dist
            uz = -dy * dz * inv
        else:
            rx, rz = 1.0, 0.0
            ux, uy, uz = 0.0, 0.0, 1.0
        return Math.Vector3(
            bx + rx * cx + ux * cy,
            by + uy * cy,
            bz + rz * cx + uz * cy)

    def shot_point(self):
        try:
            avatar = self.avatar()
            if (avatar is None or BigWorld.player() is not avatar
                    or BattleReplay.g_replayCtrl.isPlaying
                    or not avatar.isOnArena or avatar.isObserver()
                    or avatar.playerVehicleID != self.own_id
                    or avatar.gunRotator is not self.rotator
                    or getattr(avatar, '_PlayerAvatar__autoAimVehID', 0) != self.target_id):
                _release(self)
                return None
            own = BigWorld.entity(self.own_id)
            if (own is None or not own.isStarted or not own.isAlive()
                    or avatar.getVehicleAttached() is not own
                    or not _finite(own.position)):
                _release(self)
                return None
            handler = avatar.inputHandler
            if handler is None or handler.ctrlModeName not in _MODES:
                sound = (None if handler is None or handler.ctrlModeName in _DEATH_MODES
                         else AimSound.TARGET_UNLOCKED)
                _release(self, sound)
                return None
            target = self.target()
            if (target is None or BigWorld.entity(self.target_id) is not target
                    or not _enemy(avatar, target)
                    or getattr(getattr(target, 'appearance', None), 'collisions', None) is not self.collisions):
                _release(self, AimSound.TARGET_LOST, target is None or target.isAlive())
                return None
            matrix = self.collisions.getPartTransform(self.part_index)
            base = matrix.applyPoint(self.local_point)
            if not _finite(base):
                raise ValueError('Non-finite target part transform')
            point = self._apply_sway(base, own.position)
            if not _finite(point):
                raise ValueError('Non-finite sway shot point')
            return point
        except Exception:
            _logger.exception('Appropriate locker tick failed; releasing')
            _release(self, AimSound.TARGET_LOST)
            return None


def _capture(avatar, target):
    offset = _aim_offset(avatar.inputHandler)
    if offset is None:
        return None
    direction, origin = cameras.getWorldRayAndPoint(offset[0], offset[1])
    direction = Math.Vector3(direction)
    if not _finite(origin) or not _finite(direction) or direction.length < 1e-08:
        return None
    direction.normalise()
    end = origin + direction * _RAY_LENGTH
    # Raw raycast keeps partIndex; 128 = TRIANGLE_PROJECTILENOCOLLIDE. — 2026-11-01
    hit = BigWorld.wg_collideDynamicStatic(
        avatar.spaceID, origin, end, 128, avatar.playerVehicleID, -1, 0)
    if hit is None or not hit[1] or hit[2] != target.id or not _finite(hit[0]):
        return None
    appearance = getattr(target, 'appearance', None)
    collisions = getattr(appearance, 'collisions', None)
    if collisions is None:
        return None
    part_index = hit[3]
    max_static = getattr(collisions, 'maxStaticPartIndex', None)
    # Parts > maxStaticPartIndex (wheels, CGF) spin or detach → track parent. — 2026-11-01
    if max_static is not None:
        hops = 0
        while part_index > max_static:
            if hops >= 4:
                return None
            parent = collisions.getParentPartIndex(part_index)
            if parent is None or parent < 0 or parent == part_index:
                return None
            part_index = parent
            hops += 1
    inverse = Math.Matrix(collisions.getPartTransform(part_index))
    if inverse.invert() is False:
        return None
    local = inverse.applyPoint(hit[0])
    if not _finite(local):
        return None
    return (collisions, part_index, local)


def _release(state=None, sound=None, voice=True):
    global _active
    state = _active if state is None else state
    if state is None or _active is not state:
        return
    _active = None
    avatar = state.avatar()
    rotator = state.rotator
    previous_source = state.previous_source
    try:
        current_id = getattr(avatar, '_PlayerAvatar__autoAimVehID', 0) if avatar is not None else 0
        if rotator is not None:
            if rotator.shotPointSourceFunctor == state.shot_point:
                rotator.shotPointSourceFunctor = previous_source
            if (avatar is not None and avatar.gunRotator is rotator
                    and current_id in (0, state.target_id)):
                rotator.clientMode = True
        if avatar is not None and current_id == state.target_id:
            avatar._PlayerAvatar__autoAimVehID = 0
            _clear_target_lock(avatar.inputHandler)
            manager = TriggersManager.g_manager
            if manager is not None:
                manager.deactivateTrigger(TRIGGER_TYPE.AUTO_AIM_AT_VEHICLE)
            if (sound is not None and BigWorld.player() is avatar
                    and avatar.isOnArena and not BattleReplay.g_replayCtrl.isPlaying):
                avatar.onLockTarget(sound, bool(voice))
        elif avatar is not None and current_id == 0:
            _clear_target_lock(avatar.inputHandler)
    except Exception:
        _logger.exception('Appropriate locker cleanup failed')
    finally:
        state.rotator = None
        state.collisions = None
        state.previous_source = None


def _start(avatar, target, captured, announce=True):
    global _active
    state = None
    try:
        _release()
        if getattr(avatar, '_PlayerAvatar__autoAimVehID', 0) != 0:
            avatar.cell.autoAim(0, False)
            avatar._PlayerAvatar__autoAimVehID = 0
        state = AppropriateLocker(avatar, target, *captured)
        _active = state
        state.rotator.shotPointSourceFunctor = state.shot_point
        # Server cell.autoAim(nonzero) forces center lock → set client ID only. — 2026-11-01
        avatar._PlayerAvatar__autoAimVehID = state.target_id
        avatar.inputHandler.setAimingMode(True, AIMING_MODE.TARGET_LOCK)
        state.rotator.clientMode = True
        if announce:
            avatar.onLockTarget(AimSound.TARGET_LOCKED, True)
        manager = TriggersManager.g_manager
        if manager is not None:
            manager.activateTrigger(
                TRIGGER_TYPE.AUTO_AIM_AT_VEHICLE, vehicleId=state.target_id)
        return state
    except Exception:
        _logger.exception('Appropriate locker acquisition failed')
        if state is not None:
            _release(state)
        return None


def _hand_over_to_native(avatar):
    state = _active
    if state is None:
        return
    target = state.target()
    _release()
    if (avatar is not None and target is not None and BigWorld.player() is avatar
            and _can_control(avatar) and _enemy(avatar, target)):
        _native_auto_aim(avatar, target, False)


def _upgrade_to_precise(avatar):
    if _active is not None or avatar is None:
        return
    target_id = getattr(avatar, '_PlayerAvatar__autoAimVehID', 0)
    if not target_id:
        return
    target = BigWorld.entity(target_id)
    if target is None or not _enemy(avatar, target):
        return
    captured = _capture(avatar, target)
    if captured is None:
        return
    _start(avatar, target, captured, announce=False)


def _set_enabled(value, avatar=None):
    global _enabled
    value = bool(value)
    if value == _enabled:
        return
    _enabled = value
    if avatar is None:
        avatar = BigWorld.player()
    try:
        if value:
            _upgrade_to_precise(avatar)
        else:
            _hand_over_to_native(avatar)
    except Exception:
        _logger.exception('Mode switch failed')
    _refresh_indicator()


def _reset_mode():
    global _enabled
    _enabled = False


def _hide_indicator():
    global _hide_id
    _hide_id = None
    panel = _panel_ref() if _panel_ref is not None else None
    if panel is None:
        return
    try:
        panel.removeBtnHint(_HINT_ID)
    except Exception:
        _logger.exception('Mode indicator hide failed')


def _schedule_hide():
    global _hide_id
    if _hide_id is not None:
        callback_id, _hide_id = _hide_id, None
        try:
            BigWorld.cancelCallback(callback_id)
        except Exception:
            _logger.exception('Mode indicator timer cancel failed')
    _hide_id = BigWorld.callback(_INDICATOR_SEC, _hide_indicator)


def _refresh_indicator():
    panel = _panel_ref() if _panel_ref is not None else None
    if panel is None or _hint_factory is None:
        return
    text = _TEXT_PRECISE if _enabled else _TEXT_STANDARD
    try:
        panel.removeBtnHint(_HINT_ID)
        # vKey is a String on the Flash side; 0 fails DAAPI cast and drops the whole hint — 2026-11-09
        panel.setBtnHint(_HINT_ID, _hint_factory(
            '', '', False, '', text, 0, 0, _HINT_PRIORITY, False, None, False))
        _schedule_hide()
    except Exception:
        _logger.exception('Mode indicator refresh failed')


def _toggle_key(event):
    try:
        if event.isRepeatedEvent() or event.key != Keys.KEY_Q or not event.isKeyDown():
            return False
    except Exception:
        return False
    avatar = BigWorld.player()
    if not _can_control(avatar):
        return False
    _set_enabled(not _enabled, avatar)
    return True


def _auto_aim(avatar, target=None, magnetic=False, *args, **kwargs):
    global _active, _unlock_until
    state = None
    if not _enabled:
        if _active is not None and _active.avatar() is avatar:
            _release()
        return _native_auto_aim(avatar, target, magnetic, *args, **kwargs)
    try:
        if _active is not None and _active.avatar() is not avatar and BigWorld.player() is avatar:
            _release()
        if not _can_control(avatar):
            if _active is not None and _active.avatar() is avatar:
                if magnetic:
                    return None
                was_same = (target is not None
                            and getattr(target, 'id', None) == _active.target_id)
                _unlock_until = BigWorld.time() + _MAGNETIC_COOLDOWN
                mode = getattr(avatar.inputHandler, 'ctrlModeName', None)
                sound = (AimSound.TARGET_UNLOCKED
                         if (target is None or was_same) and avatar.isOnArena
                         and not BattleReplay.g_replayCtrl.isPlaying
                         and mode not in _DEATH_MODES
                         else None)
                _release(sound=sound)
                if target is None or was_same:
                    return None
            elif magnetic and _in_cooldown():
                return None
            return _native_auto_aim(avatar, target, magnetic, *args, **kwargs)
        if avatar.hasBonusCap(ARENA_BONUS_TYPE_CAPS.DISABLE_AUTO_AIM):
            return None
        if magnetic:
            if (_active is not None and _active.avatar() is avatar) or _in_cooldown():
                return None
            return _native_auto_aim(avatar, target, magnetic, *args, **kwargs)
        native_id = getattr(avatar, '_PlayerAvatar__autoAimVehID', 0)
        target_id = getattr(target, 'id', None) if target is not None else None
        same = (_active is not None and _active.avatar() is avatar
                and target_id == _active.target_id)
        same_native = native_id != 0 and target_id == native_id
        if target is None or same or same_native or not _enemy(avatar, target):
            if _active is not None and _active.avatar() is avatar:
                _unlock_until = BigWorld.time() + _MAGNETIC_COOLDOWN
                _release(sound=AimSound.TARGET_UNLOCKED)
                return None
            if native_id != 0:
                _unlock_until = BigWorld.time() + _MAGNETIC_COOLDOWN
                return _native_auto_aim(avatar, None, False)
            if target is None:
                _clear_target_lock(avatar.inputHandler)
            return _native_auto_aim(avatar, None, False)
        captured = _capture(avatar, target)
        if captured is None:
            _logger.debug('No enemy surface under reticle; tracking not started')
            return None
        _start(avatar, target, captured)
        return None
    except Exception:
        _logger.exception('Appropriate locker acquisition failed')
        if state is not None:
            _release(state)
        return None


def _prediction(original):
    fn = getattr(original, 'im_func', original)

    def wrapped(rotator, *args, **kwargs):
        if _active is not None and _active.rotator is rotator:
            return _active.shot_point()
        return fn(rotator, *args, **kwargs)
    return wrapped


def _avatar_cleanup(original):
    fn = getattr(original, 'im_func', original)

    def wrapped(avatar, *args, **kwargs):
        global _unlock_until
        if _active is not None and _active.avatar() is avatar:
            _release()
        _unlock_until = 0.0
        _reset_mode()
        return fn(avatar, *args, **kwargs)
    return wrapped


def _key_event(original):
    fn = getattr(original, 'im_func', original)

    def wrapped(handler, event, *args, **kwargs):
        try:
            if _toggle_key(event):
                return True
        except Exception:
            _logger.exception('Toggle key handling failed')
        return fn(handler, event, *args, **kwargs)
    return wrapped


def _panel_populate(original):
    fn = getattr(original, 'im_func', original)

    def wrapped(panel, *args, **kwargs):
        global _panel_ref
        _panel_ref = weakref.ref(panel)
        result = fn(panel, *args, **kwargs)
        _reset_mode()
        return result
    return wrapped


def _panel_dispose(original):
    fn = getattr(original, 'im_func', original)

    def wrapped(panel, *args, **kwargs):
        global _panel_ref, _hide_id
        if _panel_ref is not None and _panel_ref() is panel:
            _panel_ref = None
        if _hide_id is not None:
            callback_id, _hide_id = _hide_id, None
            try:
                BigWorld.cancelCallback(callback_id)
            except Exception:
                _logger.exception('Mode indicator timer cancel failed')
        return fn(panel, *args, **kwargs)
    return wrapped


def _vehicle_leave(original):
    fn = getattr(original, 'im_func', original)

    def wrapped(avatar, vehicle, *args, **kwargs):
        if _active is not None and _active.avatar() is avatar and vehicle is not None:
            vid = getattr(vehicle, 'id', None)
            if vid == _active.target_id:
                alive = bool(getattr(vehicle, 'isAlive', lambda: True)())
                _release(sound=AimSound.TARGET_LOST, voice=alive)
            elif vid == _active.own_id:
                _release()
        return fn(avatar, vehicle, *args, **kwargs)
    return wrapped


def _rotator_stop(original):
    fn = getattr(original, 'im_func', original)

    def wrapped(rotator, *args, **kwargs):
        if _active is not None and _active.rotator is rotator:
            _release()
        return fn(rotator, *args, **kwargs)
    return wrapped


def _server_lost(original):
    fn = getattr(original, 'im_func', original)

    def wrapped(avatar, *args, **kwargs):
        if _active is not None and _active.avatar() is avatar:
            return None
        return fn(avatar, *args, **kwargs)
    return wrapped


def _hook(owner, name, replacement):
    original = getattr(owner, name)
    _hooks.append((owner, name, original, replacement))
    setattr(owner, name, replacement)


def _install_indicator():
    global _hint_factory
    if _hint_factory is not None:
        return
    try:
        from gui.Scaleform.daapi.view.battle.shared.hint_panel.component import (
            BattleHintPanel)
        from gui.Scaleform.daapi.view.battle.shared.hint_panel.hint_panel_plugin import (
            HintData)
        _hook(BattleHintPanel, '_populate',
              _panel_populate(BattleHintPanel._populate))
        _hook(BattleHintPanel, '_dispose',
              _panel_dispose(BattleHintPanel._dispose))
    except Exception:
        _logger.exception('Mode indicator unavailable')
        return
    _hint_factory = HintData


def init():
    global _native_auto_aim, _unlock_until, _enabled
    if _hooks:
        return
    _unlock_until = 0.0
    _enabled = False
    _native_auto_aim = PlayerAvatar.autoAim
    try:
        handler = _input_handler.AvatarInputHandler
        _hook(PlayerAvatar, 'autoAim', _auto_aim)
        _hook(PlayerAvatar, 'onBecomeNonPlayer', _avatar_cleanup(PlayerAvatar.onBecomeNonPlayer))
        _hook(PlayerAvatar, 'onLeaveWorld', _avatar_cleanup(PlayerAvatar.onLeaveWorld))
        _hook(PlayerAvatar, 'vehicle_onLeaveWorld', _vehicle_leave(PlayerAvatar.vehicle_onLeaveWorld))
        _hook(PlayerAvatar, 'onAutoAimVehicleLost', _server_lost(PlayerAvatar.onAutoAimVehicleLost))
        _hook(VehicleGunRotator, 'stop', _rotator_stop(VehicleGunRotator.stop))
        _hook(VehicleGunRotator, 'predictLockedTargetShotPoint',
              _prediction(VehicleGunRotator.predictLockedTargetShotPoint))
        _hook(handler, 'handleKeyEvent', _key_event(handler.handleKeyEvent))
    except Exception:
        fini()
        _logger.exception('API mismatch; hooks removed')
        return
    _install_indicator()
    _logger.info('Appropriate Locker %s initialized', VERSION)


def fini():
    global _unlock_until, _enabled, _hint_factory, _panel_ref, _hide_id
    _unlock_until = 0.0
    _enabled = False
    _release()
    if _hide_id is not None:
        callback_id, _hide_id = _hide_id, None
        try:
            BigWorld.cancelCallback(callback_id)
        except Exception:
            _logger.exception('Mode indicator timer cancel failed')
    _panel_ref = None
    _hint_factory = None
    for owner, name, original, replacement in reversed(_hooks):
        current = getattr(owner, name)
        if getattr(current, 'im_func', current) is replacement:
            setattr(owner, name, original)
    del _hooks[:]

from __future__ import absolute_import, division

import collections
import math
import marshal
import sys
import types
import unittest
import zipfile


class Vector(object):

    def __init__(self, x=0.0, y=None, z=None):
        if y is None and hasattr(x, 'x'):
            self.x, self.y, self.z = x.x, x.y, x.z
        else:
            self.x, self.y, self.z = float(x), float(y or 0), float(z or 0)

    def __add__(self, other):
        return Vector(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, value):
        return Vector(self.x * value, self.y * value, self.z * value)

    @property
    def length(self):
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    def normalise(self):
        length = self.length
        self.x, self.y, self.z = self.x / length, self.y / length, self.z / length

    def values(self):
        return (self.x, self.y, self.z)

    def __eq__(self, other):
        return isinstance(other, Vector) and self.values() == other.values()

    def __ne__(self, other):
        return not self.__eq__(other)


class Matrix(object):

    def __init__(self, source=None, translation=None, rotation=None):
        self.translation = Vector(source.translation if source is not None else translation or Vector())
        self.rotation = (source.rotation if source is not None else rotation
                         or ((1, 0, 0), (0, 1, 0), (0, 0, 1)))

    def applyVector(self, point):
        values = point.values()
        return Vector(*(sum(a * b for a, b in zip(row, values)) for row in self.rotation))

    def applyPoint(self, point):
        return self.applyVector(point) + self.translation

    def invertOrthonormal(self):
        self.rotation = tuple(zip(*self.rotation))
        self.translation = self.applyVector(self.translation) * -1

    def invert(self):
        self.invertOrthonormal()
        return True


class Struct(object):

    def __init__(self, **values):
        self.__dict__.update(values)


def module(name, **values):
    result = types.ModuleType(name)
    result.__dict__.update(values)
    sys.modules[name] = result
    return result


class Cell(object):

    def __init__(self):
        self.auto_aim = []
        self.relative_points = []
        self.world_points = []

    def autoAim(self, target_id, magnetic):
        self.auto_aim.append((target_id, magnetic))

    def trackRelativePointWithGun(self, point):
        self.relative_points.append(point)

    def vehicle_trackWorldPointWithGun(self, point):
        self.world_points.append(point)


class Collision(object):

    def __init__(self):
        self.transforms = {1: Matrix(), 2: Matrix(), 3: Matrix()}
        self.parents = {}

    def getPartTransform(self, part):
        return self.transforms[part]

    def getParentPartIndex(self, part):
        return self.parents.get(part)


class Vehicle(object):

    def __init__(self, vehicle_id, team):
        self.id = vehicle_id
        self.publicInfo = {'team': team}
        self.isStarted = True
        self.isHidden = False
        self.alive = True
        self.appearance = Struct(collisions=Collision())
        self.position = Vector()
        self.matrix = Matrix()
        self.cell = Cell()

    def isAlive(self):
        return self.alive


class InputHandler(object):

    def __init__(self):
        self.ctrlModeName = 'sniper'
        self.lock = False
        self.manual_point = Vector(91, 92, 93)

    def setAimingMode(self, value, mode):
        self.lock = value

    def getAimingMode(self, mode):
        return self.lock

    def getDesiredShotPoint(self, ignoreAimingMode=False):
        return self.manual_point if not self.lock or ignoreAimingMode else None


class Rotator(object):
    USE_LOCK_PREDICTION = True

    def __init__(self, avatar):
        self._avatar = avatar
        self.clientMode = True
        self.shotPointSourceFunctor = self.default_source
        self.stops = 0
        self.rotated_points = []

    def default_source(self):
        return self._avatar.inputHandler.getDesiredShotPoint()

    @property
    def clientMode(self):
        return self._VehicleGunRotator__clientMode

    @clientMode.setter
    def clientMode(self, value):
        self._VehicleGunRotator__clientMode = value

    @property
    def shotPointSourceFunctor(self):
        return self._VehicleGunRotator__shotPointSourceFunctor

    @shotPointSourceFunctor.setter
    def shotPointSourceFunctor(self, value):
        self._VehicleGunRotator__shotPointSourceFunctor = value

    def predictLockedTargetShotPoint(self):
        return Vector(-500, -500, -500)

    def stop(self):
        self.stops += 1

    def updateRotationAndGunMarker(self, point, time_diff):
        self.rotated_points.append(point)


class Avatar(object):

    def __init__(self):
        self.playerVehicleID = 1
        self.spaceID = 7
        self.team = 1
        self.isOnArena = True
        self.observer = False
        self.disabled = False
        self.inputHandler = InputHandler()
        self.cell = Cell()
        self.gunRotator = Rotator(self)
        self._PlayerAvatar__autoAimVehID = 0
        self.sounds = []
        self.departures = []
        self.vehicleTypeDescriptor = Struct(isHullAimingAvailable=False, isYawHullAimingAvailable=False)

    @property
    def autoAimVehicle(self):
        return world.entities.get(self._PlayerAvatar__autoAimVehID)

    @property
    def vehicle(self):
        return world.entities.get(self.playerVehicleID)

    def getVehicleAttached(self):
        return self.vehicle

    def getOwnVehicleStabilisedMatrix(self):
        return Matrix(translation=self.vehicle.position)

    def isObserver(self):
        return self.observer

    def hasBonusCap(self, cap):
        return self.disabled

    def autoAim(self, target=None, magnetic=False):
        target_id = target.id if target is not None else 0
        self.cell.autoAim(target_id, magnetic)
        self._PlayerAvatar__autoAimVehID = target_id
        self.inputHandler.lock = bool(target_id)
        self.gunRotator.clientMode = not bool(target_id)

    def onLockTarget(self, sound, voice):
        self.sounds.append(sound)

    def onBecomeNonPlayer(self):
        self.departures.append('nonplayer')

    def onLeaveWorld(self):
        self.departures.append('leave')

    def vehicle_onLeaveWorld(self, vehicle):
        self.departures.append(('vehicle_leave', vehicle.id))

    def onAutoAimVehicleLost(self, flags):
        self._PlayerAvatar__autoAimVehID = 0
        self.inputHandler.lock = False


world = Struct(player=None, entities={}, hit=None, rays=[], callbacks=[], now=12.0,
               next_callback_id=[1])


def collide(*args):
    world.rays.append(args)
    return world.hit


def schedule(delay, callback):
    callback_id = world.next_callback_id[0]
    world.next_callback_id[0] += 1
    world.callbacks.append([callback_id, callback, False])
    return callback_id


def cancel(callback_id):
    for row in world.callbacks:
        if row[0] == callback_id:
            row[2] = True


def fire_callbacks():
    for row in list(world.callbacks):
        if not row[2]:
            row[2] = True
            row[1]()


replay = Struct(isPlaying=False, isRecording=False)
sounds = Struct(TARGET_LOCKED='locked', TARGET_UNLOCKED='unlocked', TARGET_LOST='lost')
manager = Struct(events=[])
manager.activateTrigger = lambda *a, **kw: manager.events.append(('start', a, kw))
manager.deactivateTrigger = lambda *a, **kw: manager.events.append(('stop', a, kw))
world_api = module('BigWorld', player=lambda: world.player,
                   entity=lambda key: world.entities.get(key), entities=world.entities,
                   wg_collideDynamicStatic=collide, time=lambda: world.now,
                   callback=schedule, cancelCallback=cancel)
module('Math', Matrix=Matrix, Vector3=Vector)
module('BattleReplay', g_replayCtrl=replay)
triggers = Struct(AUTO_AIM_AT_VEHICLE=3)
module('TriggersManager', g_manager=manager, TRIGGER_TYPE=triggers)
module('AimSound', AimSound=sounds)


class KeyEvent(object):

    def __init__(self, key, is_down=True, repeated=False):
        self.key = key
        self.down = is_down
        self.repeated = repeated

    def isKeyDown(self):
        return self.down

    def isRepeatedEvent(self):
        return self.repeated


class InputHandlerClass(object):

    def __init__(self):
        self.events = []

    def handleKeyEvent(self, event):
        self.events.append(event)
        return False


TOGGLE_KEY = 7
OTHER_KEY = 9
module('Keys', KEY_Q=TOGGLE_KEY)
module('Avatar', PlayerAvatar=Avatar)
camera = module('AvatarInputHandler.cameras', getWorldRayAndPoint=lambda x, y: (Vector(0, 0, 1), Vector()))
module('AvatarInputHandler', cameras=camera, AvatarInputHandler=InputHandlerClass)
module('Vehicle', Vehicle=Vehicle)
module('VehicleGunRotator', VehicleGunRotator=Rotator)
caps = Struct(DISABLE_AUTO_AIM=1)
module('arena_bonus_type_caps', ARENA_BONUS_TYPE_CAPS=caps)
aiming = Struct(TARGET_LOCK=2)
module('constants', AIMING_MODE=aiming)


class BattleHintPanel(object):

    instances = []

    def __init__(self):
        self.hints = {}
        self.populated = False
        self.disposed = False
        BattleHintPanel.instances.append(self)

    def _populate(self):
        self.populated = True

    def _dispose(self):
        self.disposed = True

    def setBtnHint(self, btn_id, hint):
        self.hints[btn_id] = hint

    def removeBtnHint(self, btn_id):
        return self.hints.pop(btn_id, None)


HintData = collections.namedtuple(
    'HintData', ('vKey', 'key', 'isKeyLong', 'messageLeft', 'messageRight',
                 'offsetX', 'offsetY', 'priority', 'reducedPanning', 'hintCtx',
                 'centeredMessage'))
for _package in ('gui', 'gui.Scaleform', 'gui.Scaleform.daapi',
                 'gui.Scaleform.daapi.view', 'gui.Scaleform.daapi.view.battle',
                 'gui.Scaleform.daapi.view.battle.shared',
                 'gui.Scaleform.daapi.view.battle.shared.hint_panel'):
    module(_package)
module('gui.Scaleform.daapi.view.battle.shared.hint_panel.component',
       BattleHintPanel=BattleHintPanel)
module('gui.Scaleform.daapi.view.battle.shared.hint_panel.hint_panel_plugin',
       HintData=HintData)

import mod_appropriate_locker as mod


def load_packaged(path):
    global mod
    mod.fini()
    with zipfile.ZipFile(path) as archive:
        data = archive.read('res/scripts/client/gui/mods/mod_appropriate_locker.pyc')
    packaged = types.ModuleType('mod_appropriate_locker_packaged')
    exec(marshal.loads(data[8:]), packaged.__dict__)
    mod = packaged


class AppropriateLockerTests(unittest.TestCase):

    def setUp(self):
        mod.fini()
        world.now = 12.0
        replay.isPlaying = False
        Rotator.USE_LOCK_PREDICTION = True
        self.avatar = Avatar()
        self.own = Vehicle(1, 1)
        self.enemy = Vehicle(2, 2)
        world.player = self.avatar
        world.entities.clear()
        world.entities.update({1: self.own, 2: self.enemy})
        world.rays[:] = []
        world.callbacks[:] = []
        manager.events[:] = []
        world.hit = (Vector(1, 2, 3), True, 2, 2, 0)
        mod.init()
        mod._enabled = True

    def tearDown(self):
        mod.fini()

    def lock(self):
        self.avatar.autoAim(self.enemy)
        self.assertIsNotNone(mod._active)
        return mod._active

    def assertPoint(self, point, expected):
        self.assertIsNotNone(point)
        for actual, wanted in zip(point.values(), expected):
            self.assertAlmostEqual(actual, wanted, places=7)

    def test_capture_preserves_exact_surface(self):
        state = self.lock()
        self.assertPoint(state.shot_point(), (1, 2, 3))
        self.assertEqual(self.avatar.autoAimVehicle, self.enemy)
        self.assertTrue(self.avatar.inputHandler.lock)
        self.assertTrue(self.avatar.gunRotator.clientMode)
        self.assertEqual(self.avatar.cell.auto_aim, [])
        self.assertEqual(self.avatar.sounds, ['locked'])
        self.assertEqual(world.rays[-1][3:], (128, 1, -1, 0))

    def test_translation_follows_part(self):
        state = self.lock()
        self.enemy.appearance.collisions.transforms[2] = Matrix(translation=Vector(10, 20, 30))
        self.assertPoint(state.shot_point(), (11, 22, 33))

    def test_turret_yaw_follows_same_material_point(self):
        self.enemy.appearance.collisions.transforms[2] = Matrix(translation=Vector(10, 0, 30))
        world.hit = (Vector(11, 2, 30), True, 2, 2, 0)
        state = self.lock()
        self.enemy.appearance.collisions.transforms[2] = Matrix(
            translation=Vector(20, 0, 50), rotation=((0, 0, 1), (0, 1, 0), (-1, 0, 0)))
        self.assertPoint(state.shot_point(), (20, 2, 49))

    def test_gun_pitch_independent_of_hull(self):
        world.hit = (Vector(0, 0, 4), True, 2, 3, 0)
        state = self.lock()
        self.enemy.appearance.collisions.transforms[3] = Matrix(
            translation=Vector(0, 2, 10), rotation=((1, 0, 0), (0, 0, -1), (0, 1, 0)))
        self.enemy.appearance.collisions.transforms[1] = Matrix(translation=Vector(999, 999, 999))
        self.assertPoint(state.shot_point(), (0, -2, 10))

    def test_capture_from_already_rotated_part(self):
        self.enemy.appearance.collisions.transforms[2] = Matrix(
            translation=Vector(10, 0, 20), rotation=((0, 0, 1), (0, 1, 0), (-1, 0, 0)))
        world.hit = (Vector(13, 2, 19), True, 2, 2, 0)
        state = self.lock()
        self.assertPoint(state.local_point, (1, 2, 3))
        self.enemy.appearance.collisions.transforms[2] = Matrix()
        self.assertPoint(state.shot_point(), (1, 2, 3))

    def test_hull_point_ignores_turret_motion(self):
        world.hit = (Vector(1, 2, 3), True, 2, 1, 0)
        state = self.lock()
        self.enemy.appearance.collisions.transforms[2] = Matrix(translation=Vector(999, 999, 999))
        self.assertPoint(state.shot_point(), (1, 2, 3))

    def test_missing_surface_never_falls_back_to_center(self):
        for hit in (None, (Vector(), False, 0, 0, 0), (Vector(), True, 3, 1, 0)):
            world.hit = hit
            self.avatar.autoAim(self.enemy)
            self.assertIsNone(mod._active)
            self.assertEqual(self.avatar.cell.auto_aim, [])

    def test_friendly_dead_hidden_and_unstarted_not_acquired(self):
        for field, value in (('publicInfo', {'team': 1}), ('alive', False),
                             ('isHidden', True), ('isStarted', False)):
            old = getattr(self.enemy, field)
            setattr(self.enemy, field, value)
            self.avatar.autoAim(self.enemy)
            self.assertIsNone(mod._active)
            self.assertFalse(any(row[0] for row in self.avatar.cell.auto_aim))
            setattr(self.enemy, field, old)

    def test_repeated_target_unlocks(self):
        previous = self.avatar.gunRotator.shotPointSourceFunctor
        self.lock()
        self.avatar.autoAim(self.enemy)
        self.assertIsNone(mod._active)
        self.assertEqual(self.avatar.gunRotator.shotPointSourceFunctor, previous)
        self.assertFalse(self.avatar.inputHandler.lock)
        self.assertEqual(self.avatar.sounds, ['locked', 'unlocked'])

    def test_explicit_unlock_restores_previous_provider(self):
        provider = lambda: Vector(7, 8, 9)
        self.avatar.gunRotator.shotPointSourceFunctor = provider
        self.lock()
        self.avatar.autoAim(None)
        self.assertIs(self.avatar.gunRotator.shotPointSourceFunctor, provider)
        self.assertPoint(provider(), (7, 8, 9))

    def test_switch_target_recaptures(self):
        self.lock()
        other = Vehicle(3, 2)
        world.entities[3] = other
        world.hit = (Vector(4, 5, 6), True, 3, 1, 0)
        self.avatar.autoAim(other)
        self.assertEqual(mod._active.target_id, 3)
        self.assertPoint(self.avatar.gunRotator.shotPointSourceFunctor(), (4, 5, 6))
        self.assertEqual(self.avatar.cell.auto_aim, [])

    def test_native_center_lock_cleared_before_point_lock(self):
        self.avatar._PlayerAvatar__autoAimVehID = 3
        world.entities[3] = Vehicle(3, 2)
        self.lock()
        self.assertEqual(self.avatar.cell.auto_aim, [(0, False)])
        self.assertTrue(self.avatar.gunRotator.clientMode)

    def test_target_disappearance_releases(self):
        state = self.lock()
        del world.entities[2]
        self.assertIsNone(state.shot_point())
        self.assertIsNone(mod._active)
        self.assertFalse(self.avatar.inputHandler.lock)

    def test_entity_id_reuse_releases(self):
        state = self.lock()
        world.entities[2] = Vehicle(2, 2)
        self.assertIsNone(state.shot_point())

    def test_target_death_or_hidden_releases(self):
        for field in ('alive', 'isHidden', 'isStarted'):
            state = self.lock()
            old = getattr(self.enemy, field)
            setattr(self.enemy, field, not old)
            self.assertIsNone(state.shot_point())
            self.assertIsNone(mod._active)
            setattr(self.enemy, field, old)

    def test_own_death_releases(self):
        state = self.lock()
        self.own.alive = False
        self.assertIsNone(state.shot_point())
        self.assertIsNone(mod._active)

    def test_own_vehicle_change_releases(self):
        state = self.lock()
        self.avatar.playerVehicleID = 3
        world.entities[3] = Vehicle(3, 1)
        self.assertIsNone(state.shot_point())

    def test_collision_model_replacement_releases(self):
        state = self.lock()
        self.enemy.appearance.collisions = Collision()
        self.assertIsNone(state.shot_point())

    def test_rotator_stop_releases(self):
        self.lock()
        self.avatar.gunRotator.stop()
        self.assertIsNone(mod._active)
        self.assertEqual(self.avatar.gunRotator.stops, 1)

    def test_avatar_departure_releases(self):
        for method in ('onBecomeNonPlayer', 'onLeaveWorld'):
            mod._enabled = True
            self.lock()
            getattr(self.avatar, method)()
            self.assertIsNone(mod._active)
            self.assertFalse(self.avatar.inputHandler.lock)
        self.assertEqual(self.avatar.departures, ['nonplayer', 'leave'])

    def test_camera_switch_retains_supported_modes(self):
        state = self.lock()
        for mode in ('arcade', 'sniper', 'dualgun', 'twinGun'):
            self.avatar.inputHandler.ctrlModeName = mode
            self.assertPoint(state.shot_point(), (1, 2, 3))
        self.avatar.inputHandler.ctrlModeName = 'postmortem'
        self.assertIsNone(state.shot_point())

    def test_replay_and_observer_skip_custom_acquisition(self):
        replay.isPlaying = True
        self.avatar.autoAim(self.enemy)
        self.assertIsNone(mod._active)
        self.assertEqual(world.rays, [])
        replay.isPlaying = False
        self.avatar.observer = True
        self.avatar.autoAim(self.enemy)
        self.assertIsNone(mod._active)
        self.assertEqual(world.rays, [])

    def test_arena_disabling_autoaim_respected(self):
        self.avatar.disabled = True
        self.avatar.autoAim(self.enemy)
        self.assertIsNone(mod._active)
        self.assertEqual(self.avatar.cell.auto_aim, [])

    def test_stale_server_loss_does_not_drop_custom_lock(self):
        self.lock()
        self.avatar.onAutoAimVehicleLost(0)
        self.assertIsNotNone(mod._active)
        self.assertEqual(self.avatar.autoAimVehicle, self.enemy)

    def test_provider_replaced_by_other_mod_not_overwritten(self):
        self.lock()
        external = lambda: Vector(55, 55, 55)
        self.avatar.gunRotator.shotPointSourceFunctor = external
        self.avatar.autoAim(None)
        self.assertIs(self.avatar.gunRotator.shotPointSourceFunctor, external)

    def test_init_is_idempotent(self):
        methods = [(owner, name, getattr(owner, name)) for owner, name, _, _ in mod._hooks]
        mod.init()
        self.assertEqual(len(mod._hooks), 10)
        for owner, name, expected in methods:
            self.assertEqual(getattr(owner, name), expected)

    def test_shutdown_preserves_later_external_hook(self):
        ours = Avatar.autoAim
        external = lambda *args, **kwargs: ours(*args, **kwargs)
        Avatar.autoAim = external
        try:
            mod.fini()
            self.assertIs(Avatar.autoAim.im_func, external)
        finally:
            Avatar.autoAim = mod._native_auto_aim

    def test_prediction_routes_only_owned_rotator(self):
        self.lock()
        self.assertPoint(self.avatar.gunRotator.predictLockedTargetShotPoint(), (1, 2, 3))
        self.assertPoint(Rotator(Avatar()).predictLockedTargetShotPoint(), (-500, -500, -500))

    def test_nonfinite_capture_rejected(self):
        world.hit = (Vector(float('nan'), 0, 0), True, 2, 2, 0)
        self.avatar.autoAim(self.enemy)
        self.assertIsNone(mod._active)
        self.assertEqual(self.avatar.cell.auto_aim, [])

    def test_fini_reinit_restores_native_method(self):
        original = mod._native_auto_aim
        self.lock()
        mod.fini()
        self.assertEqual(Avatar.autoAim, original)
        self.assertIsNone(mod._active)
        mod.init()
        self.assertIs(Avatar.autoAim.im_func, mod._auto_aim)
        mod._enabled = True
        self.lock()

    def test_replay_start_releases_existing_lock(self):
        state = self.lock()
        replay.isPlaying = True
        self.assertIsNone(state.shot_point())
        self.assertIsNone(mod._active)

    def test_zero_camera_ray_never_acquires(self):
        original = camera.getWorldRayAndPoint
        camera.getWorldRayAndPoint = lambda x, y: (Vector(), Vector())
        try:
            self.avatar.autoAim(self.enemy)
            self.assertIsNone(mod._active)
        finally:
            camera.getWorldRayAndPoint = original

    def test_magnetic_autoaim_delegates_when_unlocked_and_blocks_on_release_cooldown(self):
        self.avatar.autoAim(self.enemy, True)
        self.assertIsNone(mod._active)
        self.assertEqual(self.avatar.cell.auto_aim, [(2, True)])
        self.avatar.autoAim(None, False)
        self.avatar.cell.auto_aim[:] = []
        world.now = 15.0
        self.lock()
        other = Vehicle(3, 2)
        world.entities[3] = other
        self.avatar.autoAim(other, True)
        self.assertIsNotNone(mod._active)
        self.assertEqual(mod._active.target_id, 2)
        self.assertEqual(self.avatar.cell.auto_aim, [])
        world.now = 20.0
        self.avatar.autoAim(None, False)
        self.assertIsNone(mod._active)
        world.now = 20.3
        self.avatar.autoAim(self.enemy, True)
        self.assertEqual(self.avatar.cell.auto_aim, [])
        self.assertEqual(self.avatar._PlayerAvatar__autoAimVehID, 0)
        world.now = 20.7
        self.avatar.autoAim(self.enemy, True)
        self.assertEqual(self.avatar.cell.auto_aim, [(2, True)])
        self.assertEqual(self.avatar._PlayerAvatar__autoAimVehID, 2)
        world.now = 21.0
        self.avatar.autoAim(self.enemy, False)
        self.assertIsNone(mod._active)
        self.assertEqual(self.avatar._PlayerAvatar__autoAimVehID, 0)
        self.assertEqual(self.avatar.cell.auto_aim[-1], (0, False))
        world.now = 21.2
        self.avatar.autoAim(self.enemy, True)
        self.assertEqual(self.avatar._PlayerAvatar__autoAimVehID, 0)
        world.now = 5.0
        self.avatar.autoAim(self.enemy, True)
        self.assertEqual(self.avatar._PlayerAvatar__autoAimVehID, 2)

    def test_clear_target_lock_clears_all_gun_modes_and_orphan_lock(self):
        class ModeStub(object):
            def __init__(self):
                self.lock = True
            def setAimingMode(self, value, mode):
                self.lock = value

        class MapCaseStub(object):
            prevCtlMode = None
            def __init__(self, active=False):
                if active:
                    self.prevCtlMode = ['arcade', aiming.TARGET_LOCK]
            def setAimingMode(self, value, mode):
                if not value:
                    self.prevCtlMode[1] &= ~mode

        arcade = ModeStub()
        strategic = ModeStub()
        arty = ModeStub()
        inactive_mapcase = MapCaseStub(active=False)
        active_mapcase = MapCaseStub(active=True)
        self.avatar.inputHandler.ctrl = arcade
        self.avatar.inputHandler._AvatarInputHandler__ctrls = {
            'arcade': arcade, 'strategic': strategic, 'arty': arty,
            'mapcase_off': inactive_mapcase, 'mapcase_on': active_mapcase}
        self.lock()
        self.avatar.autoAim(None)
        self.assertFalse(arcade.lock)
        self.assertFalse(strategic.lock)
        self.assertFalse(arty.lock)
        self.assertEqual(active_mapcase.prevCtlMode[1], 0)
        strategic.lock = True
        self.avatar.inputHandler.lock = True
        self.avatar.autoAim(None)
        self.assertFalse(self.avatar.inputHandler.lock)
        self.assertFalse(strategic.lock)

    def test_uncontrolled_mode_race_releases_cleanly_without_center_relock(self):
        self.lock()
        self.avatar.inputHandler.ctrlModeName = 'strategic'
        self.avatar.autoAim(self.enemy, True)
        self.assertIsNotNone(mod._active)
        self.assertEqual(self.avatar.cell.auto_aim, [])
        world.now = 15.0
        self.avatar.autoAim(self.enemy, False)
        self.assertIsNone(mod._active)
        self.assertEqual(self.avatar.cell.auto_aim, [])
        self.assertEqual(self.avatar._PlayerAvatar__autoAimVehID, 0)
        self.assertEqual(self.avatar.sounds, ['locked', 'unlocked'])

    def test_moving_tight_sway_bounded_and_decays_on_stop(self):
        self.own.position = Vector(0, 0, 0)
        world.hit = (Vector(6, 2, 8), True, 2, 2, 0)
        state = self.lock()
        self.assertPoint(state.shot_point(), (6, 2, 8))
        offsets = []
        for step in range(1, 26):
            world.now = 12.0 + step * 0.1
            shift = step * 0.15
            self.enemy.appearance.collisions.transforms[2] = Matrix(translation=Vector(shift, 0, 0))
            base = Vector(6.0 + shift, 2.0, 8.0)
            point = state.shot_point()
            offset = point - base
            los = base - self.own.position
            dot = offset.x * los.x + offset.y * los.y + offset.z * los.z
            self.assertLessEqual(offset.length, 0.070001)
            self.assertLess(abs(dot), 1e-06)
            offsets.append(offset.length)
        self.assertGreater(max(offsets), 0.015)
        final_base = Vector(6.0 + 25 * 0.15, 2.0, 8.0)
        for extra in range(1, 7):
            world.now = 14.5 + extra * 0.1
            settled = state.shot_point()
        self.assertLessEqual((settled - final_base).length, 0.014001)

    def test_stationary_micro_drifter_holds_and_gently_drifts(self):
        self.own.position = Vector(0, 0, 0)
        base = Vector(0, 1, 20)
        world.hit = (base, True, 2, 2, 0)
        state = self.lock()
        points = []
        for step in range(1, 36):
            world.now = 12.0 + step * 0.1
            point = state.shot_point()
            offset = point - base
            los = base - self.own.position
            dot = offset.x * los.x + offset.y * los.y + offset.z * los.z
            self.assertLessEqual(offset.length, 0.014001)
            self.assertLess(abs(dot), 1e-06)
            points.append(point)
        self.assertGreater(max((p - base).length for p in points), 0.002)
        identical = sum(1 for a, b in zip(points, points[1:]) if a.values() == b.values())
        self.assertGreaterEqual(identical, 5)

    def test_disabled_mode_delegates_to_native_without_capture(self):
        mod._enabled = False
        self.avatar.autoAim(self.enemy)
        self.assertIsNone(mod._active)
        self.assertEqual(world.rays, [])
        self.assertEqual(self.avatar.cell.auto_aim, [(2, False)])
        self.assertEqual(self.avatar._PlayerAvatar__autoAimVehID, 2)
        self.assertFalse(self.avatar.gunRotator.clientMode)

    def test_q_toggles_mode_and_indicator(self):
        panel = BattleHintPanel()
        panel._populate()
        mod._enabled = False
        self.assertNotIn(mod._HINT_ID, panel.hints)
        handler = InputHandlerClass()
        self.assertTrue(InputHandlerClass.handleKeyEvent(handler, KeyEvent(TOGGLE_KEY, True)))
        self.assertTrue(mod._enabled)
        self.assertEqual(panel.hints[mod._HINT_ID].messageRight, mod._TEXT_PRECISE)
        self.assertEqual(panel.hints[mod._HINT_ID].priority, mod._HINT_PRIORITY)
        self.assertEqual(panel.hints[mod._HINT_ID].vKey, '')
        self.assertEqual(panel.hints[mod._HINT_ID].key, '')
        self.assertFalse(InputHandlerClass.handleKeyEvent(handler, KeyEvent(TOGGLE_KEY, False)))
        self.assertTrue(mod._enabled)
        self.assertTrue(InputHandlerClass.handleKeyEvent(handler, KeyEvent(TOGGLE_KEY, True)))
        self.assertFalse(mod._enabled)
        self.assertEqual(panel.hints[mod._HINT_ID].messageRight, mod._TEXT_STANDARD)
        self.assertEqual([(event.key, event.down) for event in handler.events],
                         [(TOGGLE_KEY, False)])

    def test_q_release_never_toggles_mode(self):
        mod._enabled = True
        handler = InputHandlerClass()
        InputHandlerClass.handleKeyEvent(handler, KeyEvent(TOGGLE_KEY, True))
        InputHandlerClass.handleKeyEvent(handler, KeyEvent(TOGGLE_KEY, False))
        self.assertFalse(mod._enabled)
        self.assertEqual(len(handler.events), 1)
        self.assertFalse(handler.events[0].down)

    def test_q_ignored_outside_supported_control_modes(self):
        mod._enabled = False
        self.avatar.inputHandler.ctrlModeName = 'postmortem'
        handler = InputHandlerClass()
        self.assertFalse(InputHandlerClass.handleKeyEvent(handler, KeyEvent(TOGGLE_KEY, True)))
        self.assertFalse(mod._enabled)
        self.assertEqual(len(handler.events), 1)

    def test_q_ignored_for_other_keys_and_repeats(self):
        mod._enabled = False
        handler = InputHandlerClass()
        self.assertFalse(InputHandlerClass.handleKeyEvent(handler, KeyEvent(OTHER_KEY, True)))
        self.assertFalse(InputHandlerClass.handleKeyEvent(
            handler, KeyEvent(TOGGLE_KEY, True, repeated=True)))
        self.assertFalse(mod._enabled)
        self.assertEqual(len(handler.events), 2)

    def test_switching_off_hands_active_lock_to_native(self):
        state = self.lock()
        self.assertEqual(state.target_id, 2)
        mod._set_enabled(False, self.avatar)
        self.assertIsNone(mod._active)
        self.assertEqual(self.avatar.cell.auto_aim, [(2, False)])
        self.assertEqual(self.avatar._PlayerAvatar__autoAimVehID, 2)
        self.assertFalse(self.avatar.gunRotator.clientMode)
        self.assertEqual(self.avatar.sounds, ['locked'])

    def test_switching_on_upgrades_existing_native_lock(self):
        mod._enabled = False
        self.avatar.autoAim(self.enemy)
        self.assertEqual(self.avatar.cell.auto_aim, [(2, False)])
        mod._set_enabled(True, self.avatar)
        self.assertIsNotNone(mod._active)
        self.assertEqual(mod._active.target_id, 2)
        self.assertEqual(self.avatar.cell.auto_aim, [(2, False), (0, False)])
        self.assertTrue(self.avatar.gunRotator.clientMode)

    def test_switching_on_without_reticle_surface_keeps_native_lock(self):
        mod._enabled = False
        world.hit = None
        self.avatar.autoAim(self.enemy)
        mod._set_enabled(True, self.avatar)
        self.assertIsNone(mod._active)
        self.assertEqual(self.avatar._PlayerAvatar__autoAimVehID, 2)

    def test_battle_start_resets_mode_and_indicator(self):
        mod._enabled = True
        panel = BattleHintPanel()
        panel._populate()
        self.assertFalse(mod._enabled)
        self.assertNotIn(mod._HINT_ID, panel.hints)
        panel._dispose()
        mod._set_enabled(True)
        self.assertIsNone(mod._panel_ref)

    def test_avatar_departure_resets_mode(self):
        mod._enabled = False
        InputHandlerClass.handleKeyEvent(InputHandlerClass(), KeyEvent(TOGGLE_KEY, True))
        self.assertTrue(mod._enabled)
        self.avatar.onLeaveWorld()
        self.assertFalse(mod._enabled)
        fire_callbacks()
        self.assertFalse(mod._enabled)

    def test_indicator_disappears_after_delay(self):
        panel = BattleHintPanel()
        panel._populate()
        self.assertNotIn(mod._HINT_ID, panel.hints)
        mod._set_enabled(True, self.avatar)
        self.assertIn(mod._HINT_ID, panel.hints)
        self.assertEqual(len(world.callbacks), 1)
        fire_callbacks()
        self.assertNotIn(mod._HINT_ID, panel.hints)

    def test_mode_change_restarts_indicator_timer(self):
        panel = BattleHintPanel()
        panel._populate()
        self.assertNotIn(mod._HINT_ID, panel.hints)
        mod._set_enabled(True, self.avatar)
        self.assertEqual(panel.hints[mod._HINT_ID].messageRight, mod._TEXT_PRECISE)
        mod._set_enabled(False, self.avatar)
        self.assertEqual(panel.hints[mod._HINT_ID].messageRight, mod._TEXT_STANDARD)
        fire_callbacks()
        self.assertNotIn(mod._HINT_ID, panel.hints)

    def test_fini_restores_key_and_panel_hooks(self):
        recorded = [(owner, name, original) for owner, name, original, _ in mod._hooks
                    if name in ('handleKeyEvent', '_populate', '_dispose')]
        self.assertEqual(len(recorded), 3)
        mod.fini()
        self.assertEqual(mod._hooks, [])
        for owner, name, original in recorded:
            current = getattr(owner, name)
            self.assertIs(getattr(current, 'im_func', current),
                          getattr(original, 'im_func', original))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--package':
        load_packaged(sys.argv[2])
        del sys.argv[1:]
    unittest.main(verbosity=2)

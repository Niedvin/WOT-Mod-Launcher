from __future__ import absolute_import, print_function

import hashlib
import imp
import io
import json
import marshal
import opcode
import os
import py_compile
import tempfile
import types
import zipfile

import test_appropriate_locker as fixture


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ENGINE_BUILTINS = set(['BigWorld', 'Math'])


def collect_imports(code, out):
    raw = code.co_code
    current = None
    idx = 0
    extended = 0
    limit = len(raw)
    while idx < limit:
        op = ord(raw[idx])
        idx += 1
        arg = None
        if op >= opcode.HAVE_ARGUMENT:
            arg = ord(raw[idx]) | (ord(raw[idx + 1]) << 8) | extended
            idx += 2
            extended = (arg << 16) if op == opcode.EXTENDED_ARG else 0
            if op == opcode.EXTENDED_ARG:
                continue
        if op == opcode.opmap['IMPORT_NAME']:
            current = code.co_names[arg]
            out.append((current, None))
        elif op == opcode.opmap['IMPORT_FROM'] and current is not None:
            out.append((current, code.co_names[arg]))
        elif op == opcode.opmap['POP_TOP']:
            current = None
    for item in code.co_consts:
        if isinstance(item, types.CodeType):
            collect_imports(item, out)


def resolve_pkg_entry(entries, dotted):
    rel = dotted.replace('.', '/')
    for prefix in ('scripts/client', 'scripts/common', 'scripts/client_common'):
        for candidate in ('%s/%s.pyc' % (prefix, rel), '%s/%s/__init__.pyc' % (prefix, rel)):
            if candidate in entries:
                return candidate
    return None


def verify_mod_imports(archive, mod_code):
    entries = set(archive.namelist())
    imports = []
    collect_imports(mod_code, imports)
    checked = []
    cache = {}
    for mod_name, attr_name in imports:
        pkg_entry = resolve_pkg_entry(entries, mod_name)
        if pkg_entry is not None:
            if attr_name is not None and attr_name != '*':
                sub_entry = resolve_pkg_entry(entries, mod_name + '.' + attr_name)
                if sub_entry is None:
                    if pkg_entry not in cache:
                        cache[pkg_entry] = marshal.loads(archive.read(pkg_entry)[8:])
                    assert attr_name in cache[pkg_entry].co_names, (
                        'Missing %s.%s in %s' % (mod_name, attr_name, pkg_entry))
            checked.append('%s.%s' % (mod_name, attr_name) if attr_name else mod_name)
        elif mod_name in ENGINE_BUILTINS:
            checked.append(mod_name)
        else:
            top = mod_name.split('.')[0]
            found = imp.find_module(top)
            if found[0] is not None:
                found[0].close()
            if attr_name is not None and attr_name != '*':
                std_mod = __import__(mod_name, fromlist=[attr_name])
                assert hasattr(std_mod, attr_name), 'Missing stdlib %s.%s' % (mod_name, attr_name)
            checked.append('%s.%s' % (mod_name, attr_name) if attr_name else mod_name)
    return sorted(set(checked))


def find_code(code, name):
    for item in code.co_consts:
        if isinstance(item, types.CodeType):
            if item.co_name == name:
                return item
            found = find_code(item, name)
            if found is not None:
                return found
    return None


class CtrlStub(object):

    def __init__(self, offset=None):
        self._aimOffset = offset
        self.lock = False

    def setAimingMode(self, value, mode):
        self.lock = value


def main():
    mod_code = None
    if len(fixture.sys.argv) == 3 and fixture.sys.argv[1] == '--package':
        with zipfile.ZipFile(fixture.sys.argv[2]) as pkg_zip:
            mod_code = marshal.loads(
                pkg_zip.read('res/scripts/client/gui/mods/mod_appropriate_locker.pyc')[8:])
        fixture.load_packaged(fixture.sys.argv[2])
    else:
        src_path = os.path.join(os.path.dirname(__file__), 'mod_appropriate_locker.py')
        fd, tmp_pyc = tempfile.mkstemp(suffix='.pyc')
        os.close(fd)
        try:
            py_compile.compile(src_path, tmp_pyc, src_path, True)
            with open(tmp_pyc, 'rb') as handle:
                mod_code = marshal.loads(handle.read()[8:])
        finally:
            if os.path.exists(tmp_pyc):
                os.remove(tmp_pyc)
    mod = fixture.mod
    mod.fini()
    modules = {}
    evidence = {}
    with zipfile.ZipFile(os.path.join(ROOT, 'res/packages/scripts.pkg')) as archive:
        evidence['verified_imports'] = verify_mod_imports(archive, mod_code)
        for name in ('Avatar', 'VehicleGunRotator'):
            data = archive.read('scripts/client/%s.pyc' % name)
            modules[name] = marshal.loads(data[8:])
            evidence[name + '_pyc_sha256'] = hashlib.sha256(data).hexdigest()
    environment = dict(fixture.__dict__)
    environment.update(
        BigWorld=fixture.world_api, Math=fixture.sys.modules['Math'],
        BattleReplay=fixture.sys.modules['BattleReplay'],
        Vehicle=fixture.sys.modules['Vehicle'],
        VehicleGunRotator=fixture.Rotator, AIMING_MODE=fixture.aiming,
        _CAPS=fixture.caps, AimSound=fixture.sounds, TRIGGER_TYPE=fixture.triggers,
        TriggersManager=fixture.sys.modules['TriggersManager'])
    for name in ('autoAim', 'onAutoAimVehicleLost'):
        code = find_code(modules['Avatar'], name)
        assert code is not None, name
        setattr(fixture.Avatar, name, types.FunctionType(code, environment))
    source_code = find_code(modules['VehicleGunRotator'], '__set_shotPointSourceFunctor')
    mode_code = find_code(modules['VehicleGunRotator'], '__set_clientMode')
    assert source_code is not None and mode_code is not None
    methods = ('__onTick', '__trackPointOnServer', '__updateShotPointOnServer')
    for name in methods:
        code = find_code(modules['VehicleGunRotator'], name)
        assert code is not None, name
        setattr(fixture.Rotator, '_VehicleGunRotator' + name, types.FunctionType(code, environment))
    fixture.Rotator._VehicleGunRotator__getTimeDiff = lambda self: 0.1
    fixture.Rotator._VehicleGunRotator__ROTATION_TICK_LENGTH = 0.1
    ray_offsets = []
    orig_ray = fixture.camera.getWorldRayAndPoint
    fixture.camera.getWorldRayAndPoint = lambda x, y: (
        ray_offsets.append((x, y)) or (fixture.Vector(0, 0, 1), fixture.Vector()))
    runs = []
    try:
        for prediction in (True, False):
            ray_offsets[:] = []
            fixture.world.now = 12.0
            avatar = fixture.Avatar()
            arcade_ctrl = CtrlStub(offset=fixture.Struct(x=0.125, y=-0.25))
            dualgun_ctrl = CtrlStub()
            dualgun_ctrl.lock = True
            strategic_ctrl = CtrlStub()
            strategic_ctrl.lock = True
            avatar.inputHandler.ctrl = arcade_ctrl
            avatar.inputHandler._AvatarInputHandler__ctrls = {
                'arcade': arcade_ctrl, 'dualgun': dualgun_ctrl, 'strategic': strategic_ctrl}
            own = fixture.Vehicle(1, 1)
            own.position = fixture.Vector(3, 0, 4)
            target = fixture.Vehicle(2, 2)
            other = fixture.Vehicle(4, 2)
            fixture.world.player = avatar
            fixture.world.entities.clear()
            fixture.world.entities.update({1: own, 2: target, 4: other})
            fixture.replay.isPlaying = False
            target.appearance.collisions.maxStaticPartIndex = 3
            target.appearance.collisions.parents = {5: 2}
            target.appearance.collisions.transforms[2] = fixture.Matrix(
                translation=fixture.Vector(10, 0, 30))
            fixture.world.hit = (fixture.Vector(11, 2, 30), True, 2, 5, 0)
            rotator = avatar.gunRotator
            rotator.USE_LOCK_PREDICTION = prediction
            fixture.Rotator.USE_LOCK_PREDICTION = prediction
            rotator._VehicleGunRotator__fixedShotAngles = None
            rotator._VehicleGunRotator__targetLastShotPoint = False
            rotator._VehicleGunRotator__lastShotPoint = fixture.Vector()
            rotator._VehicleGunRotator__prevSentShotPoint = None
            previous = fixture.Vehicle(3, 2)
            fixture.world.entities[3] = previous
            mod.init()
            avatar.autoAim(previous, True)
            assert avatar.cell.auto_aim == [(3, True)]
            del fixture.world.entities[3]
            avatar.cell.auto_aim[:] = []
            avatar.sounds[:] = []
            avatar.autoAim(target)
            assert mod._active is None
            assert avatar.cell.auto_aim == [(2, False)]
            avatar.cell.auto_aim[:] = []
            avatar.sounds[:] = []
            avatar.autoAim(other)
            assert avatar._PlayerAvatar__autoAimVehID == 4
            avatar.cell.auto_aim[:] = []
            avatar.sounds[:] = []
            mod._enabled = True
            avatar.autoAim(target)
            assert mod._active is not None
            assert mod._active.part_index == 2
            assert ray_offsets[-1] == (0.125, -0.25)
            assert avatar.cell.auto_aim == [(0, False)]
            assert avatar.sounds == ['locked']
            avatar.autoAim(other, True)
            assert mod._active is not None and mod._active.target_id == 2
            fixture.world.hit = None
            avatar.autoAim(other, False)
            assert mod._active is not None and mod._active.target_id == 2
            target.appearance.collisions.transforms[2] = fixture.Matrix(
                translation=fixture.Vector(20, 0, 50),
                rotation=((0, 0, 1), (0, 1, 0), (-1, 0, 0)))
            rotator._VehicleGunRotator__onTick()
            assert own.cell.relative_points[-1].values() == (17.0, 2.0, 45.0)
            assert rotator.rotated_points[-1].values() == (20.0, 2.0, 49.0)
            for step in range(1, 16):
                fixture.world.now = 12.0 + step * 0.1
                shift = step * 0.2
                target.appearance.collisions.transforms[2] = fixture.Matrix(
                    translation=fixture.Vector(20.0 + shift, 0, 50),
                    rotation=((0, 0, 1), (0, 1, 0), (-1, 0, 0)))
                rotator._VehicleGunRotator__onTick()
                expected_base = fixture.Vector(20.0 + shift, 2.0, 49.0)
                err = (rotator.rotated_points[-1] - expected_base).length
                assert 0.0 < err <= 0.070001
            settled_base = fixture.Vector(23.0, 2.0, 49.0)
            sent_before_idle = len(own.cell.relative_points)
            for step in range(1, 36):
                fixture.world.now = 13.5 + step * 0.1
                rotator._VehicleGunRotator__onTick()
                if step >= 6:
                    idle_err = (rotator.rotated_points[-1] - settled_base).length
                    assert idle_err <= 0.014001
            sent_during_idle = len(own.cell.relative_points) - sent_before_idle
            assert sent_during_idle < 35
            assert not any(target_id for target_id, magnetic in avatar.cell.auto_aim)
            tracked = mod._active
            avatar.vehicle_onLeaveWorld(target)
            assert mod._active is None
            assert tracked.collisions is None and tracked.rotator is None
            assert avatar.autoAimVehicle is None
            assert not avatar.inputHandler.lock
            assert not dualgun_ctrl.lock
            assert not strategic_ctrl.lock
            assert avatar.sounds == ['locked', 'lost']
            rotator._VehicleGunRotator__onTick()
            assert rotator.rotated_points[-1].values() == (91.0, 92.0, 93.0)
            runs.append({'prediction': prediction, 'relative_tracking_point': (17, 2, 45),
                          'world_aim_point': (20, 2, 49), 'nonzero_server_autoaim_calls': 0,
                          'aim_offset_forwarded': True, 'dynamic_part_resolved_to_parent': True,
                          'out_of_aoi_native_lock_cleared': True, 'inactive_ctrl_lock_cleared': True,
                          'magnetic_delegated_when_unlocked': True,
                          'disabled_mode_delegates_to_native': True,
                          'sway_and_idle_dedup_verified': True,
                          'manual_aim_restored': True})
            mod.fini()
    finally:
        fixture.camera.getWorldRayAndPoint = orig_ray
    evidence['native_methods_executed'] = list(methods) + ['autoAim']
    evidence['native_property_setters_present'] = [source_code.co_name, mode_code.co_name]
    evidence['runs'] = runs
    evidence['live_game_verified'] = False
    path = os.path.join(os.path.dirname(__file__), 'native-validation.json')
    text = json.dumps(evidence, indent=2, sort_keys=True, separators=(',', ': ')) + '\n'
    with io.open(path, 'w', encoding='utf-8') as output:
        output.write(text.decode('utf-8') if isinstance(text, bytes) else text)
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()

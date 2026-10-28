# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
import json
from collections import OrderedDict
import math
import os
import weakref

try:
    import BigWorld
except ImportError:
    BigWorld = None

try:
    import Math
    _FORWARD_VEC = Math.Vector3(0.0, 0.0, 1.0)
except ImportError:
    Math = None
    _FORWARD_VEC = None

try:
    from gui.battle_control.battle_constants import CROSSHAIR_VIEW_ID
except Exception:
    class CROSSHAIR_VIEW_ID(object):
        UNDEFINED = 0
        ARCADE = 1
        SNIPER = 2
        STRATEGIC = 3
        POSTMORTEM = 4


_BASE_DEVICES = ('engine', 'ammoBay', 'fuelTank', 'radio', 'gun', 'turretRotator', 'surveyingDevice')
_TRACKS = ('leftTrack0', 'rightTrack0')
_CREW = ('commander', 'driver', 'radioman', 'gunner', 'loader')



def calculate_ray_endpoint(pos, direction, distance=1000.0):
    return tuple(pos[index] + direction[index] * distance for index in range(3))


def calculate_dispersion_radius(dispersion_angle, distance):
    return max(0.0, float(distance) * float(dispersion_angle))


def _get_vehicle_entity(veh_id):
    if BigWorld is None or veh_id is None:
        return None
    if hasattr(BigWorld, 'entity'):
        try:
            ent = BigWorld.entity(veh_id)
            if ent is not None:
                return ent
        except Exception:
            pass
    entities = getattr(BigWorld, 'entities', None)
    if entities is not None:
        if hasattr(entities, 'get'):
            try:
                ent = entities.get(veh_id)
                if ent is not None:
                    return ent
            except Exception:
                pass
        try:
            return entities[veh_id]
        except Exception:
            pass
    return None


class TeammateTracker(object):
    def __init__(self):
        self._reloads = {}
        self._unavailable_reloads = {}
        self._equipments = {}
        self._equipment_snapshots = {}
        self._devices = {}
        self._gun_markers = {}
        self._shell_hints = {}

    def record_reload(self, vehicle_id, current_time, remaining, base, clip_time=None):
        remaining = float(remaining)
        base = float(base)
        if math.isnan(remaining) or math.isinf(remaining):
            return
        if remaining < 0.0:
            self._reloads.pop(vehicle_id, None)
            self._unavailable_reloads[vehicle_id] = float(current_time)
            return
        self._unavailable_reloads.pop(vehicle_id, None)
        if math.isnan(base) or math.isinf(base):
            base = remaining
        self._reloads[vehicle_id] = (float(current_time), float(current_time) + remaining, max(base, remaining), clip_time, True)

    def record_shot(self, vehicle_id, current_time, base_reload, clip_time=None):
        base_reload = float(base_reload)
        if base_reload <= 0.0 or math.isnan(base_reload) or math.isinf(base_reload):
            return
        unavailable = self._unavailable_reloads.get(vehicle_id)
        if unavailable is not None and current_time - unavailable < 0.5:
            return
        previous = self._reloads.get(vehicle_id)
        if previous and previous[4] and previous[1] > current_time and current_time - previous[0] < 0.5:
            return
        self._unavailable_reloads.pop(vehicle_id, None)
        self._reloads[vehicle_id] = (float(current_time), float(current_time) + base_reload, float(base_reload), clip_time, False)

    def record_equipment_used(self, vehicle_id, item_cd, current_time, cooldown):
        self._equipments.setdefault(vehicle_id, {})[item_cd] = (float(current_time), float(cooldown))

    def record_equipment(self, vehicle_id, item_cd, quantity, stage, remaining, total, index, current_time):
        records = self._equipment_snapshots.setdefault(vehicle_id, OrderedDict())
        index = index or 0
        if index <= 0 and item_cd:
            matches = [key[0] for key in records if key[1] == item_cd and key[0] > 0]
            if len(matches) == 1:
                index = matches[0]
        if index > 0:
            for key in list(records):
                if key[0] == index and key[1] != item_cd or key == (0, item_cd):
                    del records[key]
                    if not any(candidate[1] == key[1] for candidate in records):
                        self._equipments.get(vehicle_id, {}).pop(key[1], None)
        records[(index, item_cd)] = (quantity, stage, max(0.0, remaining), max(0.0, total), float(current_time))
        if item_cd:
            self.record_equipment_used(vehicle_id, item_cd, current_time, max(0.0, remaining))

    def replace_equipment(self, vehicle_id, old_item_cd, new_item_cd, quantity, stage, remaining, total, index, current_time):
        records = self._equipment_snapshots.get(vehicle_id, {})
        if not index:
            matches = [key[0] for key in records if key[1] == old_item_cd and key[0] > 0]
            if len(matches) == 1:
                index = matches[0]
        for key in list(records):
            if key[1] == old_item_cd and (not index or key[0] in (0, index)):
                del records[key]
        if not any(key[1] == old_item_cd for key in records):
            self._equipments.get(vehicle_id, {}).pop(old_item_cd, None)
        self.record_equipment(vehicle_id, new_item_cd, quantity, stage, remaining, total, index, current_time)

    def get_equipment_snapshot(self, vehicle_id, current_time):
        result = []
        records = self._equipment_snapshots.get(vehicle_id, OrderedDict()).items()
        for (index, item_cd), (quantity, stage, remaining, total, received) in sorted(records, key=lambda pair: pair[0][0]):
            result.append((index, item_cd, quantity, stage, max(0.0, remaining - max(0.0, current_time - received)), total))
        return result

    def record_device_state(self, vehicle_id, device_name, state):
        self._devices.setdefault(vehicle_id, {})[device_name] = state

    def record_gun_marker(self, vehicle_id, current_time, shot_pos, shot_vec, dispersion_angle):
        self._gun_markers[vehicle_id] = (float(current_time),
                                         tuple(float(shot_pos[index]) for index in range(3)),
                                         tuple(float(shot_vec[index]) for index in range(3)),
                                         float(dispersion_angle))

    def get_server_gun_marker(self, vehicle_id, current_time, max_age=0.3):
        record = self._gun_markers.get(vehicle_id)
        if record is None:
            return None
        age = float(current_time) - record[0]
        if age < 0.0 or age > max_age:
            return None
        return record[1], record[2], record[3]

    def record_shell_hint(self, vehicle_id, shell_cd, current_time):
        if shell_cd:
            self._shell_hints[vehicle_id] = (shell_cd, float(current_time))

    def get_shell_hint(self, vehicle_id):
        record = self._shell_hints.get(vehicle_id)
        return record[0] if record is not None else None

    def get_actual_reload(self, vehicle_id, current_time):
        record = self._reloads.get(vehicle_id)
        if not record:
            return (0.0, 0.0, False, None)
        received, end, base, clip_time, authoritative = record
        remaining = max(0.0, end - received - max(0.0, current_time - received))
        return (remaining, base, remaining > 0.0, clip_time)

    def has_reload(self, vehicle_id):
        return vehicle_id in self._reloads

    def is_reload_estimated(self, vehicle_id):
        record = self._reloads.get(vehicle_id)
        return bool(record and not record[4])

    def get_equipment_cooldown(self, vehicle_id, item_cd, current_time):
        record = self._equipments.get(vehicle_id, {}).get(item_cd)
        return max(0.0, record[1] - max(0.0, current_time - record[0])) if record else 0.0

    def get_devices(self, vehicle_id):
        return dict(self._devices.get(vehicle_id, {}))

    def clear(self):
        self._reloads.clear()
        self._unavailable_reloads.clear()
        self._equipments.clear()
        self._equipment_snapshots.clear()
        self._devices.clear()
        self._gun_markers.clear()
        self._shell_hints.clear()


class NativeCrosshairMarkerAdapter(object):
    def __init__(self):
        self._controller = None
        self._binding = None
        self._flags = 0

    def _ensure_controller(self):
        if self._controller is not None:
            return
        from AvatarInputHandler import aih_global_binding, gun_marker_ctrl
        from aih_constants import GUN_MARKER_FLAG
        class Bindings(object):
            flags = aih_global_binding.bindRW(aih_global_binding.BINDING_ID.GUN_MARKERS_FLAGS)
        self._binding = Bindings()
        self._flags = self._binding.flags
        controller = gun_marker_ctrl.createGunMarker(False)
        self._controller = controller
        controller.create()
        controller.enable()
        self._binding.flags = (self._flags | GUN_MARKER_FLAG.CONTROL_ENABLED | GUN_MARKER_FLAG.CLIENT_MODE_ENABLED) & ~GUN_MARKER_FLAG.SERVER_MODE_ENABLED

    def update_ballistic_marker(self, hit_point, radius, direction, collision, relax_time=0.0):
        self._ensure_controller()
        from VehicleGunRotator import GunMarkerInfo
        from aih_constants import GUN_MARKER_TYPE
        info = GunMarkerInfo(0, getattr(_aim_manager, '_gun_index', None), Math.Vector3(*hit_point), Math.Vector3(direction), 2.0 * radius, 0.0, 0.0, collision)
        self._controller.update(GUN_MARKER_TYPE.CLIENT, info, (), relax_time)

    def clear(self):
        if self._controller is not None:
            try:
                self._controller.disable()
                self._controller.destroy()
            finally:
                self._controller = None
                self._binding.flags = self._flags
                self._binding = None


class SpectatorAimManager(object):
    def __init__(self, marker_controller=None, bigworld=None):
        self._marker_controller = marker_controller
        self._bigworld = bigworld
        self._current_vehicle_id = None
        self._is_active = False
        self._direction = None
        self._collision = None
        self._gun_index = None

    def activate(self, vehicle_id):
        if self._is_active and vehicle_id != self._current_vehicle_id:
            self._clear_marker()
        self._current_vehicle_id = vehicle_id
        self._is_active = True

    def deactivate(self):
        self._current_vehicle_id = None
        self._is_active = False

    enable = activate
    disable = deactivate

    def is_active(self):
        return self._is_active

    def set_marker_controller(self, controller):
        self._marker_controller = controller

    def _clear_marker(self):
        self._direction = self._collision = None
        self._gun_index = None
        if self._marker_controller is not None and hasattr(self._marker_controller, 'clear'):
            self._marker_controller.clear()

    def _get_vehicle_matrix(self, vehicle):
        vehicle_filter = getattr(vehicle, 'filter', None)
        bw = self._bigworld or BigWorld
        player = bw.player() if bw is not None else None
        if player is not None and getattr(player, 'isObserver', lambda: False)():
            attached = getattr(player, 'getVehicleAttached', lambda: None)()
            if attached is not None and attached.id == vehicle.id:
                getter = getattr(player, 'getObservedVehicleStabilisedMatrix', None)
                matrix = getter() if getter is not None else getattr(vehicle_filter, 'stabilisedMatrix', None)
                if matrix is not None:
                    return matrix
        matrix = getattr(vehicle_filter, 'bodyMatrix', None)
        return matrix if matrix is not None else vehicle.matrix

    def _get_shot_params(self, vehicle, shot):
        if getattr(vehicle, 'appearance', None) is None or not hasattr(vehicle, 'getAimParams'):
            return None
        descr = vehicle.typeDescriptor
        gun_offset = descr.activeGunShotPosition
        multi_gun = descr.gun.multiGun
        self._gun_index = None
        active_guns = ()
        if getattr(descr, 'isDualgunVehicle', False):
            active_guns = (vehicle.dualGunIndex,)
        elif multi_gun:
            from items.vehicle_mechanics_types import VehicleMechanicKeys
            twin_gun = vehicle.getVehicleMechanicComponent(VehicleMechanicKeys.TWIN_GUN)
            if twin_gun is not None:
                active_guns = twin_gun.getActiveGunIndexes()
        if multi_gun and len(active_guns) == 1:
            gun_index = active_guns[0]
            if gun_index < 0 or gun_index >= len(multi_gun):
                return None
            gun_offset = multi_gun[gun_index].shotPosition
            self._gun_index = gun_index
        turret_yaw, gun_pitch = vehicle.getAimParams()
        body_matrix = self._get_vehicle_matrix(vehicle)
        turret_matrix = Math.Matrix()
        turret_matrix.setRotateY(turret_yaw)
        turret_matrix.translation = descr.hull.turretPositions[0] + descr.chassis.hullPosition
        turret_matrix.postMultiply(Math.Matrix(body_matrix))
        position = turret_matrix.applyPoint(gun_offset)
        gun_matrix = Math.Matrix()
        gun_matrix.setRotateX(gun_pitch)
        gun_matrix.postMultiply(turret_matrix)
        velocity = gun_matrix.applyVector(Math.Vector3(0.0, 0.0, shot.speed))
        return position, velocity

    def _get_shot_descriptor(self, vehicle, shell_hint=None):
        descr = getattr(vehicle, 'typeDescriptor', None)
        shell_cd = getattr(getattr(vehicle, 'ownVehicle', None), 'currentShell', -1)
        if (shell_cd is None or shell_cd < 0) and shell_hint is not None:
            shell_cd = shell_hint
        if shell_cd is not None and shell_cd >= 0:
            for shot in getattr(getattr(descr, 'gun', None), 'shots', ()):
                if shot.shell.compactDescr == shell_cd:
                    return shot
            return None
        return getattr(descr, 'shot', None)

    def get_gun_marker_data(self, vehicle, raycast_distance=1000.0, server_marker=None, shell_hint=None):
        if vehicle is None or not getattr(vehicle, 'inWorld', False) or Math is None:
            return None
        descr = getattr(vehicle, 'typeDescriptor', None)
        if descr is None:
            return None
        from AvatarInputHandler import AimingSystems
        bw = self._bigworld or BigWorld
        player = bw.player()
        if player is None:
            return None
        shot = self._get_shot_descriptor(vehicle, shell_hint)
        if shot is None:
            shot = getattr(descr, 'shot', None)
        if shot is None or shot.speed <= 0.0:
            return None
        if server_marker is not None:
            position = Math.Vector3(*server_marker[0])
            velocity = Math.Vector3(*server_marker[1])
            angle = server_marker[2] if server_marker[2] > 0.0 else descr.gun.shotDispersionAngle
        else:
            transform = self._get_shot_params(vehicle, shot)
            if transform is None:
                return None
            position, velocity = transform
            angle = descr.gun.shotDispersionAngle
            observed = getattr(player, 'observedVehicleData', {}).get(vehicle.id)
            if observed is not None and getattr(observed, 'dispAngle', 0.0) > 0.0:
                angle = observed.dispAngle
        min_bounds, max_bounds = player.arena.getSpaceBB()
        end, self._direction, self._collision, used_max = AimingSystems.getCappedShotTargetInfos(position, velocity, Math.Vector3(0.0, -shot.gravity, 0.0), shot, vehicle.id, min_bounds, max_bounds, AimingSystems.CollisionStrategy.COLLIDE_DYNAMIC_AND_STATIC)
        distance = shot.maxDistance if used_max else math.sqrt(sum((end[index] - position[index]) ** 2 for index in range(3)))
        return tuple(float(value) for value in end), calculate_dispersion_radius(angle, distance)

    def get_dispersion_size(self, vehicle, target_point):
        data = self.get_gun_marker_data(vehicle)
        return data[1] if data else 0.0

    def update_aim(self, vehicle=None, raycast_distance=1000.0, server_marker=None, shell_hint=None, relax_time=0.0):
        if not self._is_active:
            return None
        if vehicle is None or getattr(vehicle, 'id', None) != self._current_vehicle_id:
            self._clear_marker()
            return None
        data = self.get_gun_marker_data(vehicle, raycast_distance, server_marker, shell_hint)
        if data is None:
            self._clear_marker()
            return None
        if self._marker_controller is not None:
            if hasattr(self._marker_controller, 'update_ballistic_marker'):
                self._marker_controller.update_ballistic_marker(data[0], data[1], self._direction, self._collision, relax_time)
            else:
                self._marker_controller.update_marker(*data)
        return data


class SpectatorHudAdapter(object):
    def __init__(self):
        self._damage_key = None
        self._device_states = {}
        self._equipment_key = None
        self._equipment_items = {}
        self._equipment_signature = None
        self._consumables_layout = None

    def _restore_consumables_layout(self):
        layout = self._consumables_layout
        self._consumables_layout = None
        if layout is not None:
            panel, clip, damage, native_size = layout
            if getattr(panel, 'flashObject', None) is clip:
                clip.updateStage(*self._native_stage_size(clip, damage, native_size))

    @staticmethod
    def _native_stage_size(clip, damage, fallback=None):
        try:
            height = float(damage.y) + float(damage.initedHeight)
            stage = clip.stage
            return height * float(stage.stageWidth) / float(stage.stageHeight), height
        except Exception:
            if fallback is not None:
                return fallback
            raise

    def shift_consumables_left(self, panel, damage_panel):
        clip = getattr(panel, 'flashObject', None)
        damage = getattr(damage_panel, 'flashObject', None)
        if clip is None or damage is None:
            return
        layout = self._consumables_layout
        if layout is not None and layout[1] is not clip:
            self._restore_consumables_layout()
        rectangles = []
        for index in range(15):
            renderer = clip.getRendererBySlotIdx(index)
            if renderer is not None and renderer.visible:
                anchor = getattr(renderer, 'hit', None) or getattr(renderer, 'iconLoader', None)
                if anchor is None:
                    continue
                # Hidden glow clips inflate renderer bounds beyond visible buttons. — 2026-10-28
                bounds = anchor.getBounds(clip)
                if float(bounds.width) > 0 and float(bounds.height) > 0:
                    rectangles.append(bounds)
        if not rectangles:
            return
        native_size = self._native_stage_size(clip, damage)
        left = min(float(bounds.x) for bounds in rectangles)
        bottom = max(float(bounds.y) + float(bounds.height) for bounds in rectangles)
        # DamagePanel reserves 230 px independently of animated child bounds in WoT 2.4.1.0 — 2026-10-27
        target_x = float(damage.x) + 230.0 + 12.0 - left
        target_y = native_size[1] - 4.0 - bottom
        # ConsumablesPanel.updatePosition recalculates x and y from stored stage size on every redraw — 2026-10-27
        clip.updateStage(2.0 * target_x + float(clip.basePanelWidth), target_y + 58.0)
        clip.x = target_x
        clip.y = target_y
        self._consumables_layout = (panel, clip, damage, native_size)

    def reset(self):
        self._restore_consumables_layout()
        for item in self._equipment_items.values():
            if hasattr(item, 'clear'):
                item.clear()
        self._damage_key = self._equipment_key = None
        self._device_states.clear()
        self._equipment_items.clear()
        self._equipment_signature = None

    def bind_damage_panel(self, panel, health, max_health=None, device_states=None, vehicle=None):
        if panel is None:
            return
        key = (id(panel), getattr(vehicle, 'id', None))
        max_hp = max_health if max_health and max_health > 0 else max(health, 1)
        progress = max(0, min(100, int(float(health) / max_hp * 100.0)))
        roles = list(_CREW)
        if vehicle is not None:
            from gui.battle_control import vehicle_getter
            roles = vehicle_getter.getCrewMainRolesWithIndexes(vehicle.typeDescriptor.type.crewRoles)
        if self._damage_key != key:
            if hasattr(panel, 'as_resetS'):
                panel.as_resetS()
            if hasattr(panel, 'hideStatusImmediate'):
                panel.hideStatusImmediate()
            if vehicle is not None and hasattr(panel, 'as_setupS'):
                import math
                descriptor = vehicle.typeDescriptor
                yaw_limits = vehicle_getter.getYawLimits(descriptor)
                yaw_degrees = (math.degrees(-yaw_limits[0]), math.degrees(yaw_limits[1])) if yaw_limits else None
                panel.as_setupS('%d / %d' % (max(0, health), max_hp), progress,
                                vehicle_getter.getVehicleIndicatorType(descriptor), roles, yaw_degrees,
                                vehicle_getter.hasTurretRotator(descriptor), vehicle.isWheeledTech,
                                True, vehicle.isTrackWithinTrack, vehicle.isAlive())
                if vehicle.isWheeledTech:
                    panel.as_setupWheeledS(descriptor.chassis.generalWheelsAnimatorConfig.getNonTrackWheelsCount())
                if hasattr(panel, '_updatePlayerInfo'):
                    panel._updatePlayerInfo(vehicle.id)
                indicator = getattr(panel, '_DamagePanel__tankIndicator', None)
                if indicator is not None:
                    indicator.setup(vehicle, yaw_limits)
            self._damage_key = key
            self._device_states = {}
        if hasattr(panel, 'as_updateHealthS'):
            panel.as_updateHealthS('%d / %d' % (max(0, health), max_hp), progress)
        devices = list(_BASE_DEVICES)
        if vehicle is not None and getattr(vehicle, 'isWheeledTech', False):
            config = vehicle.typeDescriptor.chassis.generalWheelsAnimatorConfig
            devices.extend('wheel%d' % index for index in range(config.getNonTrackWheelsCount()))
        else:
            devices.extend(_TRACKS)
            if vehicle is not None and getattr(vehicle, 'isTrackWithinTrack', False):
                devices.extend(('leftTrack1', 'rightTrack1'))
        valid = set(devices) | set(roles)
        for name, state in (device_states or {}).items():
            if name in valid and state in ('normal', 'critical', 'destroyed', 'repaired') and self._device_states.get(name) != state:
                panel.as_updateDeviceStateS(name, state)
                self._device_states[name] = state

    def bind_consumables_cooldowns(self, panel, vehicle_id, tracker, current_time, equipment_cds=None):
        if panel is None or tracker is None:
            return
        key = (id(panel), vehicle_id)
        snapshots = tracker.get_equipment_snapshot(vehicle_id, current_time)
        signature = tuple((row[0], row[1]) for row in snapshots)
        if key != self._equipment_key or signature != self._equipment_signature:
            for item in self._equipment_items.values():
                if hasattr(item, 'clear'):
                    item.clear()
            self._equipment_items.clear()
            self._equipment_key = key
            self._equipment_signature = signature
            if hasattr(panel, '_resetEquipments'):
                panel._resetEquipments()
            else:
                panel._reset()
        if not snapshots:
            return
        import constants
        from items import vehicles
        try:
            from gui.battle_control.controllers.consumables.equipment_ctrl import EquipmentsReplayPlayer as item_factory
        except ImportError:
            from gui.battle_control.controllers.consumables.equipment_ctrl import EquipmentsController as item_factory
        active_stage = getattr(getattr(constants, 'EQUIPMENT_STAGES', None), 'ACTIVE', None)
        empty_slots = 0
        for index, item_cd, quantity, stage, remaining, total in snapshots:
            item_key = (index, item_cd)
            if not item_cd:
                empty_slots += 1
                if panel._cds.count(0) < empty_slots:
                    panel._onEquipmentAdded(0, None)
                continue
            item = self._equipment_items.get(item_key)
            if item is None:
                descriptor = vehicles.getItemByCompactDescr(item_cd)
                if descriptor is None:
                    continue
                item = item_factory.createItem(descriptor, quantity, stage, remaining, total)
                if item is None:
                    continue
                self._equipment_items[item_key] = item
            else:
                item.update(quantity, stage, remaining, total)
            if item_cd not in panel._cds:
                panel._onEquipmentAdded(item_cd, item)
            else:
                panel._onEquipmentUpdated(item_cd, item)
            if item_cd in panel._cds:
                panel._onEquipmentCooldownTime(item_cd, remaining, stage == active_stage, False)
                if hasattr(panel, '_onEquipmentCooldownInPercent'):
                    percent = max(0.0, min(100.0, 100.0 * (total - remaining) / total)) if total > 0 else 100.0
                    panel._onEquipmentCooldownInPercent(item_cd, percent)

    bind_consumables_panel = bind_consumables_cooldowns

    def prevent_consumables_hide(self, page):
        if page is not None and hasattr(page, '_setComponentsVisibility'):
            page._setComponentsVisibility(visible={'consumablesPanel', 'damagePanel'}, hidden=set())




class SpectatorReloadDisplay(object):
    def __init__(self):
        self._text = None

    def update(self, vehicle_id, tracker, current_time, show_reload=True, show_equipment_unknown=False, show_shell_unknown=False):
        text = []
        if show_reload:
            if not tracker.has_reload(vehicle_id):
                text.append(u'Перезарядка: немає даних')
            else:
                remaining = tracker.get_actual_reload(vehicle_id, current_time)[0]
                estimated = tracker.is_reload_estimated(vehicle_id)
                if remaining > 0.0:
                    text.append(u'Перезарядка: %s%.1f с' % (u'≈' if estimated else u'', remaining))
                else:
                    text.append(u'Перезарядка: немає даних' if estimated else u'Перезарядку завершено')
        if show_equipment_unknown:
            text.append(u'Спорядження: немає даних')
        if show_shell_unknown:
            text.append(u'Снаряд: немає даних')
        if not text:
            self.clear()
            return
        import GUI
        if self._text is None:
            component = GUI.Text(u'')
            component.font = 'system_medium.font'
            component.horizontalAnchor = GUI.Simple.eHAnchor.CENTER
            component.verticalAnchor = GUI.Simple.eVAnchor.TOP
            component.position = (0.0, -0.12, 0.5)
            component.colour = (255, 255, 255, 255)
            component.multiline = True
            GUI.addRoot(component)
            self._text = component
        self._text.text = u'\n'.join(text)

    def clear(self):
        if self._text is not None:
            import GUI
            GUI.delRoot(self._text)
            self._text = None


_logged_errors = set()


def _report_error(component):
    if component not in _logged_errors:
        _logged_errors.add(component)
        try:
            from debug_utils import LOG_ERROR, LOG_CURRENT_EXCEPTION
            LOG_ERROR('[SpectatorHUD] %s' % component)
            LOG_CURRENT_EXCEPTION()
        except ImportError:
            pass


def _run_hud_step(name, action):
    try:
        return action()
    except Exception:
        _report_error(name)


def _refresh_crosshair_view(player):
    shared = getattr(getattr(player, 'guiSessionProvider', None), 'shared', None)
    crosshair = getattr(shared, 'crosshair', None)
    if crosshair is None:
        return
    mode = getattr(getattr(player, 'inputHandler', None), 'ctrlModeName', 'postmortem')
    handler = getattr(crosshair, '_CrosshairDataProxy__onAvatarControlModeChanged', None)
    if handler is not None:
        handler(mode)
    elif not getattr(player, 'isVehicleAlive', False) and hasattr(crosshair, 'onCrosshairViewChanged'):
        crosshair.onCrosshairViewChanged(CROSSHAIR_VIEW_ID.ARCADE if _aim_manager.is_active() and _CONFIG.get('show_teammate_reticle', True) else CROSSHAIR_VIEW_ID.POSTMORTEM)


_DEFAULT_CONFIG = {
    'enabled': True,
    'show_teammate_reticle': True,
    'show_actual_reload': True,
    'show_module_damage': True,
    'show_consumables_cooldown': True,
    'raycast_distance': 1000.0,
    'update_rate_fps': 0
}

_CONFIG = dict(_DEFAULT_CONFIG)
_CONFIG_DIR = os.path.join('mods', 'configs', 'spectator_teammate_hud')
_CONFIG_PATH = os.path.join(_CONFIG_DIR, 'config.json')

_reload_display = SpectatorReloadDisplay()
_orig_updateVehicleAmmo = None
_orig_resetVehicleAmmo = None
_orig_damage_panel_controlling = None
_tracker = TeammateTracker()
_crosshair_adapter = NativeCrosshairMarkerAdapter()
_aim_manager = SpectatorAimManager(marker_controller=_crosshair_adapter)
_hud_adapter = SpectatorHudAdapter()
_aim_callback_id = None
_active_battle_page = None
_last_hud_update_time = 0.0
_ammo_plugin = None
_ammo_render_key = None
_plugin_hooks = []
_crew_buff_status_id = None


def _controlled_vehicle_id(player, fallback=None):
    shared = getattr(getattr(player, 'guiSessionProvider', None), 'shared', None)
    state = getattr(shared, 'vehicleState', None)
    if state is not None and hasattr(state, 'getControllingVehicleID'):
        return state.getControllingVehicleID()
    return fallback


def _spectator_shot(vehicle, require_known=False):
    descriptor = getattr(vehicle, 'typeDescriptor', None)
    if descriptor is None:
        return None
    shots = getattr(descriptor.gun, 'shots', ())
    current = getattr(getattr(vehicle, 'ownVehicle', None), 'currentShell', -1)
    if current is None or current < 0:
        if _aim_manager.is_active() and _aim_manager._current_vehicle_id == vehicle.id:
            current = _tracker.get_shell_hint(vehicle.id)
    for shot in shots:
        if getattr(shot.shell, 'compactDescr', None) == current:
            return shot
    if current is not None and current >= 0:
        return None
    if require_known and len(shots) > 1:
        return None
    return shots[0] if len(shots) == 1 else descriptor.shot


def _spectator_shot_result(marker, exclude_team, multiplier):
    from AvatarInputHandler import gun_marker_ctrl
    from aih_constants import SHOT_RESULT
    from constants import SHELL_TYPES, SHELL_MECHANICS_TYPE
    collision = marker.collData
    vehicle = _get_vehicle_entity(_aim_manager._current_vehicle_id)
    if collision is None or vehicle is None:
        return SHOT_RESULT.UNDEFINED
    entity = collision.entity
    if getattr(entity, 'health', 0) <= 0 or entity.publicInfo['team'] == exclude_team:
        return SHOT_RESULT.UNDEFINED
    shot = _spectator_shot(vehicle, require_known=True)
    if shot is None:
        return SHOT_RESULT.UNDEFINED
    resolver = gun_marker_ctrl._CrosshairShotResults
    details = resolver._getAllCollisionDetails(marker.position, marker.direction, entity)
    if details is None:
        return SHOT_RESULT.UNDEFINED
    distance = (marker.position - Math.Vector3(vehicle.position)).length
    power = gun_marker_ctrl.computePiercingPowerAtDist(shot.piercingPower, distance, shot.maxDistance, multiplier)
    shell = shot.shell
    low, high = resolver._computePiercingPowerRandomization(shell)
    if shell.kind == SHELL_TYPES.HIGH_EXPLOSIVE and shell.type.mechanics == SHELL_MECHANICS_TYPE.MODERN:
        calculate = resolver._CrosshairShotResults__shotResultModernHE
    else:
        calculate = resolver._CrosshairShotResults__shotResultDefault
    return calculate(marker, details, power, shell, low, high, entity)


def _render_spectator_reload(plugin):
    parent = plugin._parentObj
    vehicle_id = _aim_manager._current_vehicle_id
    now = BigWorld.serverTime()
    remaining, base, reloading, clip = _tracker.get_actual_reload(vehicle_id, now)
    known = _tracker.has_reload(vehicle_id) and not _tracker.is_reload_estimated(vehicle_id) and _CONFIG.get('show_actual_reload', True)
    if not known:
        remaining, base, reloading = -1.0, 0.0, False
    parent.as_setReloadingS(remaining, base, 0.0, reloading, False)


def _render_spectator_ammo(plugin):
    global _ammo_render_key
    vehicle = _get_vehicle_entity(_aim_manager._current_vehicle_id)
    parent = plugin._parentObj
    descriptor = getattr(vehicle, 'typeDescriptor', None)
    key = (id(plugin), getattr(vehicle, 'id', None), id(descriptor), id(getattr(descriptor, 'gun', None)))
    if key != _ammo_render_key:
        callback = getattr(plugin, '_AmmoPlugin__autoReloadCallbackID', None)
        if callback is not None:
            BigWorld.cancelCallback(callback)
            plugin._AmmoPlugin__autoReloadCallbackID = None
        if descriptor is not None:
            from gui.battle_control.controllers.consumables.ammo_ctrl import _GunSettings
            from gui.Scaleform.daapi.view.battle.shared.crosshair.plugins import _createAmmoSettings
            settings = _createAmmoSettings(_GunSettings.fromVehicle(vehicle.id, vehicle.typeDescriptor))
            parent.as_setClipParamsS(settings.getClipCapacity(), settings.getBurstSize(), settings.reloadingType)
        else:
            from gui.Scaleform.genConsts.CLIP_RELOADING_TYPES import CLIP_RELOADING_TYPES
            parent.as_setClipParamsS(1, 1, CLIP_RELOADING_TYPES.HIDDEN)
        parent.as_setAmmoStockS(-1, -1, 'normal', False)
        parent.as_setAutoloaderReloadingS(0.0, 0.0)
        parent.as_autoloaderUpdateS(0.0, 0.0, isTimerOn=False)
        parent.as_hideBoostS(False)
        parent.as_setIsInControllableReloadS(False)
        parent.as_setShellChangeTimeS(False, '')
        _ammo_render_key = key
    _render_spectator_reload(plugin)


def _spectator_plugin_active():
    player = BigWorld.player() if BigWorld is not None else None
    return _CONFIG.get('enabled', True) and _aim_manager.is_active() and player is not None and not getattr(player, 'isVehicleAlive', True)


def _ammo_plugin_hook(original):
    def handler(plugin, *args, **kwargs):
        global _ammo_plugin
        _ammo_plugin = weakref.ref(plugin)
        if _spectator_plugin_active():
            return _run_hud_step('native spectator reload', lambda: _render_spectator_ammo(plugin))
        return original(plugin, *args, **kwargs)
    return handler


def _shot_plugin_hook(original):
    def handler(plugin, marker):
        if _spectator_plugin_active() and _CONFIG.get('show_teammate_reticle', True):
            try:
                return _spectator_shot_result(marker, getattr(plugin, '_ShotResultIndicatorPlugin__playerTeam', 0), 1.0)
            except Exception:
                _report_error('spectator penetration')
                from aih_constants import SHOT_RESULT
                return SHOT_RESULT.UNDEFINED
        return original(plugin, marker)
    return handler


def _shot_marker_hook(original):
    def handler(plugin, marker_type, marker, support):
        if _spectator_plugin_active() and _CONFIG.get('show_teammate_reticle', True):
            result = plugin._getShotResolverResult(marker)
            colors = getattr(plugin, '_ShotResultIndicatorPlugin__colors', None)
            if colors is not None:
                return plugin._parentObj.setGunMarkerColor(marker_type, colors[result])
            return
        return original(plugin, marker_type, marker, support)
    return handler


def _crew_status_hook(original, buff_status):
    def handler(panel, status_id, duration, animated):
        if status_id == buff_status and _spectator_plugin_active() and _CONFIG.get('show_module_damage', True):
            return panel.as_hideStatusS(status_id, False)
        return original(panel, status_id, duration, animated)
    return handler

_orig_updateVehicleGunReloadTime = None
_orig_showVehicleDamageInfo = None
_orig_onBecomeNonPlayer = None
_orig_showShooting = None
_orig_updateGunMarker = None
_orig_switchVehicle = None
_orig_getCrosshairViewIDByCtrlMode = None
_orig_page_populate = None
_orig_page_dispose = None
_orig_page_switchToPostmortem = None
_orig_pm_enable = None
_orig_pm_disable = None
_orig_dfc_enable = None
_orig_dfc_disable = None


def _load_config():
    global _CONFIG
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        if os.path.isfile(_CONFIG_PATH):
            with open(_CONFIG_PATH, 'rb') as fp:
                data = json.loads(fp.read())
                if isinstance(data, dict):
                    _CONFIG.update(data)
        else:
            with open(_CONFIG_PATH, 'wb') as fp:
                fp.write(json.dumps(_DEFAULT_CONFIG, indent=4))
    except Exception:
        pass


def _ticker_delay():
    try:
        rate = int(_CONFIG.get('update_rate_fps', 0))
    except (TypeError, ValueError):
        rate = 0
    if rate <= 0:
        return 0.0
    return 1.0 / float(min(240, max(1, rate)))


def _aim_tick():
    global _aim_callback_id, _last_hud_update_time
    _aim_callback_id = None
    if not _aim_manager.is_active():
        return
    player = BigWorld.player() if BigWorld is not None else None
    if player is None or getattr(player, 'isVehicleAlive', False) or not _CONFIG.get('enabled', True):
        _on_spectate_stop()
        return
    vehicle_id = _aim_manager._current_vehicle_id
    controlled_id = _controlled_vehicle_id(player, vehicle_id)
    if controlled_id != vehicle_id:
        _on_spectate_vehicle(controlled_id)
        return
    vehicle = _get_vehicle_entity(vehicle_id)
    now = BigWorld.serverTime()
    if vehicle is not None and getattr(vehicle, 'inWorld', False):
        if hasattr(vehicle, 'isAlive') and not vehicle.isAlive():
            _on_spectate_stop()
            return
        if _CONFIG.get('show_teammate_reticle', True):
            server_marker = _tracker.get_server_gun_marker(vehicle_id, now)
            relax = _ticker_delay()
            marker = _run_hud_step('reticle', lambda: _aim_manager.update_aim(vehicle, server_marker=server_marker, shell_hint=_tracker.get_shell_hint(vehicle_id), relax_time=relax))
            if marker is None:
                _run_hud_step('missing aim cleanup', _crosshair_adapter.clear)
    else:
        _run_hud_step('unavailable vehicle cleanup', _crosshair_adapter.clear)
    if now - _last_hud_update_time >= 0.1 or now < _last_hud_update_time:
        _last_hud_update_time = now
        _update_spectator_hud(vehicle_id)
    if _aim_manager.is_active():
        _aim_callback_id = BigWorld.callback(_ticker_delay(), _aim_tick)


def _start_aim_ticker():
    global _aim_callback_id
    if _aim_callback_id is None and BigWorld is not None and hasattr(BigWorld, 'callback'):
        _aim_callback_id = BigWorld.callback(_ticker_delay(), _aim_tick)


def _stop_aim_ticker():
    global _aim_callback_id
    if _aim_callback_id is not None:
        try:
            if BigWorld is not None and hasattr(BigWorld, 'cancelCallback'):
                BigWorld.cancelCallback(_aim_callback_id)
        except Exception:
            pass
        _aim_callback_id = None


def _update_spectator_damage_panel(vehicle_id, page=None):
    if page is None and _active_battle_page is not None:
        page = _active_battle_page()
    vehicle = _get_vehicle_entity(vehicle_id)
    if page is None or vehicle is None or not getattr(vehicle, 'inWorld', False):
        return
    panel = page.getComponent('damagePanel')
    if panel is not None:
        _hud_adapter.bind_damage_panel(panel, vehicle.health, max_health=vehicle.typeDescriptor.maxHealth, device_states=_tracker.get_devices(vehicle_id), vehicle=vehicle)
        if _crew_buff_status_id is not None:
            panel.as_hideStatusS(_crew_buff_status_id, False)


def _update_spectator_hud(vehicle_id):
    if vehicle_id is None or vehicle_id <= 0:
        return
    page = _active_battle_page() if _active_battle_page is not None else None
    now = BigWorld.serverTime() if BigWorld is not None else 0.0
    plugin = _ammo_plugin() if _ammo_plugin is not None else None
    if plugin is not None and _spectator_plugin_active():
        _run_hud_step('native spectator ammo', lambda: _render_spectator_ammo(plugin))
    if _CONFIG.get('show_module_damage', True):
        _run_hud_step('modules', lambda: _update_spectator_damage_panel(vehicle_id, page))
    show_equipment = _CONFIG.get('show_consumables_cooldown', True)
    if show_equipment and page is not None:
        panel = page.getComponent('consumablesPanel')
        _run_hud_step('equipment', lambda: _hud_adapter.bind_consumables_cooldowns(panel, vehicle_id, _tracker, now))
        _run_hud_step('equipment layout', lambda: _hud_adapter.shift_consumables_left(panel, page.getComponent('damagePanel')))
    unknown_equipment = show_equipment and not any(row[1] for row in _tracker.get_equipment_snapshot(vehicle_id, now))
    vehicle = _get_vehicle_entity(vehicle_id)
    unknown_shell = _CONFIG.get('show_teammate_reticle', True) and vehicle is not None and _spectator_shot(vehicle, require_known=True) is None
    _run_hud_step('reload display', lambda: _reload_display.update(vehicle_id, _tracker, now, _CONFIG.get('show_actual_reload', True), unknown_equipment, unknown_shell))


def _on_spectate_vehicle(vehicle_id):
    if vehicle_id is None or vehicle_id <= 0:
        _on_spectate_stop()
        return
    if not _CONFIG.get('enabled', True):
        return
    player = BigWorld.player() if BigWorld is not None else None
    if player is None or getattr(player, 'isVehicleAlive', False) or vehicle_id == getattr(player, 'playerVehicleID', None):
        _on_spectate_stop()
        return
    info = getattr(getattr(player, 'arena', None), 'vehicles', {}).get(vehicle_id, {})
    if info and info.get('team') != getattr(player, 'team', info.get('team')):
        _on_spectate_stop()
        return
    vehicle = _get_vehicle_entity(vehicle_id)
    if vehicle is not None and hasattr(vehicle, 'isAlive') and not vehicle.isAlive():
        _on_spectate_stop()
        return
    if _aim_manager._current_vehicle_id != vehicle_id:
        _run_hud_step('vehicle marker reset', _crosshair_adapter.clear)
        _run_hud_step('vehicle panels reset', _hud_adapter.reset)
        _run_hud_step('vehicle reload reset', _reload_display.clear)
        global _ammo_render_key, _last_hud_update_time
        _ammo_render_key = None
        _last_hud_update_time = 0.0
        page = _active_battle_page() if _active_battle_page is not None else None
        panel = page.getComponent('consumablesPanel') if page is not None else None
        if panel is not None and hasattr(panel, '_resetAmmo'):
            _run_hud_step('previous ammo cleanup', panel._resetAmmo)
    _aim_manager.enable(vehicle_id)
    _run_hud_step('crosshair view', lambda: _refresh_crosshair_view(player))
    page = _active_battle_page() if _active_battle_page is not None else None
    if page is not None:
        _run_hud_step('panel visibility', lambda: _hud_adapter.prevent_consumables_hide(page))
    _update_spectator_hud(vehicle_id)
    _start_aim_ticker()


def _on_spectate_stop():
    global _ammo_render_key
    _ammo_render_key = None
    was_active = _aim_manager.is_active()
    _stop_aim_ticker()
    _aim_manager.disable()
    _run_hud_step('marker cleanup', _crosshair_adapter.clear)
    _run_hud_step('reload cleanup', _reload_display.clear)
    _run_hud_step('equipment cleanup', _hud_adapter.reset)
    player = BigWorld.player() if BigWorld is not None else None
    if was_active and player is not None:
        _run_hud_step('crosshair restore', lambda: _refresh_crosshair_view(player))
        plugin = _ammo_plugin() if _ammo_plugin is not None else None
        provider = getattr(player, 'guiSessionProvider', None)
        ammo = getattr(getattr(provider, 'shared', None), 'ammo', None)
        if plugin is not None and ammo is not None:
            _run_hud_step('native ammo restore', lambda: plugin._AmmoPlugin__setup(ammo, getattr(provider, 'isReplayPlaying', False)))


def _hooked_switchVehicle(self, vehicleID):
    res = _orig_switchVehicle(self, vehicleID)
    try:
        if _CONFIG.get('enabled', True):
            player = BigWorld.player() if (BigWorld is not None and hasattr(BigWorld, 'player')) else None
            player_veh_id = getattr(player, 'playerVehicleID', None) if player is not None else None
            is_alive = getattr(player, 'isVehicleAlive', True) if player is not None else True
            if not is_alive and vehicleID is not None and vehicleID > 0 and vehicleID != player_veh_id:
                _on_spectate_vehicle(_controlled_vehicle_id(player, vehicleID))
            else:
                _on_spectate_stop()
    except Exception:
        pass
    return res


def _hooked_getCrosshairViewIDByCtrlMode(ctrlMode):
    try:
        if _CONFIG.get('enabled', True) and _CONFIG.get('show_teammate_reticle', True):
            player = BigWorld.player() if BigWorld is not None else None
            if _aim_manager.is_active() and player is not None and not getattr(player, 'isVehicleAlive', True) and ctrlMode in ('postmortem', 'deathfreecam', 'respawnDeath'):
                return CROSSHAIR_VIEW_ID.ARCADE
    except Exception:
        pass
    return _orig_getCrosshairViewIDByCtrlMode(ctrlMode)


def _hooked_page_populate(self):
    res = _orig_page_populate(self)
    try:
        global _active_battle_page
        _active_battle_page = weakref.ref(self)
        _logged_errors.clear()
    except Exception:
        pass
    return res


def _hooked_page_dispose(self):
    try:
        _on_spectate_stop()
        global _active_battle_page
        _active_battle_page = None
    except Exception:
        pass
    return _orig_page_dispose(self)


def _hooked_page_switchToPostmortem(self):
    res = _orig_page_switchToPostmortem(self)
    try:
        if _CONFIG.get('enabled', True) and _aim_manager.is_active():
            _hud_adapter.prevent_consumables_hide(self)
    except Exception:
        pass
    return res


def _hooked_updateVehicleGunReloadTime(self, vehicleID, timeLeft, baseTime, clipTime=None):
    result = _orig_updateVehicleGunReloadTime(self, vehicleID, timeLeft, baseTime, clipTime)
    if _CONFIG.get('enabled', True):
        _tracker.record_reload(vehicleID, BigWorld.serverTime(), timeLeft, baseTime, clipTime)
        if _aim_manager.is_active() and _aim_manager._current_vehicle_id == vehicleID:
            _update_spectator_hud(vehicleID)
    return result


def _hooked_showVehicleDamageInfo(self, vehicleID, damageIndex, extraIndex, entityID, equipmentID, ignoreMessages=False):
    result = _orig_showVehicleDamageInfo(self, vehicleID, damageIndex, extraIndex, entityID, equipmentID, ignoreMessages)
    try:
        if _CONFIG.get('enabled', True) and extraIndex:
            import constants
            info = getattr(getattr(self, 'arena', None), 'vehicles', {}).get(vehicleID, {})
            descriptor = info.get('vehicleType', getattr(self, 'vehicleTypeDescriptor', None))
            extras = getattr(descriptor, 'extras', ())
            extra = extras.get(extraIndex) if hasattr(extras, 'get') else extras[extraIndex]
            name = extra.name
            if name.endswith('Health'):
                name = name[:-6]
            code = constants.DAMAGE_INFO_CODES[damageIndex]
            state = None
            if 'REPAIRED_TO_CRITICAL' in code or 'CRITICAL' in code:
                state = 'critical'
            elif 'DESTROYED' in code or 'TANKMAN_HIT' in code:
                state = 'destroyed'
            elif code in ('DEVICE_REPAIRED', 'TANKMAN_RESTORED') or 'NORMAL' in code:
                state = 'normal'
            if state is not None:
                _tracker.record_device_state(vehicleID, name, state)
            if _aim_manager.is_active() and _aim_manager._current_vehicle_id == vehicleID:
                _run_hud_step('damage event', lambda: _update_spectator_damage_panel(vehicleID))
    except Exception:
        _report_error('damage packet')
    return result


def _hooked_onBecomeNonPlayer(self):
    try:
        _on_spectate_stop()
        _tracker.clear()
        global _active_battle_page
        _active_battle_page = None
    except Exception:
        pass
    return _orig_onBecomeNonPlayer(self)


def _hooked_showShooting(self, *args, **kwargs):
    result = _orig_showShooting(self, *args, **kwargs)
    try:
        if _CONFIG.get('enabled', True):
            gun = self.typeDescriptor.gun
            clip = getattr(gun, 'clip', (1, 0.0))
            size = getattr(clip, 'size', clip[0] if isinstance(clip, (tuple, list)) else 1)
            tags = getattr(gun, 'tags', ())
            unsupported = set(tags) & {'dualGun', 'twinGun', 'autoreload', 'autoShoot', 'controllableReload', 'extraShot'}
            if getattr(self, 'isStarted', True) and size == 1 and not unsupported and not getattr(gun, 'reloadTimes', None) and gun.reloadTime > 0.0:
                _tracker.record_shot(self.id, BigWorld.serverTime(), gun.reloadTime)
    except Exception:
        _report_error('shot estimate')
    return result


def _hooked_pm_enable(self, **args):
    res = _orig_pm_enable(self, **args)
    try:
        if _CONFIG.get('enabled', True):
            target_veh_id = getattr(self, 'curVehicleID', None)
            player = BigWorld.player() if (BigWorld is not None and hasattr(BigWorld, 'player')) else None
            player_veh_id = getattr(player, 'playerVehicleID', None) if player is not None else None
            is_self = getattr(self, 'isSelfVehicle', False)
            is_self = is_self() if callable(is_self) else is_self
            if target_veh_id is not None and target_veh_id > 0 and target_veh_id != player_veh_id and not is_self:
                _on_spectate_vehicle(target_veh_id)
            else:
                _on_spectate_stop()
    except Exception:
        pass
    return res


def _hooked_pm_disable(self):
    try:
        _on_spectate_stop()
    except Exception:
        pass
    return _orig_pm_disable(self)


def _hooked_dfc_enable(self, **args):
    res = _orig_dfc_enable(self, **args)
    try:
        if _CONFIG.get('enabled', True):
            cur_veh_id = args.get('curVehicleID')
            player = BigWorld.player() if (BigWorld is not None and hasattr(BigWorld, 'player')) else None
            player_veh_id = getattr(player, 'playerVehicleID', None) if player is not None else None
            cur_veh_id = _controlled_vehicle_id(player)
            is_attached = True
            if hasattr(self, 'isAttachedOnVehicle'):
                try:
                    is_attached = bool(self.isAttachedOnVehicle(cur_veh_id))
                except Exception:
                    is_attached = True
            if cur_veh_id is not None and cur_veh_id > 0 and cur_veh_id != player_veh_id and is_attached:
                _on_spectate_vehicle(cur_veh_id)
            else:
                _on_spectate_stop()
    except Exception:
        pass
    return res


def _hooked_dfc_disable(self):
    try:
        _on_spectate_stop()
    except Exception:
        pass
    return _orig_dfc_disable(self)



def _hooked_damage_panel_controlling(self, vehicle):
    result = _orig_damage_panel_controlling(self, vehicle)
    if _aim_manager.is_active() and _aim_manager._current_vehicle_id == vehicle.id:
        _hud_adapter._damage_key = None
        _run_hud_step('module restore', lambda: _update_spectator_damage_panel(vehicle.id))
    return result


def _hooked_resetVehicleAmmo(self, oldCompactDescr, newCompactDescr, quantity, stage, timeRemaining, totalTime, index):
    result = _orig_resetVehicleAmmo(self, oldCompactDescr, newCompactDescr, quantity, stage, timeRemaining, totalTime, index)
    if _CONFIG.get('enabled', True):
        attached = self.getVehicleAttached() if hasattr(self, 'getVehicleAttached') else None
        vehicle_id = attached.id if attached is not None else self.playerVehicleID
        _tracker.replace_equipment(vehicle_id, oldCompactDescr, newCompactDescr, quantity, stage, timeRemaining, totalTime, index, BigWorld.serverTime())
        if _aim_manager.is_active() and _aim_manager._current_vehicle_id == vehicle_id:
            _update_spectator_hud(vehicle_id)
    return result


def _hooked_updateVehicleAmmo(self, vehicleID, compactDescr, quantity, quantityInClipOrNextStage, previousStage, timeRemaining, totalTime, index=0):
    result = _orig_updateVehicleAmmo(self, vehicleID, compactDescr, quantity, quantityInClipOrNextStage, previousStage, timeRemaining, totalTime, index)
    try:
        if _CONFIG.get('enabled', True):
            from items import ITEM_TYPE_INDICES, getTypeOfCompactDescr
            if not compactDescr or getTypeOfCompactDescr(compactDescr) == ITEM_TYPE_INDICES['equipment']:
                _tracker.record_equipment(vehicleID, compactDescr, quantity, quantityInClipOrNextStage, timeRemaining, totalTime, index, BigWorld.serverTime())
                if _aim_manager.is_active() and _aim_manager._current_vehicle_id == vehicleID:
                    _update_spectator_hud(vehicleID)
            elif compactDescr and getTypeOfCompactDescr(compactDescr) == ITEM_TYPE_INDICES['shell'] and _aim_manager.is_active() and _aim_manager._current_vehicle_id == vehicleID:
                _tracker.record_shell_hint(vehicleID, compactDescr, BigWorld.serverTime())
    except Exception:
        _report_error('equipment packet')
    return result


def _hooked_updateGunMarker(self, vehicleID, shotPos, shotVec, dispersionAngle):
    if _CONFIG.get('enabled', True):
        _tracker.record_gun_marker(vehicleID, BigWorld.serverTime(), shotPos, shotVec, dispersionAngle)
    return _orig_updateGunMarker(self, vehicleID, shotPos, shotVec, dispersionAngle)


def init():
    global _orig_updateVehicleAmmo, _orig_resetVehicleAmmo, _orig_damage_panel_controlling
    global _orig_updateVehicleGunReloadTime
    global _orig_showVehicleDamageInfo
    global _orig_onBecomeNonPlayer
    global _orig_showShooting
    global _orig_updateGunMarker
    global _orig_switchVehicle
    global _orig_getCrosshairViewIDByCtrlMode
    global _orig_page_populate
    global _orig_page_dispose
    global _orig_page_switchToPostmortem
    global _orig_pm_enable
    global _orig_pm_disable
    global _orig_dfc_enable
    global _orig_dfc_disable

    _load_config()
    try:
        from gui.Scaleform.daapi.view.battle.shared.crosshair.plugins import AmmoPlugin, ShotResultIndicatorPlugin
        if not _plugin_hooks:
            for name in ('__setup', '__onGunSettingsSet', '__onGunReloadCleared', '__onGunReloadTimeSet', '__onPredictedGunReloadTimeSet', '__onGunAutoReloadTimeSet', '__onGunAutoReloadBoostUpd', '__onShellsUpdated', '__onCurrentShellChanged', '__onCurrentShellReset', '__onShellChangeTimeUpdated', '__autoReloadFirstShellCallback'):
                attribute = '_AmmoPlugin' + name
                if hasattr(AmmoPlugin, attribute):
                    original = getattr(AmmoPlugin, attribute)
                    _plugin_hooks.append((AmmoPlugin, attribute, original))
                    setattr(AmmoPlugin, attribute, _ammo_plugin_hook(original))
            for attribute, factory in (('_getShotResolverResult', _shot_plugin_hook), ('_ShotResultIndicatorPlugin__onGunMarkerStateChanged', _shot_marker_hook)):
                original = getattr(ShotResultIndicatorPlugin, attribute)
                _plugin_hooks.append((ShotResultIndicatorPlugin, attribute, original))
                setattr(ShotResultIndicatorPlugin, attribute, factory(original))
    except ImportError:
        _report_error('crosshair plugin hooks')

    try:
        from Avatar import Avatar
        if _orig_updateVehicleAmmo is None and hasattr(Avatar, 'updateVehicleAmmo'):
            _orig_updateVehicleAmmo = Avatar.updateVehicleAmmo
            Avatar.updateVehicleAmmo = _hooked_updateVehicleAmmo
        if _orig_resetVehicleAmmo is None and hasattr(Avatar, 'resetVehicleAmmo'):
            _orig_resetVehicleAmmo = Avatar.resetVehicleAmmo
            Avatar.resetVehicleAmmo = _hooked_resetVehicleAmmo
        if _orig_updateVehicleGunReloadTime is None and hasattr(Avatar, 'updateVehicleGunReloadTime'):
            _orig_updateVehicleGunReloadTime = Avatar.updateVehicleGunReloadTime
            Avatar.updateVehicleGunReloadTime = _hooked_updateVehicleGunReloadTime
        if _orig_showVehicleDamageInfo is None and hasattr(Avatar, 'showVehicleDamageInfo'):
            _orig_showVehicleDamageInfo = Avatar.showVehicleDamageInfo
            Avatar.showVehicleDamageInfo = _hooked_showVehicleDamageInfo
        if _orig_updateGunMarker is None and hasattr(Avatar, 'updateGunMarker'):
            _orig_updateGunMarker = Avatar.updateGunMarker
            Avatar.updateGunMarker = _hooked_updateGunMarker
        if _orig_onBecomeNonPlayer is None and hasattr(Avatar, 'onBecomeNonPlayer'):
            _orig_onBecomeNonPlayer = Avatar.onBecomeNonPlayer
            Avatar.onBecomeNonPlayer = _hooked_onBecomeNonPlayer
    except Exception:
        pass

    try:
        from Vehicle import Vehicle
        if _orig_showShooting is None and hasattr(Vehicle, 'showShooting'):
            _orig_showShooting = Vehicle.showShooting
            Vehicle.showShooting = _hooked_showShooting
    except Exception:
        pass

    try:
        from gui.battle_control.battle_session import BattleSessionProvider
        if _orig_switchVehicle is None and hasattr(BattleSessionProvider, 'switchVehicle'):
            _orig_switchVehicle = BattleSessionProvider.switchVehicle
            BattleSessionProvider.switchVehicle = _hooked_switchVehicle
    except Exception:
        pass

    try:
        import gui.battle_control.controllers.crosshair_proxy as cp_mod
        if _orig_getCrosshairViewIDByCtrlMode is None and hasattr(cp_mod, 'getCrosshairViewIDByCtrlMode'):
            _orig_getCrosshairViewIDByCtrlMode = cp_mod.getCrosshairViewIDByCtrlMode
            cp_mod.getCrosshairViewIDByCtrlMode = _hooked_getCrosshairViewIDByCtrlMode
    except Exception:
        pass

    try:
        from gui.Scaleform.daapi.view.battle.shared.page import SharedPage
        if _orig_page_populate is None and hasattr(SharedPage, '_populate'):
            _orig_page_populate = SharedPage._populate
            SharedPage._populate = _hooked_page_populate
        if _orig_page_dispose is None and hasattr(SharedPage, '_dispose'):
            _orig_page_dispose = SharedPage._dispose
            SharedPage._dispose = _hooked_page_dispose
        if _orig_page_switchToPostmortem is None and hasattr(SharedPage, '_switchToPostmortem'):
            _orig_page_switchToPostmortem = SharedPage._switchToPostmortem
            SharedPage._switchToPostmortem = _hooked_page_switchToPostmortem
    except Exception:
        pass

    try:
        from AvatarInputHandler.control_modes import PostMortemControlMode
        if _orig_pm_enable is None and hasattr(PostMortemControlMode, 'enable'):
            _orig_pm_enable = PostMortemControlMode.enable
            PostMortemControlMode.enable = _hooked_pm_enable
        if _orig_pm_disable is None and hasattr(PostMortemControlMode, 'disable'):
            _orig_pm_disable = PostMortemControlMode.disable
            PostMortemControlMode.disable = _hooked_pm_disable
    except Exception:
        pass

    try:
        from AvatarInputHandler.control_modes import DeathFreeCamMode
        if _orig_dfc_enable is None and hasattr(DeathFreeCamMode, 'enable'):
            _orig_dfc_enable = DeathFreeCamMode.enable
            DeathFreeCamMode.enable = _hooked_dfc_enable
        if _orig_dfc_disable is None and hasattr(DeathFreeCamMode, 'disable'):
            _orig_dfc_disable = DeathFreeCamMode.disable
            DeathFreeCamMode.disable = _hooked_dfc_disable
    except Exception:
        pass

    try:
        from gui.Scaleform.daapi.view.battle.shared.damage_panel import DamagePanel, STATUS_ID
        global _crew_buff_status_id
        _crew_buff_status_id = STATUS_ID.BUFF
        if not any(owner is DamagePanel and attribute == 'as_showStatusS' for owner, attribute, original in _plugin_hooks):
            original = DamagePanel.as_showStatusS
            _plugin_hooks.append((DamagePanel, 'as_showStatusS', original))
            DamagePanel.as_showStatusS = _crew_status_hook(original, STATUS_ID.BUFF)
        if _orig_damage_panel_controlling is None:
            _orig_damage_panel_controlling = DamagePanel._DamagePanel__onVehicleControlling
            DamagePanel._DamagePanel__onVehicleControlling = _hooked_damage_panel_controlling
    except Exception:
        _report_error('damage panel hook')

    try:
        from debug_utils import LOG_NOTE
        LOG_NOTE('[SpectatorHUD] 1.0.7 initialized')
    except Exception:
        pass


def fini():
    global _orig_updateVehicleAmmo, _orig_resetVehicleAmmo, _orig_damage_panel_controlling
    _on_spectate_stop()
    global _ammo_plugin
    _ammo_plugin = None
    for owner, attribute, original in reversed(_plugin_hooks):
        setattr(owner, attribute, original)
    del _plugin_hooks[:]
    global _orig_updateVehicleGunReloadTime
    global _orig_showVehicleDamageInfo
    global _orig_onBecomeNonPlayer
    global _orig_showShooting
    global _orig_updateGunMarker
    global _orig_switchVehicle
    global _orig_getCrosshairViewIDByCtrlMode
    global _orig_page_populate
    global _orig_page_dispose
    global _orig_page_switchToPostmortem
    global _orig_pm_enable
    global _orig_pm_disable
    global _orig_dfc_enable
    global _orig_dfc_disable
    global _active_battle_page

    if _orig_damage_panel_controlling is not None:
        from gui.Scaleform.daapi.view.battle.shared.damage_panel import DamagePanel
        DamagePanel._DamagePanel__onVehicleControlling = _orig_damage_panel_controlling
        _orig_damage_panel_controlling = None
    _stop_aim_ticker()
    _aim_manager.disable()
    _tracker.clear()
    _active_battle_page = None

    try:
        from Avatar import Avatar
        if _orig_updateVehicleAmmo is not None:
            Avatar.updateVehicleAmmo = _orig_updateVehicleAmmo
            _orig_updateVehicleAmmo = None
        if _orig_resetVehicleAmmo is not None:
            Avatar.resetVehicleAmmo = _orig_resetVehicleAmmo
            _orig_resetVehicleAmmo = None
        if _orig_updateVehicleGunReloadTime is not None:
            Avatar.updateVehicleGunReloadTime = _orig_updateVehicleGunReloadTime
            _orig_updateVehicleGunReloadTime = None
        if _orig_showVehicleDamageInfo is not None:
            Avatar.showVehicleDamageInfo = _orig_showVehicleDamageInfo
            _orig_showVehicleDamageInfo = None
        if _orig_updateGunMarker is not None:
            Avatar.updateGunMarker = _orig_updateGunMarker
            _orig_updateGunMarker = None
        if _orig_onBecomeNonPlayer is not None:
            Avatar.onBecomeNonPlayer = _orig_onBecomeNonPlayer
            _orig_onBecomeNonPlayer = None
    except Exception:
        pass

    try:
        from Vehicle import Vehicle
        if _orig_showShooting is not None:
            Vehicle.showShooting = _orig_showShooting
            _orig_showShooting = None
    except Exception:
        pass

    try:
        from gui.battle_control.battle_session import BattleSessionProvider
        if _orig_switchVehicle is not None:
            BattleSessionProvider.switchVehicle = _orig_switchVehicle
            _orig_switchVehicle = None
    except Exception:
        pass

    try:
        import gui.battle_control.controllers.crosshair_proxy as cp_mod
        if _orig_getCrosshairViewIDByCtrlMode is not None:
            cp_mod.getCrosshairViewIDByCtrlMode = _orig_getCrosshairViewIDByCtrlMode
            _orig_getCrosshairViewIDByCtrlMode = None
    except Exception:
        pass

    try:
        from gui.Scaleform.daapi.view.battle.shared.page import SharedPage
        if _orig_page_populate is not None:
            SharedPage._populate = _orig_page_populate
            _orig_page_populate = None
        if _orig_page_dispose is not None:
            SharedPage._dispose = _orig_page_dispose
            _orig_page_dispose = None
        if _orig_page_switchToPostmortem is not None:
            SharedPage._switchToPostmortem = _orig_page_switchToPostmortem
            _orig_page_switchToPostmortem = None
    except Exception:
        pass

    try:
        from AvatarInputHandler.control_modes import PostMortemControlMode
        if _orig_pm_enable is not None:
            PostMortemControlMode.enable = _orig_pm_enable
            _orig_pm_enable = None
        if _orig_pm_disable is not None:
            PostMortemControlMode.disable = _orig_pm_disable
            _orig_pm_disable = None
    except Exception:
        pass

    try:
        from AvatarInputHandler.control_modes import DeathFreeCamMode
        if _orig_dfc_enable is not None:
            DeathFreeCamMode.enable = _orig_dfc_enable
            _orig_dfc_enable = None
        if _orig_dfc_disable is not None:
            DeathFreeCamMode.disable = _orig_dfc_disable
            _orig_dfc_disable = None
    except Exception:
        pass

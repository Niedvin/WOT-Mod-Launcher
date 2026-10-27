# -*- coding: utf-8 -*-
from __future__ import division

_BASE_DEVICES = ('engine', 'ammoBay', 'fuelTank', 'radio', 'gun', 'turretRotator', 'surveyingDevice')
_TRACKS = ('leftTrack0', 'rightTrack0')
_CREW = ('commander', 'driver', 'radioman', 'gunner', 'loader')


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
                bounds = renderer.getBounds(clip.parent)
                if float(bounds.width) > 0 and float(bounds.height) > 0:
                    rectangles.append(bounds)
        if not rectangles:
            return
        native_size = self._native_stage_size(clip, damage)
        left = min(float(bounds.x) for bounds in rectangles) - float(clip.x)
        bottom = max(float(bounds.y) + float(bounds.height) for bounds in rectangles) - float(clip.y)
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

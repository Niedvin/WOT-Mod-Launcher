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
        self._equipment_state = {}
        self._consumables_layout = None
        self._consumables_stage = None
        self._consumables_padding = None
        self._consumables_bottom = 48.0
        self._consumables_defer = False

    def _restore_consumables_layout(self):
        layout = self._consumables_layout
        self._consumables_layout = None
        self._consumables_stage = None
        self._consumables_padding = None
        self._consumables_defer = False
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

    @staticmethod
    def _place(clip, target_x, target_y):
        try:
            if abs(float(clip.x) - target_x) < 0.5 and abs(float(clip.y) - target_y) < 0.5:
                return
        except Exception:
            pass
        clip.x = target_x
        clip.y = target_y

    def _row_bottom(self, clip):
        bottom = None
        for index in range(15):
            renderer = clip.getRendererBySlotIdx(index)
            if renderer is None or not renderer.visible:
                continue
            anchor = getattr(renderer, 'hit', None) or getattr(renderer, 'iconLoader', None)
            if anchor is None:
                continue
            # Hidden glow clips inflate renderer bounds beyond visible buttons. — 2026-10-28
            try:
                bounds = anchor.getBounds(clip)
            except Exception:
                continue
            if float(bounds.width) > 0 and float(bounds.height) > 0:
                value = float(bounds.y) + float(bounds.height)
                if bottom is None or value > bottom:
                    bottom = value
        if bottom is not None:
            self._consumables_bottom = bottom
        return self._consumables_bottom

    def _stage_padding(self, clip):
        if self._consumables_padding is None:
            # Bottom padding differs per mode (58 stock, 86 Halloween), so measure it before resizing — 2026-10-31
            try:
                padding = float(clip.stage.stageHeight) - float(clip.y)
            except Exception:
                return 58.0
            if 0.0 < padding < 200.0:
                self._consumables_padding = padding
            else:
                return 58.0
        return self._consumables_padding

    @staticmethod
    def _reset_equipment_slots(panel):
        start = getattr(panel, '_HW_EQUIPMENT_START_IDX', None)
        end = getattr(panel, '_HW_EQUIPMENT_END_IDX', None)
        slots = []
        if start is not None and end is not None and getattr(panel, '_cds', None) is not None:
            # Event abilities are booked in 3..5, which _resetEquipments leaves untouched — 2026-10-31
            slots = [index for index in range(start, end + 1) if index < len(panel._cds)]
            mask = 0
            for index in slots:
                panel._cds[index] = None
                mask |= 1 << index
            if hasattr(panel, '_mask'):
                panel._mask &= ~mask
            if slots and hasattr(panel, 'as_resetPassiveAbilitiesS'):
                panel.as_resetPassiveAbilitiesS(slots)
            if slots and hasattr(panel, 'as_resetS'):
                panel.as_resetS(slots)
        if hasattr(panel, '_resetEquipments'):
            panel._resetEquipments()
        else:
            panel._reset()

    def shift_consumables_left(self, panel, damage_panel):
        clip = getattr(panel, 'flashObject', None)
        damage = getattr(damage_panel, 'flashObject', None)
        if clip is None or damage is None:
            return
        layout = self._consumables_layout
        if layout is not None and layout[1] is not clip:
            self._restore_consumables_layout()
        native_size = self._native_stage_size(clip, damage)
        padding = self._stage_padding(clip)
        # DamagePanel reserves 230 px independently of animated child bounds in WoT 2.4.1.0 — 2026-10-27
        target_x = float(damage.x) + 230.0 + 12.0
        target_y = native_size[1] - 4.0 - self._row_bottom(clip)
        # Native redraws re-center the clip from the stage size, so place the row on every tick — 2026-10-31
        self._place(clip, target_x, target_y)
        if self._consumables_defer:
            # Rebuilt row gets its final width on the next frame; resize the stage then, but never skip the placement — 2026-10-31
            self._consumables_defer = False
            self._consumables_layout = (panel, clip, damage, native_size)
            return
        stage_width = 2.0 * target_x + float(clip.basePanelWidth)
        stage_height = target_y + padding
        applied = self._consumables_stage
        if applied is not None and applied[0] is clip and abs(applied[1] - stage_width) < 0.5 and abs(applied[2] - stage_height) < 0.5:
            self._consumables_layout = (panel, clip, damage, native_size)
            return
        # updateStage per tick re-runs updatePosition and makes the whole row blink — 2026-10-28
        clip.updateStage(stage_width, stage_height)
        self._consumables_stage = (clip, stage_width, stage_height)
        self._consumables_layout = (panel, clip, damage, native_size)

    def reset(self):
        self._restore_consumables_layout()
        for item in self._equipment_items.values():
            if hasattr(item, 'clear'):
                item.clear()
        self._damage_key = self._equipment_key = None
        self._device_states.clear()
        self._equipment_items.clear()
        self._equipment_state.clear()
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
        signature = tuple(sorted(set(row[1] for row in snapshots if row[1])))
        if key != self._equipment_key or signature != self._equipment_signature:
            for item in self._equipment_items.values():
                if hasattr(item, 'clear'):
                    item.clear()
            self._equipment_items.clear()
            self._equipment_state.clear()
            self._equipment_key = key
            self._equipment_signature = signature
            self._reset_equipment_slots(panel)
            # The rebuilt row reports its final width on the next frame, so resize the stage after it — 2026-10-31
            self._consumables_defer = True
        if not signature:
            return
        import constants
        from items import vehicles
        try:
            from gui.battle_control.controllers.consumables.equipment_ctrl import EquipmentsReplayPlayer as item_factory
        except ImportError:
            from gui.battle_control.controllers.consumables.equipment_ctrl import EquipmentsController as item_factory
        active_stage = getattr(getattr(constants, 'EQUIPMENT_STAGES', None), 'ACTIVE', None)
        empty_slots = 0
        touched = False
        for index, item_cd, quantity, stage, remaining, total in snapshots:
            if not item_cd:
                empty_slots += 1
                if panel._cds.count(0) < empty_slots:
                    panel._onEquipmentAdded(0, None)
                    touched = True
                continue
            remaining = max(0.0, remaining)
            state = (quantity, stage, int(remaining), int(total))
            item = self._equipment_items.get(item_cd)
            previous = self._equipment_state.get(item_cd)
            created = False
            if item is None:
                descriptor = vehicles.getItemByCompactDescr(item_cd)
                if descriptor is None:
                    continue
                item = item_factory.createItem(descriptor, quantity, stage, remaining, total)
                if item is None:
                    continue
                self._equipment_items[item_cd] = item
                created = True
            if created or item_cd not in panel._cds:
                item.update(quantity, stage, remaining, total)
                self._equipment_state[item_cd] = state
                panel._onEquipmentAdded(item_cd, item)
                panel._onEquipmentCooldownTime(item_cd, state[2], stage == active_stage, False)
                touched = True
            elif previous != state:
                self._equipment_state[item_cd] = state
                if previous is None or previous[:2] != state[:2] or previous[3] != state[3] or (state[2] == 0 and previous[2] > 0):
                    item.update(quantity, stage, remaining, total)
                    panel._onEquipmentUpdated(item_cd, item)
                    panel._onEquipmentCooldownTime(item_cd, state[2], stage == active_stage, False)
                else:
                    # Snapshot refresh rewrites only the counter; full update restarts its flash. — 2026-10-28
                    panel._onEquipmentCooldownTime(item_cd, state[2], stage == active_stage, False)
            if item_cd in panel._cds and hasattr(panel, '_onEquipmentCooldownInPercent') and (remaining > 0.0 or previous != state):
                percent = max(0.0, min(100.0, 100.0 * (total - remaining) / total)) if total > 0 else 100.0
                panel._onEquipmentCooldownInPercent(item_cd, percent)
        if touched and hasattr(panel, 'as_showEquipmentSlotsS'):
            # An empty slot hides the whole row; re-show it after the replay re-adds real slots. — 2026-10-28
            panel.as_showEquipmentSlotsS(True)

    bind_consumables_panel = bind_consumables_cooldowns

    def prevent_consumables_hide(self, page):
        if page is not None and hasattr(page, '_setComponentsVisibility'):
            page._setComponentsVisibility(visible={'consumablesPanel', 'damagePanel'}, hidden=set())

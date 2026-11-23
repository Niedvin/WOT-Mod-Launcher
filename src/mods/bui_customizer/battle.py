# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

import BigWorld
import GUI
import Keys

from . import layout, rating
from .overlay import EditorOverlay, TeamStrip


LOGGER = logging.getLogger('Niedvin/BUI')
CONSUMER = 'BuiCustomizer'
MOUSE_BUTTONS = (Keys.KEY_LEFTMOUSE, Keys.KEY_RIGHTMOUSE)
BLOCKED = frozenset((
    'battleLoading', 'fullStats', 'tabScreen', 'radialMenu', 'battleStatisticDataController',
    'battleVehicleConfigurator', 'prebattleAmmunitionPanel', 'fullscreenMap', 'playersPanel',
    'deathCamHud', 'markers2D', 'hitDirection', 'damageIndicator', 'predictionIndicator',
    'battleRoyaleWinnerCongrats', 'killCamSoundPlayer', 'questProgressTopView',
))
FIELDS = {
    'teamBasesPanel': 'teamBasesPanelUI',
    'timersPanel': 'destroyTimersPanel',
    'postmortemPanel': 'postmortemPanelUI',
    'spectatorView': 'spectatorViewUI',
    'battleHintPanel': 'hintPanel',
    'situationIndicators': 'situationIndicatorsPanel',
    'widgetPanel': 'widgetsPanel',
    'battleEndWarningPanel': 'endWarningPanel',
    'siegeModeIndicator': 'siegeModePanel',
}


def interface_scale():
    try:
        from helpers import dependency
        from skeletons.account_helpers.settings_core import ISettingsCore
        value = round(float(dependency.instance(ISettingsCore).interfaceScale.get()), 1)
    except Exception:
        return 1.0
    # Battle Flash works in screen pixels / interface scale, as CrosshairDataProxy converts them — 2026-11-23
    return value if value > 1.0 else 1.0


def flash_bounds(clip, relative_to):
    bounds = clip.getBounds(relative_to)
    return tuple(float(getattr(bounds, key)) for key in ('x', 'y', 'width', 'height'))


def display_visible(clip, check_alpha=True):
    alpha = getattr(clip, 'alpha', None) if check_alpha else None
    return bool(getattr(clip, 'visible', True)) and (alpha is None or float(alpha) > 0.01)


def visible_content(clip, skip_name=None):
    if not display_visible(clip):
        return
    if skip_name is not None and getattr(clip, 'name', None) == skip_name:
        return
    count = int(getattr(clip, 'numChildren', 0) or 0)
    if count:
        for index in range(count):
            child = clip.getChildAt(index)
            if child is not None:
                for item in visible_content(child, skip_name):
                    yield item
    else:
        text = getattr(clip, 'text', None)
        if (not isinstance(text, basestring) or text.strip()) and getattr(clip, 'getBounds', None) is not None:
            yield clip


def equipment_slots(clip):
    for i in range(int(getattr(clip, 'numChildren', 0) or 0)):
        slot = clip.getChildAt(i)
        child = getattr(slot, 'getChildByName', None)
        if child is not None and display_visible(slot):
            hit = child(b'hit') or child(b'iconLoader')
            if hit is not None:
                yield hit


def enclosing_rect(rectangles):
    left = min(rect[0] for rect in rectangles)
    top = min(rect[1] for rect in rectangles)
    right = max(rect[0] + rect[2] for rect in rectangles)
    bottom = max(rect[1] + rect[3] for rect in rectangles)
    return left, top, right - left, bottom - top


class Widget(object):
    def __init__(self, clip, draw_clip=None):
        self.clip = clip
        self.draw_clip = draw_clip if draw_clip is not None else clip
        self.base = None
        self.applied = None

    def transform(self):
        return tuple(float(getattr(self.clip, name)) for name in ('x', 'y', 'scaleX', 'scaleY'))

    def write_transform(self, values):
        self.clip.x, self.clip.y, self.clip.scaleX, self.clip.scaleY = values

    def apply(self, target, rect, local):
        x, y, width, height = rect
        if local[2] <= 0 or local[3] <= 0:
            return
        current = self.transform()
        if self.applied is None:
            self.base = current
        else:
            self.base = tuple(new if abs(new - applied) > 0.001 else base
                              for new, applied, base in zip(current, self.applied, self.base))
        u, v, w, h = target
        if max(abs(a - b) for a, b in zip(target, (x, y, width, height))) < 0.25:
            return
        origin_x, origin_y, sx, sy = current
        factor_x, factor_y = w / width, h / height
        parent_x, parent_y = local[2] / width, local[3] / height
        left = origin_x + (u - x) * parent_x + (local[0] - origin_x) * (1 - factor_x)
        top = origin_y + (v - y) * parent_y + (local[1] - origin_y) * (1 - factor_y)
        self.write_transform((left, top, sx * factor_x, sy * factor_y))
        self.applied = self.transform()

    def restore(self):
        if self.applied is not None:
            current = self.transform()
            self.write_transform(tuple(base if abs(value - applied) <= 0.001 else value
                                       for value, applied, base in zip(current, self.applied, self.base)))
        self.base = self.applied = None


class BattleLayout(object):
    def __init__(self, page, edit_key):
        self.edit_key = getattr(Keys, 'KEY_' + edit_key, None) if edit_key else None
        self.page = page
        self.state = layout.load()
        self.widgets = {}
        self.stage = None
        self.screen = None
        self.strips = {key: TeamStrip(key) for key in layout.TEAMS}
        self.native = {}
        self.editor = EditorOverlay()
        self.bounds = {}
        self.hit_bounds = {}
        self.focus_key = None
        self.native_visible = set()
        self.drag = None
        self.active = False
        self.wants_alt = False
        self.block_release = set()
        self.buttons_down = set()
        self.flash_mouse = None
        self.timer = None
        self.next_scan = 0
        self.next_layout = 0
        self.last_error = None

    def refresh_widgets(self):
        root = self.page.flashObject
        if root is None:
            return
        # Scaleform Python returns no stage on the battle page itself — 2026-11-18
        self.stage = root
        panel = getattr(root, 'playersPanel', None)
        if panel is not None:
            for key, attr in (('allies', 'listLeft'), ('enemies', 'listRight')):
                clip = getattr(panel, attr, None)
                if clip is not None:
                    self.add_widget(key, clip, self.list_renderers(clip))
            self.add_widget('panelSwitch', getattr(panel, 'panelSwitch', None))
        postmortem = root.getChildByName(b'postmortemPanelUI')
        rating_host = postmortem.getChildByName(b'postmortemInfoPanel') if postmortem is not None else None
        if rating_host is not None and getattr(rating_host, 'numChildren', 0):
            self.add_widget('postmortemInfoPage', rating_host.getChildAt(0))
        names = (set(self.page.components) | set(layout.ELEMENTS)) - BLOCKED
        for key in names:
            if key in layout.TEAMS or key in ('panelSwitch', 'postmortemInfoPage'):
                continue
            component = self.page.getComponent(key)
            clip = getattr(component, 'flashObject', None)
            if key == 'consumablesPanel':
                # Component and timeline proxies can point to empty instances — 2026-11-20
                clip = root.getChildByName(b'consumablesPanel') or clip
            elif key == 'postmortemPanel':
                clip = postmortem or clip
            if clip is None:
                clip = getattr(root, str(FIELDS.get(key, key)), None)
            if clip is not None and getattr(clip, 'getBounds', None) is not None:
                draw_clip = None
                if key == 'minimap':
                    clip = getattr(root, 'minimap', None) or clip
                    draw_clip = getattr(clip, 'mapHit', None)
                    if draw_clip is None:
                        continue
                self.add_widget(key, clip, draw_clip)

    @staticmethod
    def list_renderers(clip):
        for index in range(int(getattr(clip, 'numChildren', 0) or 0) - 1, -1, -1):
            child = clip.getChildAt(index)
            if int(getattr(child, 'numChildren', 0) or 0) > 2:
                return child

    def add_widget(self, key, clip, draw_clip=None):
        if clip is None:
            return
        current = self.widgets.get(key)
        if current is None:
            self.widgets[key] = Widget(clip, draw_clip)
        else:
            current.clip = clip
            current.draw_clip = draw_clip if draw_clip is not None else clip

    def row_data(self):
        provider = self.page.sessionProvider
        arena = provider.getArenaDP()
        field = provider.dynamic.battleField
        rows = {key: [] for key in layout.TEAMS}
        for info in sorted(arena.getVehiclesInfoIterator()):
            if info.isObserver():
                continue
            vehicle = info.vehicleType
            health = field.getVehicleHealthInfo(info.vehicleID) if field is not None else None
            hp = None
            if not info.isAlive():
                hp = 0.0
            elif health and health[0] >= 0 and health[1] > 0:
                hp = min(1.0, float(health[0]) / health[1])
            team = 'allies' if arena.isAllyTeam(info.team) else 'enemies'
            rows[team].append((info.vehicleID, vehicle.shortName, vehicle.level, vehicle.iconName, hp))
        return rows

    def restore_list(self, key):
        native = self.native.pop(key, None)
        if native:
            clip, alpha, mouse_enabled, mouse_children = native
            try:
                clip.alpha = alpha
                clip.mouseEnabled = mouse_enabled
                clip.mouseChildren = mouse_children
            except AttributeError:
                pass
        self.strips[key].hide()

    def show_list(self, key, clip):
        original = self.native.get(key)
        if original is None:
            self.native[key] = (clip, clip.alpha, clip.mouseEnabled, clip.mouseChildren)
        else:
            self.native[key] = (clip,) + original[1:]
        clip.alpha = 0
        clip.mouseEnabled = False
        clip.mouseChildren = False

    def preset(self, key, mode):
        return self.state['elements'].get(key, {}).get(mode)

    def controls_equipment_position(self):
        return (self.preset('consumablesPanel', 'slots') is not None or
                self.drag is not None and self.drag['key'] == 'consumablesPanel')

    def target(self, key, mode, original):
        if self.drag is not None and self.drag['key'] == key and self.drag['mode'] == mode:
            return self.drag['target']
        saved = self.preset(key, mode)
        return layout.denormalize(saved, self.screen) if saved is not None else original

    def update_visibility(self):
        self.native_visible = set(self.page.as_getComponentsVisibilityS() or ())

    def render_layout(self):
        self.bounds.clear()
        self.hit_bounds.clear()
        self.update_visibility()
        self.render_teams()
        self.render_widgets(self.active)

    def render_teams(self):
        visible = self.page.isGuiVisible() and not self.page._isBattleLoading
        rows = self.row_data() if visible and self.state['top'] else {}
        for key, strip in self.strips.items():
            widget = self.widgets.get(key)
            if not widget or key not in self.state['top'] or not rows.get(key) or not self.on_screen(key, widget.clip):
                self.restore_list(key)
                continue
            widget.restore()
            target = self.target(key, 'top', strip.default_rect(self.screen, len(rows[key])))
            strip.update(rows[key], target, self.screen)
            self.show_list(key, widget.clip)
            self.bounds[key] = target

    def on_screen(self, key, clip):
        alias = 'playersPanel' if key in layout.TEAMS or key == 'panelSwitch' else key
        if key != 'postmortemInfoPage' and alias not in self.native_visible:
            return False
        if key in ('postmortemPanel', 'postmortemInfoPage') and not self.page._isInPostmortem:
            return False
        if key == 'sixthSense' and getattr(clip, 'currentFrame', None) == 1:
            return False
        if not display_visible(clip, check_alpha=key not in self.native):
            return False
        parent = getattr(clip, 'parent', None)
        while parent is not None:
            if not display_visible(parent):
                return False
            parent = getattr(parent, 'parent', None)
        return True

    def intersects_screen(self, rect):
        x, y, width, height = rect
        sw, sh = self.screen
        return x < sw and y < sh and x + width > 0 and y + height > 0

    def widget_geometry(self, key, widget):
        sw, sh = self.screen
        dynamic = key not in layout.ALWAYS_VISIBLE
        if key == 'consumablesPanel':
            clips = equipment_slots(widget.draw_clip)
        elif key == 'postmortemPanel':
            clips = visible_content(widget.draw_clip, 'postmortemInfoPanel')
        elif key == 'postmortemInfoPage':
            clips = (widget.draw_clip,)
        else:
            clips = visible_content(widget.draw_clip) if dynamic else (widget.draw_clip,)
        found = []
        for clip in clips:
            rect = self.region_bounds(key, clip, self.stage)
            if rect is None:
                continue
            _, _, width, height = rect
            if not (width > 0 and height > 0 and width <= sw * 1.15 and height <= sh * 1.15):
                continue
            if width > sw * 0.82 and height > sh * 0.82:
                continue
            if key in ('minimap', 'consumablesPanel') or self.intersects_screen(rect):
                found.append((clip, rect))
        return found

    @staticmethod
    def region_bounds(key, clip, relative_to):
        bounds = flash_bounds(clip, relative_to)
        return rating.content_bounds(bounds) if key == 'postmortemInfoPage' else bounds

    def chat_hit_regions(self, widget):
        regions = []
        for clip in visible_content(widget.draw_clip):
            if not isinstance(getattr(clip, 'text', None), basestring):
                continue
            rect = flash_bounds(clip, self.stage)
            if min(rect[2:]) > 0 and self.intersects_screen(rect):
                regions.append(rect)
        return regions

    def render_widgets(self, edited):
        hud_visible = self.page.isGuiVisible() and not self.page._isBattleLoading
        for key, widget in self.widgets.items():
            if not hud_visible or key in self.native:
                continue
            mode = layout.normal_mode(key)
            saved = self.preset(key, mode)
            if saved is None and not edited:
                continue
            if key == 'consumablesPanel':
                displayed = self.stage.getChildByName(b'consumablesPanel')
                if displayed is not None:
                    widget.clip = widget.draw_clip = displayed
            if not self.on_screen(key, widget.clip):
                continue
            geometry = self.widget_geometry(key, widget)
            if not geometry:
                if key in ('minimap', 'consumablesPanel'):
                    widget.restore()
                continue
            clips, regions = zip(*geometry)
            rect = enclosing_rect(regions)
            if min(rect[2:]) <= 4:
                continue
            if (key not in layout.ALWAYS_VISIBLE and rect[2] > self.screen[0] * 0.82
                    and rect[3] > self.screen[1] * 0.82):
                continue
            target = self.target(key, mode, rect)
            if target != rect:
                local = self.parent_region(key, widget, clips, rect)
                widget.apply(target, rect, local)
                if key == 'consumablesPanel':
                    regions = tuple(area for _, area in self.widget_geometry(key, widget))
                    if not regions:
                        widget.restore()
                        continue
                else:
                    regions = tuple(self.region_bounds(key, clip, self.stage) for clip in clips)
                rect = enclosing_rect(regions)
                if key in ('minimap', 'consumablesPanel') and not self.intersects_screen(rect):
                    widget.restore()
                    continue
            if self.intersects_screen(rect):
                if key == 'battleMessenger':
                    regions = self.chat_hit_regions(widget)
                    if not regions:
                        continue
                self.bounds[key] = rect
                self.hit_bounds[key] = (rect,) if key in ('postmortemPanel', 'consumablesPanel') else regions

    def parent_region(self, key, widget, clips, stage_rect):
        if key == 'consumablesPanel':
            return stage_rect
        parent = widget.clip.parent
        if parent is None:
            return stage_rect
        return enclosing_rect([self.region_bounds(key, clip, parent) for clip in clips])

    def pointer(self):
        position = GUI.mcursor().position
        sw, sh = self.screen
        return ((float(position[0]) + 1) * sw / 2, (1 - float(position[1])) * sh / 2)

    def pick(self, point):
        x, y = point
        focused = self.bounds.get(self.focus_key)
        if focused is not None and layout.inside(focused, x, y, layout.HIT_EDGE):
            grip = layout.edges(focused, x, y)
            if grip != (0, 0):
                return self.focus_key, focused, grip
        hits = []
        for key, rect in self.bounds.items():
            if any(layout.inside(region, x, y, layout.HIT_EDGE)
                   for region in self.hit_bounds.get(key, (rect,))):
                grip = layout.edges(rect, x, y)
                hits.append((grip == (0, 0), rect[2] * rect[3], key, rect, grip))
        if not hits:
            return None, None, (0, 0)
        _, _, key, rect, grip = min(hits)
        return key, rect, grip

    def pick_team(self, point):
        for team in layout.TEAMS:
            rect = self.bounds.get(team)
            if rect is not None and layout.inside(rect, point[0], point[1], layout.HIT_EDGE):
                return team

    def update_drag(self, point):
        if self.drag is None:
            return
        drag = self.drag
        dx, dy = point[0] - drag['start'][0], point[1] - drag['start'][1]
        if abs(dx) < 1 and abs(dy) < 1 and drag['target'] == drag['rect']:
            return
        minimum = 38 if drag['mode'] == 'top' else layout.MIN_EDGE
        maximum = None
        if drag['key'] in ('postmortemPanel', 'postmortemInfoPage'):
            maximum = tuple(int(size * limit) for size, limit in zip(self.screen, layout.POSTMORTEM_LIMIT))
        drag['target'] = layout.adjust(drag['rect'], drag['grip'], dx, dy, self.screen, minimum, maximum)

    def end_drag(self, save):
        drag = self.drag
        self.drag = None
        if drag is None:
            return
        key = drag['key']
        if save and drag['target'] != drag['rect']:
            changes = {name: dict(value) for name, value in self.state['elements'].items()}
            changes.setdefault(key, {})[drag['mode']] = layout.normalize(drag['target'], self.screen)
            if self.save(dict(self.state, elements=changes)):
                return
        if drag['mode'] == layout.normal_mode(key) and self.preset(key, drag['mode']) is None:
            self.widgets[key].restore()
        self.next_layout = 0

    def save(self, state):
        try:
            layout.write_json(layout.PATH, state)
        except (IOError, OSError, ValueError):
            LOGGER.exception('Cannot save battle HUD layout')
            return
        self.state = state
        self.next_layout = 0
        return True

    def toggle_top(self, key):
        current = self.state['top']
        self.save(dict(self.state, top=[team for team in current if team != key]
                       if key in current else current + [key]))

    def enter(self):
        if not self.active:
            self.page.app.enterGuiControlMode(CONSUMER, cursorVisible=True, enableAiming=False)
            self.active = True
            root = self.page.flashObject
            if root is not None:
                self.flash_mouse = (root, root.mouseChildren, root.mouseEnabled)
                root.mouseChildren = False
                root.mouseEnabled = False
            self.refresh_widgets()
            self.next_scan = self.next_layout = 0

    def leave(self, save):
        if self.active:
            self.active = False
            try:
                self.end_drag(save)
            finally:
                self.focus_key = None
                self.editor.close()
                if self.flash_mouse is not None:
                    root, children, enabled = self.flash_mouse
                    self.flash_mouse = None
                    root.mouseChildren = children
                    root.mouseEnabled = enabled
                self.page.app.leaveGuiControlMode(CONSUMER)

    def input(self, event):
        return self.handle_key(event.key, event.isKeyDown())

    def handle_key(self, key, down):
        if self.edit_key is not None and key == self.edit_key:
            if down and not self.wants_alt and self.can_edit():
                self.wants_alt = True
                self.enter()
                return True
            if self.wants_alt:
                if not down:
                    self.wants_alt = False
                    self.leave(True)
                return True
        if not down and key in self.block_release:
            self.block_release.discard(key)
            self.buttons_down.discard(key)
            if key == Keys.KEY_LEFTMOUSE and self.drag is not None:
                self.update_drag(self.pointer())
                self.end_drag(True)
            return True
        if not self.active:
            return False
        if key == Keys.KEY_ESCAPE and down:
            self.leave(False)
            return True
        if key not in MOUSE_BUTTONS:
            return False
        if down:
            if key in self.buttons_down:
                return True
            self.buttons_down.add(key)
            self.block_release.add(key)
            point = self.pointer()
            if self.drag is not None:
                return True
            if key == Keys.KEY_LEFTMOUSE and self.editor.menu_hit(point):
                team = self.editor.team
                self.editor.close_menu()
                self.toggle_top(team)
                return True
            self.editor.close_menu()
            self.render_layout()
            if key == Keys.KEY_RIGHTMOUSE:
                team = self.pick_team(point)
                if team is not None:
                    self.editor.open_menu(team, team in self.state['top'], point, self.screen, self.bounds[team])
            else:
                target, rect, grip = self.pick(point)
                if target is not None:
                    mode = 'top' if target in self.native else layout.normal_mode(target)
                    self.drag = dict(key=target, mode=mode, rect=rect, target=rect, grip=grip, start=point)
        return True

    def can_edit(self):
        return (self.screen is not None and self.page.isGuiVisible() and not self.page._isBattleLoading
                and not self.page._fsToggling
                and not self.page.app.hasGuiControlModeConsumers('battleLoading', 'radialMenu', 'fullStats'))

    def sync_edit_key(self, focused):
        if focused and self.edit_key is not None:
            held = BigWorld.isKeyDown(self.edit_key)
            if self.wants_alt != held:
                self.handle_key(self.edit_key, held)

    def tick(self):
        self.timer = None
        try:
            self.update()
            self.last_error = None
        except Exception as error:
            self.next_scan = 0
            signature = (type(error), str(error))
            if signature != self.last_error:
                self.last_error = signature
                LOGGER.exception('Battle HUD update failed')
        finally:
            self.timer = BigWorld.callback(0.016 if self.active else 0.08, self.tick)

    def update(self):
        now = BigWorld.time()
        if now >= self.next_scan:
            self.refresh_widgets()
            self.next_scan = now + 0.8
        if self.stage is None:
            return
        focused = GUI.mcursor().inFocus
        if self.active and (not focused or not self.can_edit()):
            self.leave(False)
        self.sync_edit_key(focused)
        if self.active:
            for key in MOUSE_BUTTONS:
                down = BigWorld.isKeyDown(key)
                if down != (key in self.buttons_down):
                    self.handle_key(key, down)
        scale = interface_scale()
        screen = tuple(float(side) / scale for side in GUI.screenResolution()[:2])
        if min(screen) <= 0:
            return
        if self.screen != screen:
            self.end_drag(False)
            self.editor.close_menu()
            self.screen = screen
            self.next_layout = 0
        if self.active:
            point = self.pointer()
            self.update_drag(point)
        if (self.active or self.state['elements'] or self.state['top']) and now >= self.next_layout:
            self.render_layout()
            self.next_layout = now + (0.0 if self.active else 0.08)
        if self.active:
            if self.drag is not None:
                rect, grip = self.drag['target'], self.drag['grip']
            else:
                self.focus_key, rect, grip = self.pick(point)
            self.editor.highlight(rect, screen, grip)
            self.editor.resize_cursor((0, 0) if self.editor.menu_rect is not None else grip, point, screen)

    def close(self):
        if self.timer is not None:
            BigWorld.cancelCallback(self.timer)
            self.timer = None
        try:
            self.leave(True)
            for widget in self.widgets.values():
                widget.restore()
            for key, strip in self.strips.items():
                self.restore_list(key)
                strip.close()
        finally:
            self.editor.close()

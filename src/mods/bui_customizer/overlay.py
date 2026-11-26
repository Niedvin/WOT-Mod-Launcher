# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import math
import unicodedata

import GUI

from .layout import TEAMS, inside


PALETTE = 'gui/maps/bui_customizer/{}.png'
CONTOUR = 'gui/maps/icons/vehicle/contour/{}.png'
ROMAN = ('', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI')
CYRILLIC = 'АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯЁ'
LATIN = 'A B V H G D E Ye Zh Z I I Yi Y K L M N O P R S T U F Kh Ts Ch Sh Shch - Y - E Yu Ya Yo'.split()
ROSTER_GLYPHS = {ord(letter): value.replace('-', '')
                 for alphabet, replacements in ((CYRILLIC, LATIN), (CYRILLIC.lower(), [item.lower() for item in LATIN]))
                 for letter, value in zip(alphabet, replacements)}


def roster_name(name):
    # WoT's Arial 12 atlas lacks Cyrillic and Latin Extended-A glyphs — 2026-11-19
    value = name.translate(ROSTER_GLYPHS).replace('’', "'")
    return unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii').strip()


class Surface(object):
    def __init__(self, component, depth, parent=None):
        self.component = component
        self.component.horizontalAnchor = GUI.Simple.eHAnchor.LEFT
        self.component.verticalAnchor = GUI.Simple.eVAnchor.TOP
        self.depth = depth
        self.rect = None
        self.parent = parent
        if parent is None:
            GUI.addRoot(component)
        else:
            parent.component.addChild(component)

    def place(self, rect, screen, size=True):
        parent_rect = self.parent.rect[0] if self.parent is not None else None
        value = rect, screen, parent_rect
        if self.rect == value:
            return
        self.rect = value
        x, y, w, h = rect
        sw, sh = screen
        if parent_rect is None:
            self.component.position = (2.0 * x / sw - 1, 1 - 2.0 * y / sh, self.depth)
        else:
            left, top, width, height = parent_rect
            self.component.position = ((2 * (x - left) - width) / sw,
                                       (height - 2 * (y - top)) / sh, self.depth)
        if size:
            self.component.size = (2.0 * w / sw, 2.0 * h / sh)

    def close(self):
        if self.parent is None:
            GUI.delRoot(self.component)
        else:
            self.parent.component.delChild(self.component)


def quad(texture, depth, parent=None):
    component = GUI.Simple(str(texture))
    component.materialFX = GUI.Simple.eMaterialFX.BLEND
    return Surface(component, depth, parent)


def label(text, depth, parent=None):
    component = GUI.Text('')
    component.font = 'hpmp_panel.font'
    component.colour = (255, 249, 229, 255)
    component.text = text
    return Surface(component, depth, parent)


class TankCard(object):
    def __init__(self, info, team, parent=None):
        _, name, tier, icon, _ = info
        self.name = roster_name(name) or icon.split('-', 1)[-1].replace('_', ' ')
        self.tier = ROMAN[tier] if 0 < tier < len(ROMAN) else str(tier) if tier else ''
        self.background = quad(PALETTE.format('card'), 0.09, parent)
        self.health = quad(PALETTE.format(team), 0.08, parent)
        self.icon = quad(CONTOUR.format(icon), 0.07, parent)
        self.nameplate = label('', 0.06, parent)
        self.level = label(self.tier, 0.06, parent)
        self.parts = (self.background, self.health, self.icon, self.nameplate, self.level)

    def render(self, rect, screen, hp):
        x, y, w, h = rect
        self.background.place(rect, screen)
        self.health.component.visible = hp is not None and hp > 0
        if self.health.component.visible:
            self.health.place((x, y, w * hp, h), screen)
        self.icon.component.colour = (255, 255, 255, 105 if hp == 0 else 255)
        icon_h = min(18, h * 0.46)
        tier_width = self.level.component.width * screen[0] / 2.0
        icon_room = max(4, w - tier_width - 7)
        icon_w = min(icon_room, icon_h * 3.2)
        self.icon.place((x + (icon_room - icon_w) / 2 + 2, y + 1, icon_w, icon_h), screen)
        self.level.place((x + max(2, w - tier_width - 3), y + 1, 0, 0), screen, size=False)
        component = self.nameplate.component
        name = self.name
        max_width = 2.0 * (w - 4) / screen[0]
        component.text = name
        while len(name) > 1 and component.width > max_width:
            name = name[:-1].rstrip()
            component.text = name + '.'
        text_width = component.width * screen[0] / 2.0
        self.nameplate.place((x + max(2, (w - text_width) / 2), y + icon_h + 1, 0, 0), screen, size=False)
        component.colour = (210, 218, 209, 150) if hp == 0 else (255, 249, 229, 255)
        self.level.component.colour = component.colour

    def show(self, visible):
        for part in self.parts:
            part.component.visible = visible
        if visible:
            self.health.component.visible = False

    def close(self):
        for part in self.parts:
            part.close()


class TeamStrip(object):
    def __init__(self, team):
        self.team = team
        self.cards = []
        self.spec = ()
        self.frame = None
        self.visible = False
        self.window = None

    def default_rect(self, screen, count):
        sw, sh = screen
        width = max(80, (sw - max(220, sw * 0.28)) / 2.0 - 16)
        columns = max(1, min(count, int(width / 46)))
        rows = int(math.ceil(float(count) / columns))
        return (8 if self.team == 'allies' else sw - width - 8, 49, width, max(1, rows) * 38)

    def update(self, rows, rect, screen, viewport=None):
        spec = tuple(row[:4] for row in rows)
        if spec != self.spec or (viewport is None) != (self.window is None):
            self.close()
            self.spec = spec
            if viewport is not None:
                self.window = Surface(GUI.Window(), 0.09)
            self.cards = [TankCard(row, self.team, self.window) for row in rows]
        if not self.cards:
            return
        frame = rect, screen, tuple(row[4] for row in rows), viewport
        if frame == self.frame and self.visible:
            return
        if self.window is not None:
            self.window.place(viewport, screen)
        columns = max(1, min(len(rows), int(rect[2] / 46)))
        row_count = int(math.ceil(float(len(rows)) / columns))
        cell_w = rect[2] / columns
        cell_h = rect[3] / row_count
        x, y = rect[:2]
        for i, (card, row) in enumerate(zip(self.cards, rows)):
            if not self.visible:
                card.show(True)
            card.render((x + (i % columns) * cell_w, y + (i // columns) * cell_h,
                         max(4, cell_w - 2), max(4, cell_h - 2)), screen, row[4])
        self.frame = frame
        self.visible = True

    def hide(self):
        if self.visible:
            for card in self.cards:
                card.show(False)
        self.visible = False

    def close(self):
        for card in self.cards:
            card.close()
        if self.window is not None:
            self.window.close()
            self.window = None
        self.cards = []
        self.spec = ()
        self.frame = None
        self.visible = False


class EditorOverlay(object):
    def __init__(self):
        self.outline = []
        self.handles = []
        self.button = []
        self.menu_rows = []
        self.menu_rect = None
        self.menu_key = None
        self.highlight_rect = None
        self.resize_icon = None
        self.resize_direction = None

    def highlight(self, rect, screen, grip):
        state = (rect, screen, grip)
        if self.highlight_rect == state:
            return
        self.highlight_rect = state
        if rect is None:
            for line in self.outline + self.handles:
                line.component.visible = False
            return
        if not self.outline:
            self.outline = [quad(PALETTE.format('focus'), 0.04) for _ in range(4)]
            self.handles = [quad(PALETTE.format('focus'), 0.039) for _ in range(8)]
        x, y, w, h = rect
        horizontal, vertical = grip
        thickness = [4 if active else 2 for active in
                     (vertical < 0, vertical > 0, horizontal < 0, horizontal > 0)]
        a, b, c, d = thickness
        lines = ((x, y, w, a), (x, y + h - b, w, b), (x, y, c, h), (x + w - d, y, d, h))
        for line, position in zip(self.outline, lines):
            line.component.visible = True
            line.place(position, screen)
        positions = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
        for handle, (side_x, side_y) in zip(self.handles, positions):
            size = 11 if grip == (side_x, side_y) else 7
            hx = x + (side_x + 1) * w / 2 - size / 2.0
            hy = y + (side_y + 1) * h / 2 - size / 2.0
            handle.component.visible = (-size / 2.0 <= hx <= screen[0] - size / 2.0 and
                                        -size / 2.0 <= hy <= screen[1] - size / 2.0)
            if handle.component.visible:
                handle.place((hx, hy, size, size), screen)

    def resize_cursor(self, grip, pointer, screen):
        horizontal, vertical = grip
        if not horizontal and not vertical:
            if self.resize_icon is not None:
                self.resize_icon.component.visible = False
            return
        if horizontal and vertical:
            direction = 'diagonal_down' if horizontal == vertical else 'diagonal_up'
        else:
            direction = 'horizontal' if horizontal else 'vertical'
        if direction != self.resize_direction:
            if self.resize_icon is not None:
                self.resize_icon.close()
            self.resize_icon = quad(PALETTE.format('resize_' + direction), 0.01)
            self.resize_direction = direction
        size = 25
        x, y = pointer
        sw, sh = screen
        left, right = x - size - 8, x + 14
        above, below = y - size - 8, y + 12
        left = left if (horizontal < 0 and left >= 0) or right + size > sw else right
        top = above if (vertical < 0 and above >= 0) or below + size > sh else below
        self.resize_icon.component.visible = True
        self.resize_icon.place((max(0, left), max(0, top), size, size), screen)

    def open_menu(self, key, top, pointer, screen, anchor):
        self.close_menu()
        x, y = pointer
        sw, sh = screen
        items = [('reset', 'menu_reset')]
        if key in TEAMS:
            items.insert(0, ('dock', 'menu_side' if top else 'menu_top'))
        width, height = min(288, sw), min(36 * len(items), sh)
        left, above = anchor[0] - width - 8, anchor[1] - height - 8
        right, below = anchor[0] + anchor[2] + 8, anchor[1] + anchor[3] + 8
        room_right = right + width <= sw
        room_left = left >= 0
        if key in TEAMS:
            if top or not (room_left or room_right):
                y = below if below + height <= sh else above
            elif room_right and (not room_left or pointer[0] < sw / 2):
                x = right
            else:
                x = left
        x = max(0, min(x, sw - width))
        y = max(0, min(y, sh - height))
        self.menu_key = key
        self.menu_rect = (x, y, width, height)
        row_height = height / float(len(items))
        for index, (action, texture) in enumerate(items):
            rect = (x, y + index * row_height, width, row_height)
            surface = quad(PALETTE.format(texture), 0.025)
            surface.place(rect, screen)
            self.button.append(surface)
            self.menu_rows.append((action, rect))

    def menu_hit(self, pointer):
        return next((action for action, rect in self.menu_rows if inside(rect, *pointer)), None)

    def close_menu(self):
        for component in self.button:
            component.close()
        self.button = []
        self.menu_rows = []
        self.menu_key = None
        self.menu_rect = None

    def close(self):
        self.close_menu()
        if self.resize_icon is not None:
            self.resize_icon.close()
            self.resize_icon = None
            self.resize_direction = None
        for line in self.outline + self.handles:
            line.close()
        self.outline = []
        self.handles = []
        self.highlight_rect = None

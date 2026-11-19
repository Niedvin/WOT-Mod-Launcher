from __future__ import unicode_literals

from collections import namedtuple
import sys
import types
import unittest


module_names = ('BigWorld', 'GUI', 'Keys', 'constants', 'gui', 'gui.ua_mod_manager', 'gui.ua_mod_manager.manager',
                'gui.ua_mod_manager.bindings', 'gui.ua_bui', 'gui.ua_bui.battle')
original_modules = {name: sys.modules.get(name) for name in module_names}
try:
    for name in module_names:
        sys.modules[name] = types.ModuleType(str(name))
    sys.modules['Keys'].KEY_LEFTMOUSE = 1
    sys.modules['Keys'].KEY_RIGHTMOUSE = 2
    sys.modules['Keys'].KEY_ESCAPE = 3
    sys.modules['gui.ua_mod_manager.manager'].read_json = lambda path: {}
    sys.modules['gui.ua_mod_manager.manager'].write_json = lambda path, state: None
    sys.modules['gui.ua_mod_manager.bindings'].binding_for = lambda identifier, fallback: fallback
    sys.modules['constants'].ARENA_BONUS_TYPE = type(str('Modes'), (), dict(
        REGULAR=1, TRAINING=2, EPIC_RANDOM=24, EVENT_RANDOM=33, COMP7=43, FORT_RUSH=154))

    from . import battle
    from . import layout
    from . import modes
    from . import overlay
    sys.modules['gui.ua_bui'] = sys.modules[__package__]
    sys.modules['gui.ua_bui.battle'] = battle
    from . import entry
finally:
    for name, module in original_modules.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


Bounds = namedtuple('Bounds', 'x y width height')


class Clip(object):
    def __init__(self, parent=None, x=0, y=0, width=0, height=0):
        self.parent = parent
        self.x, self.y = x, y
        self.scaleX = self.scaleY = 1.0
        self.visible = True
        self.alpha = 1.0
        self.width, self.height = width, height
        self.children = []
        if parent is not None:
            parent.children.append(self)

    @property
    def numChildren(self):
        return len(self.children)

    def getChildAt(self, index):
        return self.children[index]

    def getBounds(self, relative_to):
        x = y = 0.0
        width, height = self.width, self.height
        clip = self
        while clip is not relative_to:
            x = clip.x + x * clip.scaleX
            y = clip.y + y * clip.scaleY
            width *= clip.scaleX
            height *= clip.scaleY
            clip = clip.parent
        return Bounds(x, y, width, height)


class Page(object):
    _isBattleLoading = False
    _isInPostmortem = False

    def isGuiVisible(self):
        return True

    def as_getComponentsVisibilityS(self):
        return self.aliases


class KeyEvent(object):
    def __init__(self, key, down):
        self.key = key
        self.down = down

    def isMouseButton(self):
        return self.key in battle.MOUSE_BUTTONS

    def isKeyDown(self):
        return self.down


class BattleLayoutTest(unittest.TestCase):
    def setUp(self):
        self.hud = battle.BattleLayout(Page(), None)
        self.hud.stage = Clip()
        self.hud.screen = (1000.0, 800.0)
        self.hud.page.aliases = self.hud.native_visible

    def add(self, key, x=0, y=0, width=0, height=0, draw_clip=None):
        clip = Clip(self.hud.stage, x, y, width, height)
        self.hud.add_widget(key, clip, draw_clip)
        self.hud.native_visible.add(key)
        return clip

    def render(self):
        self.hud.bounds.clear()
        self.hud.hit_bounds.clear()
        self.hud.render_widgets(True)

    def test_registered_hidden_contents_and_empty_labels_are_not_selectable(self):
        postmortem = self.add('postmortemPanel', width=1000, height=400)
        Clip(postmortem, width=200, height=200)
        sixth_sense = self.add('sixthSense', x=100, y=100, width=100, height=100)
        sixth_sense.currentFrame = 1
        ribbons = self.add('ribbonsPanel', x=400, y=200, width=400, height=400)
        hidden_parent = Clip(ribbons)
        hidden_parent.visible = 0
        Clip(hidden_parent, width=300, height=200)
        empty = Clip(ribbons, width=200, height=100)
        empty.text = '  '
        self.render()
        self.assertEqual(self.hud.bounds, {})

        sixth_sense.currentFrame = 2
        text = Clip(ribbons, x=40, y=30, width=45, height=24)
        text.text = '\u0428\u043a\u043e\u0434\u0430'
        self.render()
        self.assertEqual(self.hud.bounds['ribbonsPanel'], (440, 230, 45, 24))
        self.assertEqual(self.hud.pick((600, 350))[0], None)
        self.assertEqual(self.hud.pick((164, 164))[0], 'sixthSense')

    def test_minimap_recovers_after_native_move_and_respects_native_visibility(self):
        minimap = self.add('minimap', x=1200, y=600)
        mask = Clip(minimap, width=200, height=200)
        mask.visible = False
        self.hud.add_widget('minimap', minimap, mask)
        wanted = (730, 520, 270, 270)
        self.hud.state['elements']['minimap'] = {'normal': layout.normalize(wanted, self.hud.screen)}
        self.render()
        for actual, expected in zip(self.hud.bounds['minimap'], wanted):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(minimap.scaleX, 1.35)

        minimap.x, minimap.y = 1300, 550
        self.render()
        for actual, expected in zip(self.hud.bounds['minimap'], wanted):
            self.assertAlmostEqual(actual, expected)
        minimap.visible = False
        self.render()
        self.assertNotIn('minimap', self.hud.bounds)
        self.assertFalse(minimap.visible)

    def test_empty_chat_space_cannot_be_picked(self):
        chat = self.add('battleMessenger', y=250, width=325, height=390)
        hidden = Clip(chat, x=5, y=20, width=300, height=350)
        hidden.visible = False
        line = Clip(chat, x=8, y=367, width=95, height=17)
        line.text = 'Battle message'
        self.render()
        self.assertIsNone(self.hud.pick((155, 400))[0])
        self.assertEqual(self.hud.pick((50, 625))[0], 'battleMessenger')
        line.text = ''
        self.render()
        self.assertNotIn('battleMessenger', self.hud.bounds)

    def test_distant_transient_children_do_not_make_a_fullscreen_target(self):
        ribbon = self.add('ribbonsPanel')
        Clip(ribbon, x=8, y=10, width=43, height=28)
        Clip(ribbon, x=920, y=740, width=67, height=39)
        self.render()
        self.assertNotIn('ribbonsPanel', self.hud.bounds)

    def test_reset_actions_keep_unrelated_layout_and_have_two_categories(self):
        read, write = layout.read_json, layout.write_json
        data = {'elements': {'minimap': {'normal': [0.75, 0.7, 0.25, 0.3]},
                             'sixthSense': {'normal': [0.4, 0.1, 0.1, 0.1]}},
                'top': ['enemies']}
        written = {}
        layout.read_json = lambda path: data
        layout.write_json = lambda path, state: written.update(state)
        try:
            fields = layout.actions('test-layout.json')
            self.assertEqual(len([field for field in fields if field['kind'] == 'section']), 2)
            self.assertTrue(next(field for field in fields if field.get('key') == 'allies')['disabled'])
            self.assertFalse(next(field for field in fields if field.get('key') == 'minimap')['disabled'])
            layout.reset('minimap', 'test-layout.json')
            self.assertEqual(written['top'], ['enemies'])
            self.assertEqual(set(written['elements']), {'sixthSense'})
            layout.reset('*', 'test-layout.json')
            self.assertEqual(written, {'elements': {}, 'top': []})
        finally:
            layout.read_json, layout.write_json = read, write

    def test_oversized_legacy_postmortem_preset_is_ignored_and_visible_edges_resize(self):
        read = layout.read_json
        layout.read_json = lambda path: {'elements': {
            'postmortemPanel': {'normal': [0, 0.3263889, 1.0, 0.6736111]},
            'minimap': {'normal': [0.75, 0.75, 0.25, 0.25]},
        }}
        try:
            self.hud.state = layout.load()
        finally:
            layout.read_json = read
        self.assertEqual(self.hud.state['elements']['postmortemPanel'], {})
        self.assertIn('normal', self.hud.state['elements']['minimap'])
        self.hud.page._isInPostmortem = True
        panel = self.add('postmortemPanel', x=350, y=550)
        Clip(panel, width=100, height=25)
        Clip(panel, x=190, y=25, width=110, height=25)
        self.render()
        key, rect, grip = self.hud.pick((620, 550))
        self.assertEqual((key, rect, grip), ('postmortemPanel', (350, 550, 300, 50), (0, -1)))
        self.hud.drag = dict(key=key, mode='normal', rect=rect, target=rect, grip=grip, start=(620, 550))
        self.hud.update_drag((620, 0))
        self.assertEqual(self.hud.drag['target'], (350, 264, 300, 336))

    def test_battle_allowlist_rejects_events_even_on_the_same_page(self):
        self.assertEqual(modes.SUPPORTED_MODES, set((1, 2, 24)))
        player = type(str('Player'), (), {})()
        modes.BigWorld.player = lambda: player
        for bonus_type in (None, 0, 33, 43, 154, 999):
            player.arenaBonusType = bonus_type
            self.assertFalse(modes.is_supported_battle())
            self.assertEqual('original', entry.populate(lambda page: 'original', self.hud.page))
            self.assertIsNone(entry._session)
        player.arenaBonusType = 1
        self.assertTrue(modes.is_supported_battle())

    def test_roster_right_click_is_consumed_before_native_gui_only_in_edit_mode(self):
        calls = []
        editor = self.hud.editor
        editor.open_menu = lambda team, top, point, screen, anchor: calls.append((team, top))
        self.hud.bounds['allies'] = (0, 40, 200, 250)
        self.hud.bounds['debugPanel'] = (0, 40, 50, 100)
        self.hud.pointer = lambda: (15, 75)
        self.hud.render_layout = lambda: None
        self.hud.enter = lambda: setattr(self.hud, 'active', True)
        self.hud.can_edit = lambda: True
        self.hud.edit_key = 184
        held = set()
        battle.BigWorld.isKeyDown = held.__contains__
        entry.GUI.mcursor = lambda: type(str('Cursor'), (), {'inFocus': True})()

        def native(event):
            calls.append('native')
            return True

        entry._session = self.hud
        try:
            click = KeyEvent(battle.Keys.KEY_RIGHTMOUSE, True)
            release = KeyEvent(battle.Keys.KEY_RIGHTMOUSE, False)
            self.assertTrue(entry.gui_key_event(native, click))
            self.assertEqual(calls, ['native'])
            held.add(self.hud.edit_key)
            self.assertTrue(entry.gui_key_event(native, click))
            self.assertTrue(entry.gui_key_event(native, release))
            self.assertEqual(calls, ['native', ('allies', False)])
            self.hud.state['top'] = ['allies']
            self.hud.bounds['allies'] = (350, 20, 420, 60)
            self.hud.pointer = lambda: (525, 55)
            self.assertTrue(entry.gui_key_event(native, click))
            self.assertTrue(entry.gui_key_event(native, release))
            self.assertEqual(calls[-1], ('allies', True))
            self.assertEqual(calls.count('native'), 1)
        finally:
            entry._session = None

    def test_focused_edge_resizes_over_other_widget_and_stays_at_screen_edge(self):
        panel = self.add('damagePanel', x=800, y=600, width=200, height=200)
        self.add('debugPanel', x=780, y=670, width=80, height=60)
        self.render()
        self.hud.focus_key = 'damagePanel'
        self.hud.active = True
        self.hud.pointer = lambda: (806, 700)
        self.hud.bounds.clear()
        self.assertTrue(self.hud.handle_key(battle.Keys.KEY_LEFTMOUSE, True))
        self.assertEqual(self.hud.drag['grip'], (-1, 0))
        self.hud.pointer = lambda: (766, 700)
        self.hud.update_drag(self.hud.pointer())
        self.render()
        self.assertEqual(self.hud.bounds['damagePanel'], (760, 600, 240, 200))
        self.assertAlmostEqual(panel.scaleX, 1.2)
        self.assertTrue(self.hud.handle_key(battle.Keys.KEY_LEFTMOUSE, False))
        self.assertEqual(self.hud.state['elements']['damagePanel']['normal'], [0.76, 0.75, 0.24, 0.25])

    def test_resize_indicator_tracks_grip_and_stays_on_screen(self):
        created = []
        old_quad = overlay.quad

        def quad(texture, depth):
            surface = Clip()
            surface.component = surface
            surface.close = lambda: setattr(surface, 'closed', True)
            surface.place = lambda rect, screen: setattr(surface, 'rect', rect)
            created.append((texture, surface))
            return surface

        overlay.quad = quad
        try:
            editor = self.hud.editor
            editor.resize_cursor((-1, 1), (995, 795), self.hud.screen)
            name, icon = created[-1]
            self.assertTrue(name.endswith('resize_diagonal_up.png'))
            self.assertLess(icon.rect[0] + icon.rect[2], self.hud.screen[0])
            self.assertLess(icon.rect[1] + icon.rect[3], self.hud.screen[1])
            editor.resize_cursor((1, 0), (500, 500), self.hud.screen)
            self.assertTrue(icon.closed)
            name, icon = created[-1]
            self.assertTrue(name.endswith('resize_horizontal.png'))
            editor.resize_cursor((-1, 0), (420, 400), self.hud.screen)
            self.assertLess(icon.rect[0] + icon.rect[2], 420)
            editor.resize_cursor((0, 0), (500, 500), self.hud.screen)
            self.assertFalse(icon.visible)
            editor.close()
            self.assertTrue(icon.closed)
        finally:
            overlay.quad = old_quad

    def test_roster_menu_uses_drawn_labels_for_both_directions(self):
        textures = []
        original = overlay.quad
        def quad(texture, depth):
            textures.append(texture)
            surface = Clip()
            surface.place = lambda *args: None
            surface.close = lambda: None
            return surface
        overlay.quad = quad
        try:
            editor = self.hud.editor
            editor.open_menu('allies', False, (20, 60), self.hud.screen, (0, 40, 200, 210))
            x, y, w, h = editor.menu_rect
            self.assertGreater(x, 200)
            self.assertTrue(editor.menu_hit((x + 4, y + 4)))
            editor.open_menu('enemies', False, (900, 60), self.hud.screen, (750, 40, 260, 210))
            x, _, w, _ = editor.menu_rect
            self.assertLess(x + w, 750)
            editor.open_menu('allies', True, (20, 60), self.hud.screen, (0, 49, 420, 40))
            self.assertGreater(editor.menu_rect[1], 89)
            self.assertEqual([path.rsplit('/', 1)[-1] for path in textures],
                             ['menu_top.png', 'menu_top.png', 'menu_side.png'])

        finally:
            overlay.quad = original

    def test_roster_label_keeps_vehicle_identity_when_bitmap_lacks_glyphs(self):
        self.assertEqual(overlay.roster_name('\u0406\u0421-7'), 'IS-7')
        self.assertEqual(overlay.roster_name('\u0418\u0421-7'), 'IS-7')
        self.assertEqual(overlay.roster_name('\u041e\u0431. 907'), 'Ob. 907')
        self.assertEqual(overlay.roster_name('\u0160koda T 56'), 'Skoda T 56')

    def test_roster_health_resizes_and_unknown_or_dead_health_hides_fill(self):
        class Part(object):
            def __init__(self, text=''):
                self.component = self
                self.text = text
                self.width = .026
                self.visible = True

            def place(self, rect, screen, size=True):
                self.rect = rect

        make_quad, make_label = overlay.quad, overlay.label
        overlay.quad = lambda texture, depth: Part()
        overlay.label = lambda text, depth: Part(text)
        try:
            card = overlay.TankCard((7, 'Maus', 10, 'germany-G42_Maus', 1.0), 'allies')
            card.render((100, 50, 74, 36), self.hud.screen, .25)
            self.assertEqual(card.health.rect, (100, 50, 18.5, 36))
            self.assertTrue(card.health.visible)
            self.assertEqual(card.nameplate.text, 'Maus')
            self.assertEqual(card.level.text, 'X')
            card.render((100, 50, 74, 36), self.hud.screen, None)
            self.assertFalse(card.health.visible)
            card.render((100, 50, 74, 36), self.hud.screen, 0)
            self.assertFalse(card.health.visible)
            self.assertLess(card.nameplate.colour[3], 255)
        finally:
            overlay.quad, overlay.label = make_quad, make_label


if __name__ == '__main__':
    unittest.main()

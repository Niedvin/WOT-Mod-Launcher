import base64
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

ROOT = Path.cwd()
MEMBER = 'gui/gameface/_dist/production/mono/hangar/main/bundle.js'
NEEDLE = 'navigateTo:e.createCallback(e=>({entry:e}),"onNavigate")'
REPLACE = 'navigateTo:(window.__uaNavigate=e.createCallback(e=>({entry:e}),"onNavigate"))'
CARD_PATTERN = re.compile(
    r'children:\[(?P<jsx>\(0,[$\w]+\.jsx\))\([$\w]+,'
    r'\{vehicle:o,validBP:[$\w]+\(m,p,l\),dimmed:u,statistic:l,selected:t,doubleRow:a\}\)'
)
LIBRARY_IMPORT = re.compile(r'import\{([^{}]+)\}from"\.\./chunks/lib\.js"')
CARD_BUTTON = '''
  (r.className || "").includes("Carousel_card_") && __JSX__(__BUTTON__, {
    className: "uaResearchBtn" + (a ? " uaResearchBtn__double" : ""),
    classNames: {border: "uaResearchBorder", background: "uaResearchBg"},
    type: "button", size: __BUTTON__.sizes.extraSmall, theme: __BUTTON__.themes.secondary,
    autoAlignContent: false, disabled: u, title: "Дослідити",
    onMouseDown: event => event.stopPropagation(),
    onClick: event => {
      event.preventDefault();
      event.stopPropagation();
      if (typeof window.__uaNavigate === "function") window.__uaNavigate("ua.research:" + e);
    },
    children: __JSX__("img", {className: "uaResearchGlyph", src: __UA_ICON__, alt: "", draggable: false})
  }),
'''
INJECTOR = r'''
;(function(){
  if(document.getElementById('uaResearchStyle')){return;}
  var css=document.createElement('style');
  css.id='uaResearchStyle';
  css.textContent='.uaResearchBtn{position:absolute;left:8rem;top:50%;transform:translateY(-50%);z-index:30;width:24rem;min-width:24rem;height:24rem;padding:0;outline:0;pointer-events:auto}.uaResearchBorder{display:none}.uaResearchGlyph{display:block;width:20rem;height:20rem;pointer-events:none}.mediaLarge .uaResearchBtn{width:32rem;min-width:32rem;height:32rem}.mediaLarge .uaResearchGlyph{width:24rem;height:24rem}.mediaExtraLarge .uaResearchBtn{left:12rem}.mediaExtraLarge .uaResearchBtn.uaResearchBtn__double{left:8rem}';
  document.head.appendChild(css);
})();
'''


def game_version():
    return re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', (ROOT / 'version.xml').read_text(encoding='utf-8')).group(1)


def data_image(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Research assets must be PNG')
    return json.dumps('data:image/png;base64,' + base64.b64encode(data).decode('ascii'))


def build():
    with zipfile.ZipFile(ROOT / 'res/packages/gui-part2.pkg') as archive:
        original = archive.read(MEMBER).decode('utf-8')
    cards = list(CARD_PATTERN.finditer(original))
    if original.count(NEEDLE) != 1 or len(cards) != 1:
        raise ValueError('Unsupported hangar bundle: callback or vehicle-card component changed')
    with zipfile.ZipFile(ROOT / 'res/packages/gui-part1.pkg') as archive:
        library = archive.read('gui/gameface/_dist/production/mono/hangar/chunks/lib.js').decode('utf-8')
    export = re.search(r'\bButton\$1 as ([$\w]+)', library)
    imports = LIBRARY_IMPORT.search(original)
    button = re.search(r'(?:^|,)' + re.escape(export[1]) + r' as ([$\w]+)(?:,|$)', imports[1]) if export and imports else None
    if not button:
        raise ValueError('Unsupported native Button export')
    with zipfile.ZipFile(ROOT / 'res/packages/gui-part4.pkg') as archive:
        icon = archive.read('gui/maps/icons/vehPostProgression/tooltips/veh_skill_tree_bonus.png')
    card = cards[0]
    insert_at = card.start('jsx')
    addition = (CARD_BUTTON.replace('__JSX__', card['jsx'])
                .replace('__BUTTON__', button[1])
                .replace('__UA_ICON__', data_image(icon)))
    result = (original[:insert_at] + addition + original[insert_at:]).replace(NEEDLE, REPLACE, 1) + INJECTOR
    assert result.count('className: "uaResearchGlyph"') == 1
    assert 'window.__uaNavigate("ua.research:" + e)' in result
    output = Path(__file__).with_name('out_mono') / 'bundle.js'
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.building.js')
    temporary.write_bytes(result.encode('utf-8'))
    os.replace(temporary, output)
    print('MONO', len(result.encode('utf-8')), hashlib.sha256(output.read_bytes()).hexdigest())
    return output


if __name__ == '__main__':
    build()

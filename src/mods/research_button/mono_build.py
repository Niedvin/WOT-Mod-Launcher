import base64
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MEMBER = 'gui/gameface/_dist/production/mono/hangar/main/bundle.js'
NEEDLE = 'navigateTo:e.createCallback(e=>({entry:e}),"onNavigate")'
REPLACE = 'navigateTo:(window.__uaNavigate=e.createCallback(e=>({entry:e}),"onNavigate"))'
CARD_NEEDLE = 'children:[(0,ti.jsx)(_,{vehicle:o,validBP:un(m,p,l),dimmed:u,statistic:l,selected:t,doubleRow:a})'
CARD_BUTTON = '''children:[(r.className||"").indexOf("Carousel_card_")!==-1&&(0,ti.jsx)("button",{className:u?"uaResearchBtn uaResearchBtn__disabled":"uaResearchBtn",type:"button",disabled:u,title:"\\u0414\\u043e\\u0441\\u043b\\u0456\\u0434\\u0438\\u0442\\u0438",onMouseDown:t=>t.stopPropagation(),onClick:t=>{t.preventDefault();t.stopPropagation();if(typeof window.__uaNavigate==="function"){c.play("click",{target:"vehicle-card",original:t});window.__uaNavigate("ua.research:"+e)}},children:(0,ti.jsxs)(ti.Fragment,{children:[(0,ti.jsx)("img",{className:"uaResearchFrame",src:__UA_FRAME__,alt:"",draggable:!1}),(0,ti.jsx)("img",{className:"uaResearchHover",src:__UA_HOVER__,alt:"",draggable:!1}),(0,ti.jsx)("img",{className:"uaResearchGlyph",src:__UA_ICON__,alt:"",draggable:!1})]})}),(0,ti.jsx)(_,{vehicle:o,validBP:un(m,p,l),dimmed:u,statistic:l,selected:t,doubleRow:a})'''
INJECTOR = r'''
;(function(){
  if(document.getElementById('uaResearchStyle')){return;}
  var css=document.createElement('style');
  css.id='uaResearchStyle';
  css.textContent='.uaResearchBtn{position:absolute;left:4rem;top:50%;transform:translateY(-50%);z-index:30;width:24rem;height:24rem;padding:0;border:0;background:none;cursor:pointer;pointer-events:auto;outline:none}.uaResearchBtn img{position:absolute;display:block;pointer-events:none}.uaResearchFrame{left:0;top:0;width:24rem;height:24rem}.uaResearchHover{left:-3.857rem;top:-3.857rem;width:31.714rem;height:31.714rem;opacity:0}.uaResearchGlyph{left:2rem;top:2rem;width:20rem;height:20rem}.uaResearchBtn:hover .uaResearchHover,.uaResearchBtn:focus .uaResearchHover{opacity:1}.uaResearchBtn:hover .uaResearchFrame,.uaResearchBtn:focus .uaResearchFrame{opacity:0}.uaResearchBtn__disabled{opacity:.45;cursor:default}';
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
    if original.count(NEEDLE) != 1 or original.count(CARD_NEEDLE) != 1:
        raise ValueError('Unsupported hangar bundle: callback or vehicle-card component changed')
    with zipfile.ZipFile(ROOT / 'res/packages/gui-part1.pkg') as archive:
        frame = archive.read('gui/maps/icons/vehicle_hub/modules/small/default.png')
    with zipfile.ZipFile(ROOT / 'res/packages/gui-part3.pkg') as archive:
        hover = archive.read('gui/maps/icons/vehicle_hub/modules/small/hover.png')
    icon = Path(__file__).with_name('research_action.png').read_bytes()
    card = CARD_BUTTON.replace('__UA_FRAME__', data_image(frame)).replace('__UA_HOVER__', data_image(hover)).replace('__UA_ICON__', data_image(icon))
    result = original.replace(NEEDLE, REPLACE, 1).replace(CARD_NEEDLE, card, 1) + INJECTOR
    output = Path(__file__).with_name('out_mono') / 'bundle.js'
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.building.js')
    temporary.write_bytes(result.encode('utf-8'))
    assert result.count('className:"uaResearchGlyph"') == 1
    assert 'window.__uaNavigate("ua.research:"+e)' in result
    os.replace(temporary, output)
    print('MONO', len(result.encode('utf-8')), hashlib.sha256(output.read_bytes()).hexdigest())
    return output


if __name__ == '__main__':
    build()

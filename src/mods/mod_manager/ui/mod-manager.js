(() => {
    const researchId = 'ua.research_button';
    let state = { mods: [], open: false };
    let selected = '';
    let filter = '';
    let adapter;
    let pending = null;
    let request = 0;
    let timer;
    let overlay;
    let list;
    let listScroll;
    let detail;
    let detailScroll;
    let restart;
    let summary;
    let status;
    let search;
    let lastActive;
    let filterTab = 'all';
    let choiceKey = '';

    const element = (tag, className, text) => {
        const node = document.createElement(tag);
        node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    };

    const button = (text, className, action) => {
        const control = element('button', className, text);
        control.type = 'button';
        control.addEventListener('click', action);
        return control;
    };

    function send(action, data) {
        if (pending !== null && (action === 'change' || action === 'restart')) return;
        const id = ++request;
        try {
            if (action === 'change') {
                pending = id;
                setStatus('Збереження…', false);
                timer = setTimeout(() => {
                    pending = null;
                    setStatus('Гра не підтвердила зміну.', true);
                }, 3500);
            }
            adapter(Object.assign({ action, request: id }, data));
        } catch (error) {
            pending = null;
            clearTimeout(timer);
            setStatus('Зв’язок із грою втрачено.', true);
        }
    }

    function change(mod, key, value) {
        send('change', { id: mod.id, key, value: JSON.stringify(value) });
    }

    function setStatus(message, error) {
        status.textContent = message;
        status.classList.toggle('uamm-error', !!error);
    }

    function scrollPane(parent, name) {
        const viewport = element('div', 'uamm-' + name + ' uamm-scroll');
        const content = element('div', 'uamm-scroll-content');
        const track = element('div', 'uamm-track');
        const thumb = element('div', 'uamm-thumb');
        let offset = 0;
        let drag = null;
        let limit = 0;
        let travel = 0;
        viewport.appendChild(content);
        track.appendChild(thumb);
        viewport.appendChild(track);
        parent.appendChild(viewport);
        function position(value) {
            const height = viewport.clientHeight;
            const total = Math.max(content.offsetHeight, content.scrollHeight);
            limit = Math.max(0, total - height);
            offset = Math.max(0, Math.min(limit, value));
            content.style.transform = 'translateY(' + (-offset) + 'px)';
            track.classList.toggle('uamm-hidden', !limit);
            thumb.style.height = Math.max(8, 100 * height / (total || 1)) + '%';
            travel = Math.max(0, track.clientHeight - thumb.offsetHeight);
            thumb.style.top = (limit ? offset / limit * travel : 0) + 'px';
        }
        viewport.addEventListener('wheel', event => {
            const delta = event.deltaY || -event.wheelDelta || 0;
            if (!delta) return;
            event.preventDefault();
            event.stopPropagation();
            // Gameface wheel-down emits negative deltaY in line-sized units — 2026-11-18
            const pixels = window.viewEnv ? -delta * 18 : (event.deltaMode === 1 ? delta * 18 : delta);
            position(offset + Math.max(-150, Math.min(pixels, 150)));
        }, { passive: false });
        function stopDrag() {
            if (!drag) return;
            drag = null;
            track.classList.remove('uamm-dragging');
        }
        track.addEventListener('mousedown', event => {
            if (event.button !== 0 || !travel) return;
            event.preventDefault();
            event.stopPropagation();
            const insideThumb = event.target === thumb;
            if (!insideThumb) {
                const y = event.clientY - track.getBoundingClientRect().top - thumb.offsetHeight / 2;
                position(limit * y / travel);
            }
            drag = { y: event.clientY, offset };
            track.classList.add('uamm-dragging');
        });
        window.addEventListener('mousemove', event => {
            if (drag && travel) position(drag.offset + (event.clientY - drag.y) * limit / travel);
        }, true);
        window.addEventListener('mouseup', stopDrag, true);
        window.addEventListener('blur', stopDrag);
        viewport.addEventListener('focusin', event => {
            const windowRect = viewport.getBoundingClientRect();
            const target = event.target.getBoundingClientRect();
            if (target.bottom > windowRect.bottom) position(offset + target.bottom - windowRect.bottom);
            if (target.top < windowRect.top) position(offset + target.top - windowRect.top);
        });
        return { content, reset: () => position(0), refresh: () => position(offset) };
    }

    const keyboardCodes = {
        AltLeft: 'LALT', AltRight: 'RALT', ControlLeft: 'LCONTROL', ControlRight: 'RCONTROL',
        ShiftLeft: 'LSHIFT', ShiftRight: 'RSHIFT', MetaLeft: 'LWIN', MetaRight: 'RWIN',
        Enter: 'RETURN', Escape: 'ESCAPE', ArrowUp: 'UPARROW', ArrowLeft: 'LEFTARROW',
        ArrowRight: 'RIGHTARROW', ArrowDown: 'DOWNARROW', PageUp: 'PGUP', PageDown: 'PGDN',
        BracketLeft: 'LBRACKET', BracketRight: 'RBRACKET', Equal: 'EQUALS', Quote: 'APOSTROPHE',
        Backquote: 'GRAVE', IntlBackslash: 'OEM_102', ContextMenu: 'APPS', ScrollLock: 'SCROLL',
        PrintScreen: 'SYSRQ', NumpadEnter: 'NUMPADENTER', NumpadMultiply: 'NUMPADSTAR',
        NumpadAdd: 'ADD', NumpadSubtract: 'NUMPADMINUS', NumpadDivide: 'NUMPADSLASH',
        NumpadDecimal: 'NUMPADPERIOD', NumpadEqual: 'NUMPADEQUALS',
    };

    function bindingKey(event) {
        const code = event.code;
        if (keyboardCodes[code]) return keyboardCodes[code];
        if (typeof code === 'string' && /^(Key[A-Z]|Digit[0-9]|F[0-9]+|Numpad[0-9]|Space|Backspace|Tab|CapsLock|NumLock|Home|End|Insert|Delete|Pause|Semicolon|Comma|Period|Minus|Slash|Backslash)$/.test(code)) {
            return code.replace(/^(Key|Digit)/, '').toUpperCase();
        }
        const vk = event.keyCode || event.which;
        if (vk >= 65 && vk <= 90 || vk >= 48 && vk <= 57) return String.fromCharCode(vk);
        if (vk >= 112 && vk <= 126) return 'F' + (vk - 111);
        if (vk >= 96 && vk <= 105) return 'NUMPAD' + (vk - 96);
        const side = event.location === 2 ? 'R' : 'L';
        const fallback = {
            8: 'BACKSPACE', 9: 'TAB', 13: event.location === 3 ? 'NUMPADENTER' : 'RETURN',
            16: side + 'SHIFT', 17: side + 'CONTROL', 18: side + 'ALT', 19: 'PAUSE', 20: 'CAPSLOCK',
            27: 'ESCAPE', 32: 'SPACE', 33: 'PGUP', 34: 'PGDN', 35: 'END', 36: 'HOME',
            37: 'LEFTARROW', 38: 'UPARROW', 39: 'RIGHTARROW', 40: 'DOWNARROW', 44: 'SYSRQ',
            45: 'INSERT', 46: 'DELETE', 91: 'LWIN', 92: 'RWIN', 93: 'APPS', 106: 'NUMPADSTAR',
            107: 'ADD', 109: 'NUMPADMINUS', 110: 'NUMPADPERIOD', 111: 'NUMPADSLASH', 144: 'NUMLOCK',
            145: 'SCROLL', 186: 'SEMICOLON', 187: 'EQUALS', 188: 'COMMA', 189: 'MINUS',
            190: 'PERIOD', 191: 'SLASH', 192: 'GRAVE', 219: 'LBRACKET', 220: 'BACKSLASH',
            221: 'RBRACKET', 222: 'APOSTROPHE', 226: 'OEM_102',
        };
        return fallback[vk] || keyboardCodes[event.key] ||
            (typeof event.key === 'string' && /^[A-Za-z0-9]$|^F[0-9]+$/.test(event.key) ? event.key.toUpperCase() : null);
    }

    function mount() {
        overlay = element('div', 'uamm-backdrop uamm-hidden');
        const dialog = element('section', 'uamm-panel');
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');
        dialog.setAttribute('aria-labelledby', 'uamm-heading');

        const header = element('header', 'uamm-header');
        const title = element('div', 'uamm-heading-group');
        const heading = element('h1', 'uamm-heading', 'Моди');
        heading.id = 'uamm-heading';
        summary = element('div', 'uamm-count');
        title.appendChild(heading);
        title.appendChild(summary);
        const close = button('Закрити', 'uamm-button uamm-close', () => send('close'));
        header.appendChild(title);
        header.appendChild(close);

        const body = element('div', 'uamm-body');
        const sidebar = element('section', 'uamm-sidebar');
        const searchLabel = element('label', 'uamm-search-label', 'Пошук модів');
        searchLabel.htmlFor = 'uamm-search';
        search = element('input', 'uamm-search');
        search.id = 'uamm-search';
        search.type = 'text';
        search.addEventListener('input', () => {
            filter = search.value.toLowerCase().trim();
            listScroll.reset();
            renderList();
        });
        const tabs = element('div', 'uamm-filters');
        [['all', 'Усі'], ['on', 'Активні'], ['off', 'Вимкнені']].forEach(([id, label]) => {
            const tab = button(label, 'uamm-filter', () => {
                filterTab = id;
                listScroll.reset();
                Array.from(tabs.children).forEach(node => {
                    node.setAttribute('aria-pressed', String(node.dataset.filter === filterTab));
                });
                renderList();
            });
            tab.dataset.filter = id;
            tab.setAttribute('aria-pressed', String(id === filterTab));
            tabs.appendChild(tab);
        });
        sidebar.appendChild(searchLabel);
        sidebar.appendChild(search);
        sidebar.appendChild(tabs);
        listScroll = scrollPane(sidebar, 'list');
        list = listScroll.content;
        body.appendChild(sidebar);
        detailScroll = scrollPane(body, 'detail');
        detail = detailScroll.content;
        detail.setAttribute('aria-label', 'Налаштування моду');

        const footer = element('footer', 'uamm-footer');
        footer.appendChild(element('span', 'uamm-help', 'Параметри зберігаються автоматично'));
        const actions = element('div', 'uamm-footer-actions');
        status = element('span', 'uamm-status');
        status.setAttribute('role', 'status');
        actions.appendChild(status);
        restart = button('Перезапустити гру', 'uamm-button uamm-restart uamm-hidden', () => {
            restart.disabled = true;
            send('restart');
        });
        actions.appendChild(restart);
        footer.appendChild(actions);
        dialog.appendChild(header);
        dialog.appendChild(body);
        dialog.appendChild(footer);
        overlay.appendChild(dialog);
        overlay.addEventListener('click', event => {
            if (event.target === overlay) send('close');
        });
        overlay.addEventListener('keydown', event => {
            if (state.binding && state.binding.capture && event.target.className !== 'uamm-key-search') {
                event.stopPropagation();
                event.preventDefault();
                const key = bindingKey(event);
                if (key && !event.repeat) send('bindReceived', { key });
                return;
            }
            if (event.key === 'Escape' || event.keyCode === 27) {
                event.stopPropagation();
                event.preventDefault();
                send('close');
            }
            if (event.key !== 'Tab' && event.keyCode !== 9) return;
            const focusable = dialog.querySelectorAll('button:not(:disabled), input:not(:disabled)');
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        });
        document.body.appendChild(overlay);
    }

    function toggle(label, checked, action, id) {
        const control = button('', 'uamm-switch', action);
        control.setAttribute('role', 'switch');
        control.setAttribute('aria-checked', String(!!checked));
        control.setAttribute('aria-label', label);
        control.dataset.control = id;
        control.appendChild(element('span', 'uamm-switch-knob'));
        return control;
    }

    function renderList() {
        list.textContent = '';
        const shown = state.mods.filter(mod => {
            if (filterTab === 'on' && !mod.enabled || filterTab === 'off' && mod.enabled) return false;
            return !filter || (mod.title + ' ' + mod.id).toLowerCase().indexOf(filter) !== -1;
        });
        if (!shown.length) list.appendChild(element('p', 'uamm-empty', 'Модів не знайдено.'));
        let group = '';
        shown.forEach(mod => {
            const label = mod.library ? 'Компоненти OpenWG' : 'Ігрові моди';
            if (label !== group) {
                list.appendChild(element('div', 'uamm-group', label));
                group = label;
            }
            const row = element('div', 'uamm-list-row');
            row.classList.toggle('uamm-selected', mod.id === selected);
            const pick = button('', 'uamm-pick', () => {
                selected = mod.id;
                choiceKey = '';
                renderList();
                renderDetail(false);
                const node = Array.from(list.querySelectorAll('.uamm-pick')).find(item => item.dataset.control === mod.id);
                if (node) node.focus();
            });
            pick.dataset.control = mod.id;
            pick.setAttribute('aria-pressed', String(mod.id === selected));
            pick.appendChild(element('span', 'uamm-mod-name', mod.title));
            const meta = mod.pending ? 'Після перезапуску' : (mod.version ? 'v' + mod.version : '');
            if (meta) pick.appendChild(element('span', 'uamm-mod-meta', meta));
            row.appendChild(pick);
            const power = toggle(mod.title, mod.enabled, () => change(mod, 'enabled', !mod.enabled), mod.id + ':power');
            power.title = mod.restart ? 'Застосується після перезапуску гри' : 'Застосується одразу';
            power.disabled = !!mod.error;
            row.appendChild(power);
            list.appendChild(row);
        });
        listScroll.refresh();
    }

    function renderKeyPicker(offer) {
        const panel = element('div', 'uamm-key-picker');
        const filterKeys = element('input', 'uamm-key-search');
        filterKeys.type = 'text';
        filterKeys.placeholder = 'Знайти клавішу';
        filterKeys.setAttribute('aria-label', 'Знайти клавішу');
        const results = element('div', 'uamm-bind-actions');
        const navigation = element('div', 'uamm-bind-actions');
        const pageSize = 12;
        let page = 0;
        function render() {
            const query = filterKeys.value.trim().toLowerCase();
            const keys = offer.keys.filter(key =>
                key.label.toLowerCase().indexOf(query) !== -1 || key.name.toLowerCase().indexOf(query) !== -1);
            results.textContent = '';
            navigation.textContent = '';
            keys.slice(page * pageSize, (page + 1) * pageSize).forEach(key =>
                results.appendChild(button(key.label, 'uamm-button', () => send('bindPick', { key: key.name }))));
            if (!keys.length) results.appendChild(element('span', 'uamm-empty', 'Клавіш не знайдено.'));
            if (page > 0) navigation.appendChild(button('Назад', 'uamm-button', () => { page--; render(); }));
            if ((page + 1) * pageSize < keys.length) navigation.appendChild(button('Далі', 'uamm-button', () => { page++; render(); }));
            detailScroll.refresh();
        }
        filterKeys.addEventListener('focus', () => send('bindSearch'));
        filterKeys.addEventListener('input', () => { page = 0; render(); });
        panel.appendChild(filterKeys);
        panel.appendChild(results);
        panel.appendChild(navigation);
        detail.appendChild(panel);
        render();
    }

    function renderDetail(preserveScroll) {
        detail.textContent = '';
        const mod = state.mods.find(item => item.id === selected);
        if (!mod) {
            detail.appendChild(element('p', 'uamm-empty', 'Виберіть мод зі списку.'));
            return;
        }
        const name = element('div', 'uamm-detail-heading');
        name.appendChild(element('h2', 'uamm-detail-title', mod.title));
        name.appendChild(element('span', 'uamm-power ' + (mod.running ? 'uamm-power-on' : ''), mod.running ? 'Увімкнено' : 'Вимкнено'));
        detail.appendChild(name);
        if (mod.description) detail.appendChild(element('p', 'uamm-description', mod.description));
        if (mod.pending) {
            const message = mod.enabled ? 'Мод увімкнеться після перезапуску гри.' : 'Мод вимкнеться після перезапуску гри.';
            detail.appendChild(element('p', 'uamm-notice', message));
        } else if (mod.restart) {
            detail.appendChild(element('p', 'uamm-description', 'Перемикач діє з наступного запуску гри.'));
        }
        if (mod.error) detail.appendChild(element('p', 'uamm-notice uamm-error', mod.error));
        if (mod.graphics) {
            const openGraphics = button('Відкрити налаштування графіки', 'uamm-button uamm-graphics', () => send('graphics', { id: mod.id }));
            detail.appendChild(openGraphics);
        }
        if (mod.fields.length) detail.appendChild(element('h3', 'uamm-section-title', 'Налаштування'));
        mod.fields.forEach(field => {
            if (field.kind === 'section') {
                detail.appendChild(element('h3', 'uamm-section-title', field.label));
                return;
            }
            const row = element('div', 'uamm-setting');
            row.appendChild(element('span', 'uamm-setting-label', field.label));
            if (field.kind === 'bind') {
                const capture = state.binding && state.binding.id === mod.id && state.binding.capture;
                const changeKey = button(capture ? 'Скасувати вибір' : field.display,
                    'uamm-button', () => send(capture ? 'bindCancel' : 'bindBegin', { id: mod.id }));
                changeKey.dataset.control = 'bind';
                row.appendChild(changeKey);
                if (field.value && !capture) {
                    const clear = button('Прибрати', 'uamm-button', () => send('bindClear', { id: mod.id }));
                    row.appendChild(clear);
                }
                detail.appendChild(row);
                const offer = state.binding;
                if (offer && offer.id === mod.id && offer.conflicts && offer.conflicts.length) {
                    const warning = element('div', 'uamm-notice uamm-bind-warning');
                    warning.setAttribute('role', 'alert');
                    warning.appendChild(element('div', '', 'Клавіша «' + offer.label + '» зайнята.'));
                    const conflicts = element('ul', '');
                    offer.conflicts.forEach(label => conflicts.appendChild(element('li', '', label)));
                    warning.appendChild(conflicts);
                    const actions = element('div', 'uamm-bind-actions');
                    actions.appendChild(button('Вибрати іншу', 'uamm-button', () => send('bindBegin', { id: mod.id })));
                    if (offer.replaceable) {
                        actions.appendChild(button('Замінити прив’язку', 'uamm-button', () => send('bindReplace')));
                    }
                    actions.appendChild(button('Скасувати', 'uamm-button', () => send('bindCancel')));
                    warning.appendChild(actions);
                    detail.appendChild(warning);
                }
                if ((!offer || offer.id !== mod.id) && field.issues && field.issues.length) {
                    detail.appendChild(element('p', 'uamm-notice',
                        'Також призначено на цю клавішу: ' + field.issues.join(', ') + '.'));
                }
                if (capture) {
                    renderKeyPicker(offer);
                    changeKey.focus();
                }
                return;
            }
            if (field.kind === 'reset') {
                const reset = button('Скинути', 'uamm-button', () => change(mod, field.key, true));
                reset.disabled = !!field.disabled;
                reset.dataset.control = field.key;
                reset.setAttribute('aria-label', 'Скинути — ' + field.label);
                row.appendChild(reset);
            } else if (field.kind === 'bool') {
                const setting = toggle(field.label, field.value, () => change(mod, field.key, !field.value), field.key);
                setting.disabled = !!field.disabled;
                if (field.disabled) setting.title = 'Недоступно';
                row.appendChild(setting);
            } else if (field.kind === 'choice') {
                const options = field.options;
                const chosen = options.find(option => option.value === field.value);
                const picker = element('div', 'uamm-choice');
                const control = button(chosen ? chosen.label : 'Недоступно', 'uamm-button uamm-choice-current', () => {
                    choiceKey = choiceKey === field.key ? '' : field.key;
                    renderDetail(true);
                });
                control.disabled = !!field.disabled;
                control.dataset.control = field.key;
                control.setAttribute('aria-expanded', String(choiceKey === field.key));
                control.setAttribute('aria-label', field.label + (chosen ? ' — ' + chosen.label : ' — недоступно'));
                picker.appendChild(control);
                if (choiceKey === field.key) {
                    const menu = element('div', 'uamm-choice-menu');
                    options.forEach(option => {
                        const pick = button(option.label, 'uamm-choice-option', () => {
                            choiceKey = '';
                            renderDetail(true);
                            if (option.value !== field.value) change(mod, field.key, option.value);
                        });
                        pick.setAttribute('aria-pressed', String(option.value === field.value));
                        menu.appendChild(pick);
                    });
                    picker.appendChild(menu);
                }
                row.appendChild(picker);
            } else {
                const stepper = element('div', 'uamm-stepper');
                const lower = field.zero && field.value <= field.min ? 0 : Math.max(field.min, field.value - field.step);
                const higher = Math.min(field.max, Math.max(field.min, field.value + field.step));
                const less = button('-', 'uamm-step', () => change(mod, field.key, lower));
                const more = button('+', 'uamm-step', () => change(mod, field.key, higher));
                less.dataset.control = field.key + ':less';
                more.dataset.control = field.key + ':more';
                less.setAttribute('aria-label', field.label + ' — зменшити');
                more.setAttribute('aria-label', field.label + ' — збільшити');
                less.disabled = !!field.disabled || lower === field.value;
                more.disabled = !!field.disabled || higher === field.value;
                const value = element('input', 'uamm-value');
                value.type = 'text';
                value.inputMode = 'numeric';
                value.maxLength = 6;
                value.value = String(field.value);
                value.disabled = !!field.disabled;
                if (field.zero) value.title = '0 — без обмеження';
                value.setAttribute('aria-label', field.label);
                value.dataset.control = field.key;
                value.addEventListener('change', () => {
                    if (value.value === String(field.value)) return;
                    if (!/^\d+$/.test(value.value.trim())) {
                        value.value = String(field.value);
                        setStatus('Введіть число.', true);
                        return;
                    }
                    change(mod, field.key, Number(value.value));
                });
                value.addEventListener('keydown', event => {
                    if (event.key === 'Enter' || event.keyCode === 13) value.blur();
                });
                stepper.appendChild(less);
                stepper.appendChild(value);
                if (field.unit) stepper.appendChild(element('span', 'uamm-unit', field.unit));
                stepper.appendChild(more);
                row.appendChild(stepper);
            }
            detail.appendChild(row);
        });
        if (!mod.fields.length && !mod.graphics && !mod.error) {
            detail.appendChild(element('p', 'uamm-empty', 'Додаткових налаштувань немає.'));
        }
        if (preserveScroll) detailScroll.refresh();
        else detailScroll.reset();
    }

    function receive(next) {
        const wasOpen = state.open;
        const active = document.activeElement;
        const focus = active && active.getAttribute('data-control');
        state = next;
        if (pending !== null && next.request === pending) {
            pending = null;
            clearTimeout(timer);
        }
        const research = state.mods.find(mod => mod.id === researchId);
        document.body.classList.toggle('uamm-disable-research', !!research && !research.enabled);
        overlay.classList.toggle('uamm-hidden', !next.open);
        if (!next.open) {
            choiceKey = '';
            if (wasOpen && lastActive && document.body.contains(lastActive)) lastActive.focus();
            return;
        }
        if (!wasOpen) lastActive = document.activeElement;
        if (!state.mods.some(mod => mod.id === selected)) {
            const initial = state.mods.find(mod => mod.fields.length) || state.mods[0];
            selected = initial ? initial.id : '';
        }
        summary.textContent = state.mods.filter(mod => mod.running).length + ' з ' + state.mods.length + ' активні';
        setStatus(state.status || '', state.error);
        restart.classList.toggle('uamm-hidden', !state.restartRequired);
        restart.disabled = !!state.restarting;
        renderList();
        renderDetail(wasOpen);
        if (!wasOpen) overlay.querySelector('.uamm-close').focus();
        if (focus && wasOpen) {
            const control = Array.from(overlay.querySelectorAll('[data-control]')).find(item => item.dataset.control === focus);
            if (control && !control.disabled) control.focus();
        }
    }

    function connectNative() {
        adapter = args => window.model.onModManagerRequest(args);
        const sync = () => {
            const model = window.model;
            if (model && model.modManagerState) {
                receive(JSON.parse(model.modManagerState));
            }
        };
        const callback = viewEnv.addDataChangedCallback('model', 0, true);
        const listener = (data, indexes, callbacks) => {
            if (callbacks.indexOf(callback) !== -1) sync();
        };
        engine.on('viewEnv.onDataChanged', listener);
        sync();
        if (!window.model || !window.model.modManagerState) adapter({ action: 'refresh' });
        window.addEventListener('unload', () => {
            engine.off('viewEnv.onDataChanged', listener);
            viewEnv.removeDataChangedCallback(callback, 0);
        });
    }

    mount();
    if (window.engine && window.viewEnv) {
        engine.whenReady.then(connectNative);
    } else if (window.modManagerPreview) {
        adapter = args => receive(window.modManagerPreview(args));
        document.body.appendChild(button('Моди', 'uamm-launcher uamm-launcher-preview', () => send('open')));
        send('open');
    }
})();

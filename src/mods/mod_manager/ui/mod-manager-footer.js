(() => {
    window.engine.whenReady.then(() => {
        const launcher = document.createElement('button');
        launcher.type = 'button';
        launcher.className = 'uamm-launcher';
        launcher.textContent = 'Моди';
        launcher.dataset.testId = 'ua-mod-manager';
        launcher.setAttribute('aria-haspopup', 'dialog');
        launcher.addEventListener('click', () => window.model.onOpenModManager({}));

        const mount = () => {
            const menu = document.querySelector('[data-test-id="menu"]');
            if (!menu || !window.model || typeof window.model.onOpenModManager !== 'function') return;
            const section = menu.parentNode;
            if (section.firstChild !== launcher) section.insertBefore(launcher, section.firstChild);
        };
        const observer = new MutationObserver(mount);
        observer.observe(document.getElementById('root'), { childList: true, subtree: true });
        window.addEventListener('unload', () => observer.disconnect());
        mount();
    });
})();

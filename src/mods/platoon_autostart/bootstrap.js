(() => {
    const base = document.currentScript.src.replace(/\.js(?:\?.*)?$/, "");
    const separator = base.lastIndexOf("/");
    const directory = base.slice(0, separator + 1);
    const view = base.slice(separator + 1);
    let started = false;

    function loadView() {
        if (started) return;
        started = true;
        const model = window.model;
        const customized = model && model.squadPlusEnabled === true;
        if (customized) {
            const nativeStyle = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
                .find(link => link.href === base + ".css");
            if (nativeStyle) nativeStyle.href = base + ".squad.css";
            else {
                const style = document.createElement("link");
                style.rel = "stylesheet";
                style.href = base + ".squad.css";
                document.head.appendChild(style);
            }
        }
        const script = document.createElement("script");
        // Gameface resolves model scope from the JS basename — 2026-11-25
        script.src = directory + (customized ? "squad/" : "stock/") + view + ".js";
        document.head.appendChild(script);
    }

    if (engine._BindingsReady && engine._ContentLoaded) loadView();
    else engine.on("Ready", loadView);
})();

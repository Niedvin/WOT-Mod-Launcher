(() => {
    const base = document.currentScript.src.replace(/\.js(?:\?.*)?$/, "");
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
        script.src = base + (customized ? ".squad.js" : ".stock.js");
        document.head.appendChild(script);
    }

    if (engine._BindingsReady && engine._ContentLoaded) loadView();
    else engine.on("Ready", loadView);
})();

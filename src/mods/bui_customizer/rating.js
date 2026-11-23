(() => {
    let last = "";
    window.setInterval(() => {
        const model = window.model;
        const panel = document.querySelector('[class*="PostmortemPanelViewApp_column"]');
        if (!model || typeof model.onBuiMeasure !== "function" || !panel
                || !window.innerWidth || !window.innerHeight) return;
        const box = panel.getBoundingClientRect();
        if (!box.width || !box.height) return;
        const data = {
            x: Math.max(0, box.left / window.innerWidth),
            y: Math.max(0, box.top / window.innerHeight),
            width: Math.min(1, box.width / window.innerWidth),
            height: Math.min(1, box.height / window.innerHeight)
        };
        const signature = JSON.stringify(data);
        if (signature !== last) {
            model.onBuiMeasure(data);
            last = signature;
        }
    }, 150);
})();

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const bootstrap = fs.readFileSync(path.join(__dirname, "bootstrap.js"), "utf8");

for (const view of ["MembersWindow", "PlatoonDropdown"]) {
    for (const branch of ["squad", "stock"]) {
        test(`${view} retains its model scope in ${branch}`, () => {
            const directory = `coui://gui/platoon/${view}/`;
            const scriptUrl = `${directory}${view}.js`;
            const loaded = [];
            const document = {
                currentScript: { src: scriptUrl },
                head: { appendChild: node => loaded.push(node) },
                createElement: () => ({}),
                querySelectorAll: () => [],
            };
            const window = { model: { squadPlusEnabled: branch === "squad" } };
            let ready;
            const engine = { on(event, callback) { assert.equal(event, "Ready"); ready = callback; } };

            vm.runInNewContext(bootstrap, { document, window, engine });
            assert.equal(loaded.length, 0);
            ready();
            ready();
            assert.deepEqual(loaded.filter(node => node.src).map(node => node.src), [
                `${directory}${branch}/${view}.js`,
            ]);
        });
    }
}

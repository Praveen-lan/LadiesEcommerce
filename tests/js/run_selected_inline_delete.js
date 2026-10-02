"use strict";
/*
 * Runs static/store/admin/selected-inline-delete.js against the DOM stub.
 *
 * Usage:  node tests/js/run_selected_inline_delete.js <script-path>  < spec.json
 *
 * spec.json: { origin, deleteUrl, deleteLinkIn, rows: [{prefix, index, id, deleteChecked}] }
 * Output:    { linkFound, clickHandlers, intercepted, navigatedTo, alerts }
 */

const fs = require("fs");
const vm = require("vm");
const { build } = require("./dom_stub");

const scriptPath = process.argv[2];
const spec = JSON.parse(fs.readFileSync(0, "utf8"));
const source = fs.readFileSync(scriptPath, "utf8");

const dom = build(spec);
const sandbox = { document: dom.document, window: dom.window, URL, console };
sandbox.window.document = dom.document;
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: scriptPath });

for (const handler of dom.document.listeners.DOMContentLoaded || []) handler();

let defaultPrevented = false;
const event = {
    type: "click",
    target: dom.deleteAnchor,
    preventDefault() {
        defaultPrevented = true;
    },
};
const handlers = dom.deleteAnchor.listeners.click || [];
for (const handler of handlers) handler(event);

process.stdout.write(
    JSON.stringify({
        linkFound: Boolean(dom.deleteAnchor.listeners.click),
        clickHandlers: handlers.length,
        intercepted: defaultPrevented,
        navigatedTo: dom.window.location.assigned[0] || null,
        alerts: dom.window.alerts,
    })
);

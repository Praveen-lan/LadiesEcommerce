"use strict";
/*
 * Tiny DOM stub used to exercise static/store/admin/selected-inline-delete.js
 * from the pytest suite. The admin bug lives in the browser, so the regression
 * test drives the real script instead of re-implementing its logic.
 */

function parseCompound(token) {
    const parts = token.match(/[a-zA-Z][\w-]*|\.[\w-]+|\[[^\]]+\]|:[\w-]+/g) || [];
    const spec = { tag: null, classes: [], attrs: [], pseudos: [] };
    for (const part of parts) {
        if (part[0] === ".") {
            spec.classes.push(part.slice(1));
        } else if (part[0] === "[") {
            const match = part.slice(1, -1).match(/^([\w-]+)(?:([*^$~|]?=)"?([^"\]]*)"?)?$/);
            spec.attrs.push({ name: match[1], op: match[2] || null, value: match[3] });
        } else if (part[0] === ":") {
            spec.pseudos.push(part.slice(1));
        } else {
            spec.tag = part.toLowerCase();
        }
    }
    return spec;
}

function matches(node, spec) {
    if (!node || node.__kind !== "element") return false;
    if (spec.tag && node.tag !== spec.tag) return false;
    for (const cls of spec.classes) {
        if (!node.classes.includes(cls)) return false;
    }
    for (const attr of spec.attrs) {
        const value = node.attrs[attr.name];
        if (value === undefined) return false;
        if (attr.op === null) continue;
        const text = String(value);
        if (attr.op === "*=" && !text.includes(attr.value)) return false;
        if (attr.op === "$=" && !text.endsWith(attr.value)) return false;
        if (attr.op === "^=" && !text.startsWith(attr.value)) return false;
        if (attr.op === "=" && text !== attr.value) return false;
    }
    for (const pseudo of spec.pseudos) {
        if (pseudo === "checked") {
            if (!node.checked) return false;
        } else {
            return false;
        }
    }
    return true;
}

function element(tag, attrs, children) {
    attrs = attrs || {};
    children = children || [];
    const node = {
        __kind: "element",
        tag: tag.toLowerCase(),
        attrs,
        classes: String(attrs.class || "").split(/\s+/).filter(Boolean),
        children,
        parent: null,
        checked: Object.prototype.hasOwnProperty.call(attrs, "checked"),
        listeners: {},
        get name() {
            return attrs.name === undefined ? "" : String(attrs.name);
        },
        get value() {
            return attrs.value === undefined ? "" : String(attrs.value);
        },
        set value(next) {
            attrs.value = next;
        },
    };
    node.addEventListener = function (type, handler) {
        (node.listeners[type] = node.listeners[type] || []).push(handler);
    };
    node.querySelector = function (selector) {
        const found = queryAll(node, selector);
        return found.length ? found[0] : null;
    };
    node.querySelectorAll = function (selector) {
        return queryAll(node, selector);
    };
    node.closest = function (selector) {
        return closest(node, selector);
    };
    for (const child of children) child.parent = node;
    return node;
}

function descendants(node, acc) {
    acc = acc || [];
    for (const child of node.children) {
        acc.push(child);
        descendants(child, acc);
    }
    return acc;
}

function queryAll(root, selector) {
    const compounds = selector.trim().split(/\s+/).map(parseCompound);
    return descendants(root).filter(function (node) {
        let index = compounds.length - 1;
        if (!matches(node, compounds[index])) return false;
        let cursor = node.parent;
        index -= 1;
        while (index >= 0 && cursor) {
            if (matches(cursor, compounds[index])) index -= 1;
            cursor = cursor.parent;
        }
        return index < 0;
    });
}

function closest(node, selector) {
    const spec = parseCompound(selector);
    let cursor = node;
    while (cursor) {
        if (matches(cursor, spec)) return cursor;
        cursor = cursor.parent;
    }
    return null;
}

function attachNavigation(node, origin) {
    const parsed = new URL(node.attrs.href, origin);
    node.pathname = parsed.pathname;
    node.search = parsed.search;
    node.href = node.attrs.href;
}

function build(spec) {
    const origin = spec.origin || "http://testserver";
    function buildRow(row) {
        const cells = [
            element("input", {
                type: "hidden",
                name: row.idName || row.prefix + "-" + row.index + "-id",
                value: row.id || "",
            }),
            element("input", { type: "checkbox", name: row.prefix + "-" + row.index + "-is_featured" }),
        ];
        if (row.deleteChecked) {
            cells[1].attrs.name = row.deleteName || row.prefix + "-" + row.index + "-DELETE";
            cells[1].checked = true;
        }
        return element("tr", {}, cells);
    }

    const rows = (spec.rows || []).map(buildRow);
    const outsideRows = (spec.outsideRows || []).map(buildRow);

    const inlineGroup = element(
        "div",
        { class: "js-inline-admin-formset inline-group", id: "sarees-group" },
        [element("table", {}, [element("tbody", {}, rows)])]
    );

    const deleteAnchor = element("a", { role: "button", href: spec.deleteUrl, class: "deletelink" }, [
        (() => {
            const text = element("span", {}, []);
            text.textContent = "Delete";
            return text;
        })(),
    ]);
    attachNavigation(deleteAnchor, origin);

    const body = element("body", {}, [element("form", {}, [inlineGroup])]);
    if (outsideRows.length) {
        body.children.push(element("div", { class: "outside-controls" }, outsideRows));
    }
    if (spec.deleteLinkIn !== "none") {
        const containerClass = spec.deleteLinkIn === "object-tools" ? "object-tools" : "submit-row";
        body.children[0].children.push(
            element("ul", { class: containerClass }, [deleteAnchor])
        );
    }

    const document = {
        listeners: {},
        addEventListener(type, handler) {
            (this.listeners[type] = this.listeners[type] || []).push(handler);
        },
        querySelector(selector) {
            const found = queryAll(body, selector);
            return found.length ? found[0] : null;
        },
        querySelectorAll(selector) {
            return queryAll(body, selector);
        },
    };

    const window = {
        location: {
            origin,
            assigned: [],
            assign(value) {
                this.assigned.push(value);
            },
        },
        alerts: [],
        alert(message) {
            this.alerts.push(message);
        },
    };

    return { body, document, window, deleteAnchor };
}

module.exports = { build };

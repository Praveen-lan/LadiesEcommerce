(function () {
    "use strict";

    const SELECTIONS = {
        category: { key: "selected_sarees", prefix: "sarees" },
        order: { key: "selected_items", prefix: "items" },
    };

    // Django >= 4.0 renders the object "Delete" button in .submit-row, older
    // versions put it in .object-tools. Both are searched, but a candidate only
    // qualifies when its href is this object's delete view, so the inline
    // "Remove saree" links (which are also .deletelink) are never matched.
    const DELETE_LINK_SELECTORS = [
        ".submit-row a.deletelink",
        ".object-tools a.deletelink",
        ".submit-row a[href$='/delete/']",
        ".object-tools a[href$='/delete/']",
    ];

    const UNSAVED_ROW_WARNING =
        "Save or remove unsaved inline rows before deleting selected items.";

    function selectionKeyFor(deleteLink) {
        if (!deleteLink) return null;
        const path = deleteLink.pathname || "";
        const match = path.match(/\/store\/(category|order)\/\d+\/delete\/?$/);
        return match ? SELECTIONS[match[1]] : null;
    }

    function findObjectDeleteLink() {
        for (const selector of DELETE_LINK_SELECTORS) {
            const links = document.querySelectorAll(selector);
            for (let i = 0; i < links.length; i += 1) {
                if (selectionKeyFor(links[i])) return links[i];
            }
        }
        return null;
    }

    function checkedDeleteRows(formsetPrefix) {
        const selector =
            '.inline-group input[type="checkbox"][name^="' +
            formsetPrefix +
            '-"][name$="-DELETE"]:checked';
        const checkboxes = document.querySelectorAll(selector);
        const rows = [];
        for (let i = 0; i < checkboxes.length; i += 1) {
            const checkbox = checkboxes[i];
            const nameMatch = checkbox.name.match(
                new RegExp("^" + formsetPrefix + "-(\\d+)-DELETE$")
            );
            const row = checkbox.closest("tr");
            const idInput = row && nameMatch
                ? row.querySelector(
                    'input[type="hidden"][name="' +
                        formsetPrefix +
                        "-" +
                        nameMatch[1] +
                        '-id"]'
                )
                : null;
            rows.push({ id: idInput ? String(idInput.value).trim() : "" });
        }
        return rows;
    }

    document.addEventListener("DOMContentLoaded", function () {
        const deleteLink = findObjectDeleteLink();
        const selection = selectionKeyFor(deleteLink);
        if (!deleteLink || !selection) return;

        deleteLink.addEventListener("click", function (event) {
            const rows = checkedDeleteRows(selection.prefix);
            // Nothing ticked: fall through to the normal whole-object delete.
            if (!rows.length) return;

            const selectedIds = new Set();
            for (const row of rows) {
                if (!row.id) {
                    event.preventDefault();
                    window.alert(UNSAVED_ROW_WARNING);
                    return;
                }
                selectedIds.add(row.id);
            }

            event.preventDefault();
            const target = new URL(deleteLink.href, window.location.origin);
            for (const id of selectedIds) {
                target.searchParams.append(selection.key, id);
            }
            window.location.assign(target.toString());
        });
    });
})();
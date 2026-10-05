(function () {
    "use strict";

    // Every category owns the same starter sub category titles, so the raw list
    // is ambiguous. Options carry data-category (see store/forms.py); this hides
    // the ones that do not belong to the category selected just above them.
    // The server still rejects a mismatched pair in Saree.clean().

    function categoryFieldFor(subcategoryField) {
        // The main form is "id_subcategory"; an inline row is
        // "id_sarees-0-subcategory". Both map onto the sibling category field.
        return document.getElementById(
            subcategoryField.id.replace(/subcategory$/, "category")
        );
    }

    function sync(subcategoryField, categoryField) {
        var options = subcategoryField.options;
        for (var i = 0; i < options.length; i += 1) {
            var option = options[i];
            if (!option.value) continue;
            var matches = option.getAttribute("data-category") === categoryField.value;
            option.hidden = !matches;
            option.disabled = !matches;
        }
        var selected = options[subcategoryField.selectedIndex];
        if (selected && selected.disabled) {
            subcategoryField.selectedIndex = 0;
        }
    }

    function bind(subcategoryField) {
        var categoryField = categoryFieldFor(subcategoryField);
        if (!categoryField) return;
        categoryField.addEventListener("change", function () {
            sync(subcategoryField, categoryField);
        });
        sync(subcategoryField, categoryField);
    }

    document.addEventListener("DOMContentLoaded", function () {
        var fields = document.querySelectorAll('select[name$="subcategory"]');
        for (var i = 0; i < fields.length; i += 1) {
            bind(fields[i]);
        }
    });
})();

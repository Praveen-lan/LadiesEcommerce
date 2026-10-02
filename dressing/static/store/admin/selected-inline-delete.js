document.addEventListener("DOMContentLoaded", () => {
    const deleteLink = document.querySelector('.object-tools a[href$="/delete/"]');
    if (!deleteLink) return;

    const match = deleteLink.pathname.match(/\/store\/(category|order)\/\d+\/delete\/$/);
    if (!match) return;
    const selectionKey = match[1] === "order" ? "selected_items" : "selected_sarees";

    deleteLink.addEventListener("click", (event) => {
        const checkedBoxes = Array.from(
            document.querySelectorAll('.inline-group input[type="checkbox"][name$="-DELETE"]:checked')
        );
        if (!checkedBoxes.length) return;

        const selectedIds = [];
        for (const checkbox of checkedBoxes) {
            const row = checkbox.closest("tr");
            const idInput = row && row.querySelector('input[name$="-id"]');
            if (!idInput || !idInput.value) {
                event.preventDefault();
                window.alert("Save or remove unsaved inline rows before deleting selected items.");
                return;
            }
            selectedIds.push(idInput.value);
        }

        event.preventDefault();
        const target = new URL(deleteLink.href, window.location.origin);
        selectedIds.forEach((id) => target.searchParams.append(selectionKey, id));
        window.location.assign(target.toString());
    });
});
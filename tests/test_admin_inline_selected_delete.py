"""Regression tests for the admin inline "Delete?" checkbox handling.

Bug 1: ticking "Delete?" on some inline rows and pressing the object "Delete"
button deleted the whole category/order, because the helper script looked for
the button in `.object-tools` while Django renders it in `.submit-row`.

Bug 2: the helper script was never loaded at all. A `?v=3` cache-busting query
string was appended to the static path, and Django percent-encodes the `?`, so
the page asked for `/static/.../selected-inline-delete.js%3Fv%3D3` -> 404. With
no script the "Delete" button always went to the whole-object delete view, which
is exactly the reported symptom.
"""

import json
import re
import shutil
import subprocess
from urllib.parse import urljoin
from urllib.request import urlopen
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

from store.admin import SELECTED_INLINE_DELETE_JS
from store.models import Category, OrderItem, Saree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PROJECT_ROOT / "tests" / "js" / "run_selected_inline_delete.js"
SCRIPT = PROJECT_ROOT / "static" / "store" / "admin" / "selected-inline-delete.js"

node_required = pytest.mark.skipif(shutil.which("node") is None, reason="node is required for the JS tests")


def run_inline_delete_script(**spec):
    completed = subprocess.run(
        ["node", str(RUNNER), str(SCRIPT)],
        input=json.dumps(spec),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def inline_rows(content, formset_prefix, order):
    """Build the DOM-stub rows the browser would have for ``formset_prefix``."""
    rows = []
    for index in range(order):
        hidden = re.search(
            r'<input type="hidden" name="%s-%d-id" value="(\d*)"' % (re.escape(formset_prefix), index),
            content,
        )
        delete = re.search(r'<input type="checkbox" name="%s-%d-DELETE"' % (re.escape(formset_prefix), index), content)
        rows.append(
            {
                "prefix": formset_prefix,
                "index": index,
                "id": hidden.group(1) if hidden else "",
                "deleteChecked": bool(delete),
            }
        )
    return rows


def build_selected_delete_url(delete_url, selection_key, ids, origin=""):
    pairs = "&".join(f"{selection_key}={pk}" for pk in ids)
    return f"{origin}{delete_url}?{pairs}"


# --------------------------------------------------------------------------- #
# The rendered admin page must expose the markup the script depends on.
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_category_change_page_renders_delete_button_in_the_submit_row(admin_user, client, category, chiffon_saree):
    client.force_login(admin_user)

    content = client.get(reverse("admin:store_category_change", args=[category.pk])).content.decode()

    assert "store/admin/selected-inline-delete.js" in content
    assert 'class="submit-row"' in content
    assert 'class="deletelink"' in content
    assert reverse("admin:store_category_delete", args=[category.pk]) in content
    # The markup the previous version of the script searched for is gone, which
    # is exactly why "Delete" used to fall through to the whole-category delete.
    object_tools = re.search(r'<ul class="object-tools">(.*?)</ul>', content, re.DOTALL)
    assert object_tools is not None
    assert "/delete/" not in object_tools.group(1)


@pytest.mark.django_db
def test_order_change_page_renders_delete_button_in_the_submit_row(
    admin_user, client, order_with_three_items
):
    order, _items = order_with_three_items
    client.force_login(admin_user)

    content = client.get(reverse("admin:store_order_change", args=[order.pk])).content.decode()

    assert "store/admin/selected-inline-delete.js" in content
    assert 'class="submit-row"' in content
    assert 'class="deletelink"' in content
    assert reverse("admin:store_order_delete", args=[order.pk]) in content


@pytest.mark.django_db
def test_category_change_page_serves_the_helper_script(
    admin_user, client, category, chiffon_saree, live_server
):
    """The rendered script URL resolves and returns the actual static asset."""
    client.force_login(admin_user)

    content = client.get(reverse("admin:store_category_change", args=[category.pk])).content.decode()

    srcs = re.findall(r'<script[^>]*src="([^"]*selected-inline-delete\.js[^"]*)"', content)
    assert srcs, "the helper script is not referenced by the change page"
    for src in srcs:
        # A cache-busting "?v=..." query string is percent-encoded into the path
        # by django.forms.widgets.Media and 404s.
        assert "%3F" not in src and "%3D" not in src, src
        assert "?" not in src, src
        assert src.endswith(SELECTED_INLINE_DELETE_JS), src

    assert finders.find(SELECTED_INLINE_DELETE_JS), (
        f"{SELECTED_INLINE_DELETE_JS} is referenced but not on disk"
    )
    script_url = urljoin(live_server.url + reverse("admin:store_category_change", args=[category.pk]), srcs[0])
    with urlopen(script_url) as response:
        assert response.status == 200
        assert response.read() == SCRIPT.read_bytes()


@pytest.mark.django_db
def test_category_change_page_renders_the_markup_the_script_relies_on(
    admin_user, client, category, chiffon_saree, silk_saree
):
    """Guard every selector in the helper script against real Django markup."""
    client.force_login(admin_user)

    content = client.get(reverse("admin:store_category_change", args=[category.pk])).content.decode()

    # The object "Delete" button the script intercepts.
    submit_row = re.search(r'<div class="submit-row">(.*?)</div>', content, re.DOTALL)
    assert submit_row is not None
    delete_anchors = [
        tag
        for tag in re.findall(r"<a[^>]*>", submit_row.group(1))
        if "deletelink" in tag and "/delete/" in tag
    ]
    assert len(delete_anchors) == 1, delete_anchors
    assert reverse("admin:store_category_delete", args=[category.pk]) in delete_anchors[0]

    # Inline rows live in a ".inline-group" and expose a hidden "-id" input plus a
    # "-DELETE" checkbox, so a ticked box can be mapped back to a saree pk.
    assert 'class="js-inline-admin-formset inline-group"' in content
    ids = dict(
        (index, pk)
        for index, pk in re.findall(
            r'<input type="hidden" name="sarees-(\d+)-id" value="(\d+)"', content
        )
    )
    assert ids == {"0": str(silk_saree.pk), "1": str(chiffon_saree.pk)}
    for index in ids:
        assert f'<input type="checkbox" name="sarees-{index}-DELETE"' in content


# --------------------------------------------------------------------------- #
# The script itself.
# --------------------------------------------------------------------------- #
@node_required
@pytest.mark.django_db
def test_script_sends_only_the_ticked_saree_when_delete_is_clicked(
    admin_user, client, category, chiffon_saree, silk_saree
):
    client.force_login(admin_user)
    change_url = reverse("admin:store_category_change", args=[category.pk])
    delete_url = reverse("admin:store_category_delete", args=[category.pk])
    content = client.get(change_url).content.decode()
    rows = inline_rows(content, "sarees", 2)
    for row, ticked in zip(rows, (False, True)):
        row["deleteChecked"] = ticked

    result = run_inline_delete_script(
        origin="http://testserver",
        deleteUrl=delete_url,
        deleteLinkIn="submit-row",
        rows=rows,
    )

    assert result["intercepted"] is True
    assert result["navigatedTo"] == build_selected_delete_url(
        delete_url, "selected_sarees", [chiffon_saree.pk], origin="http://testserver"
    )


@node_required
@pytest.mark.django_db
def test_script_sends_only_the_ticked_order_items(admin_user, client, order_with_three_items):
    order, items = order_with_three_items
    client.force_login(admin_user)
    change_url = reverse("admin:store_order_change", args=[order.pk])
    delete_url = reverse("admin:store_order_delete", args=[order.pk])
    content = client.get(change_url).content.decode()
    rows = inline_rows(content, "items", 3)
    for row, ticked in zip(rows, (True, True, False)):
        row["deleteChecked"] = ticked

    result = run_inline_delete_script(
        origin="http://testserver",
        deleteUrl=delete_url,
        deleteLinkIn="submit-row",
        rows=rows,
    )

    assert result["intercepted"] is True
    assert result["navigatedTo"] == build_selected_delete_url(
        delete_url, "selected_items", [items[0].pk, items[1].pk], origin="http://testserver"
    )


@node_required
@pytest.mark.django_db
def test_script_still_supports_the_legacy_object_tools_delete_button(
    admin_user, client, category, chiffon_saree, silk_saree
):
    delete_url = reverse("admin:store_category_delete", args=[category.pk])

    result = run_inline_delete_script(
        origin="http://testserver",
        deleteUrl=delete_url,
        deleteLinkIn="object-tools",
        rows=[
            {"prefix": "sarees", "index": 0, "id": str(chiffon_saree.pk), "deleteChecked": True},
            {"prefix": "sarees", "index": 1, "id": str(silk_saree.pk), "deleteChecked": False},
        ],
    )

    assert result["intercepted"] is True
    assert result["navigatedTo"].endswith(f"?selected_sarees={chiffon_saree.pk}")


@node_required
@pytest.mark.django_db
def test_script_leaves_the_link_alone_when_no_row_is_ticked(admin_user, client, category, chiffon_saree):
    delete_url = reverse("admin:store_category_delete", args=[category.pk])

    result = run_inline_delete_script(
        origin="http://testserver",
        deleteUrl=delete_url,
        deleteLinkIn="submit-row",
        rows=[{"prefix": "sarees", "index": 0, "id": str(chiffon_saree.pk), "deleteChecked": False}],
    )

    assert result["intercepted"] is False
    assert result["navigatedTo"] is None


@node_required
@pytest.mark.django_db
def test_script_refuses_unsaved_rows_instead_of_deleting_the_parent(
    admin_user, client, category, chiffon_saree
):
    delete_url = reverse("admin:store_category_delete", args=[category.pk])

    result = run_inline_delete_script(
        origin="http://testserver",
        deleteUrl=delete_url,
        deleteLinkIn="submit-row",
        rows=[
            {"prefix": "sarees", "index": 0, "id": str(chiffon_saree.pk), "deleteChecked": False},
            {"prefix": "sarees", "index": 1, "id": "", "deleteChecked": True},
        ],
    )

    assert result["intercepted"] is True
    assert result["navigatedTo"] is None
    assert result["alerts"]


@node_required
def test_script_ignores_checked_delete_controls_outside_the_inline_group():
    result = run_inline_delete_script(
        origin="http://testserver",
        deleteUrl="/admin/store/category/1/delete/",
        deleteLinkIn="submit-row",
        rows=[],
        outsideRows=[
            {"prefix": "sarees", "index": 0, "id": "17", "deleteChecked": True}
        ],
    )

    assert result["intercepted"] is False
    assert result["navigatedTo"] is None


@node_required
def test_script_requires_the_matching_formset_id_and_deduplicates_selected_ids():
    delete_url = "/admin/store/category/1/delete/"
    invalid = run_inline_delete_script(
        origin="http://testserver",
        deleteUrl=delete_url,
        deleteLinkIn="submit-row",
        rows=[
            {
                "prefix": "sarees",
                "index": 0,
                "id": "17",
                "idName": "items-0-id",
                "deleteChecked": True,
            }
        ],
    )
    assert invalid["intercepted"] is True
    assert invalid["navigatedTo"] is None
    assert invalid["alerts"]

    duplicate = run_inline_delete_script(
        origin="http://testserver",
        deleteUrl=delete_url,
        deleteLinkIn="submit-row",
        rows=[
            {"prefix": "sarees", "index": 0, "id": "17", "deleteChecked": True},
            {"prefix": "sarees", "index": 1, "id": "17", "deleteChecked": True},
        ],
    )
    assert duplicate["navigatedTo"] == "http://testserver/admin/store/category/1/delete/?selected_sarees=17"


@node_required
@pytest.mark.django_db
def test_script_ignores_models_it_does_not_manage(admin_user, client, chiffon_saree):
    delete_url = reverse("admin:store_saree_delete", args=[chiffon_saree.pk])

    result = run_inline_delete_script(
        origin="http://testserver",
        deleteUrl=delete_url,
        deleteLinkIn="submit-row",
        rows=[{"prefix": "sarees", "index": 0, "id": str(chiffon_saree.pk), "deleteChecked": True}],
    )

    assert result["linkFound"] is False


# --------------------------------------------------------------------------- #
# End-to-end: what the confirmation page lists, and what actually gets deleted.
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_category_confirmation_lists_only_the_ticked_saree(admin_user, client, category, chiffon_saree, silk_saree):
    client.force_login(admin_user)
    delete_url = reverse("admin:store_category_delete", args=[category.pk])
    selected_url = build_selected_delete_url(delete_url, "selected_sarees", [chiffon_saree.pk])

    response = client.get(selected_url)

    assert response.status_code == 200
    assert b"Chiffon Sunset Saree" in response.content
    assert b"Kanjivaram Silk Saree" not in response.content
    assert b"category and all unselected sarees will be kept" in response.content


@pytest.mark.django_db
def test_category_confirmation_deletes_only_the_ticked_saree(
    admin_user, client, category, chiffon_saree, silk_saree, basic_saree
):
    client.force_login(admin_user)
    delete_url = reverse("admin:store_category_delete", args=[category.pk])
    selected_url = build_selected_delete_url(delete_url, "selected_sarees", [chiffon_saree.pk])

    response = client.post(
        selected_url,
        {"delete_selected_sarees": "yes", "selected_sarees": str(chiffon_saree.pk)},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("admin:store_category_change", args=[category.pk])
    assert Category.objects.filter(pk=category.pk).exists()
    assert not Saree.objects.filter(pk=chiffon_saree.pk).exists()
    assert Saree.objects.filter(pk=silk_saree.pk).exists()
    assert Saree.objects.filter(pk=basic_saree.pk).exists()


@pytest.mark.django_db
def test_category_saree_from_another_category_is_rejected(admin_user, client, category, basic_saree, chiffon_saree):
    client.force_login(admin_user)
    delete_url = reverse("admin:store_category_delete", args=[category.pk])
    selected_url = build_selected_delete_url(delete_url, "selected_sarees", [chiffon_saree.pk, basic_saree.pk])

    response = client.get(selected_url, follow=True)

    assert response.status_code == 200
    assert b"no longer in this category" in response.content
    assert Saree.objects.filter(pk=chiffon_saree.pk).exists()
    assert Saree.objects.filter(pk=basic_saree.pk).exists()


@pytest.mark.django_db
def test_order_confirmation_lists_only_the_ticked_items(admin_user, client, order_with_three_items):
    order, items = order_with_three_items
    client.force_login(admin_user)
    delete_url = reverse("admin:store_order_delete", args=[order.pk])
    selected_url = build_selected_delete_url(delete_url, "selected_items", [items[0].pk, items[1].pk])

    response = client.get(selected_url)

    assert response.status_code == 200
    assert b"Banarasi Moonlight Brocade" in response.content
    assert b"Patola Heritage Silk" in response.content
    assert b"Cotton Everyday Saree" not in response.content
    assert b"order and all unselected items will be kept" in response.content


@pytest.mark.django_db
def test_order_confirmation_deletes_only_the_ticked_items(admin_user, client, order_with_three_items):
    from decimal import Decimal

    order, items = order_with_three_items
    client.force_login(admin_user)
    delete_url = reverse("admin:store_order_delete", args=[order.pk])
    selected_url = build_selected_delete_url(delete_url, "selected_items", [items[0].pk, items[1].pk])

    response = client.post(
        selected_url,
        {"delete_selected_items": "yes", "selected_items": [str(items[0].pk), str(items[1].pk)]},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("admin:store_order_change", args=[order.pk])
    assert order.items.count() == 1
    assert order.items.get().name == "Cotton Everyday Saree"
    assert not OrderItem.objects.filter(pk__in=[items[0].pk, items[1].pk]).exists()

    order.refresh_from_db()
    assert order.subtotal == Decimal("999.00")
    assert order.delivery_charge == Decimal("0.00")
    assert order.gst == Decimal("49.95")
    assert order.total == Decimal("1048.95")


@pytest.mark.django_db
def test_order_selection_cannot_remove_every_item(admin_user, client, order_with_three_items):
    order, items = order_with_three_items
    client.force_login(admin_user)
    delete_url = reverse("admin:store_order_delete", args=[order.pk])
    selected_url = build_selected_delete_url(delete_url, "selected_items", [item.pk for item in items])

    response = client.get(selected_url)

    assert response.status_code == 200
    assert b"must keep at least one item" in response.content
    assert b"Yes, remove selected items" not in response.content


@pytest.mark.django_db
def test_saving_with_a_ticked_checkbox_still_keeps_the_category(
    admin_user, client, category, chiffon_saree, silk_saree
):
    """The other half of the flow: tick + Save removes the row, not the category."""
    client.force_login(admin_user)
    change_url = reverse("admin:store_category_change", args=[category.pk])
    response = client.get(change_url)
    formset = response.context["inline_admin_formsets"][0].formset
    prefix = formset.prefix

    client.post(
        change_url,
        {
            "title": category.title,
            "tier": category.tier,
            "slug": category.slug,
            "subtitle": "",
            "image": "",
            "order": "0",
            "_save": "Save",
            f"{prefix}-TOTAL_FORMS": str(formset.total_form_count()),
            f"{prefix}-INITIAL_FORMS": str(formset.initial_form_count()),
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-id": str(silk_saree.pk),
            f"{prefix}-1-id": str(chiffon_saree.pk),
            f"{prefix}-1-DELETE": "on",
        },
    )

    assert Category.objects.filter(pk=category.pk).exists()
    assert not Saree.objects.filter(pk=chiffon_saree.pk).exists()
    assert Saree.objects.filter(pk=silk_saree.pk).exists()

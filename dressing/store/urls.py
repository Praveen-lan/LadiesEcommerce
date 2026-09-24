from django.urls import path

from .views import (
    add_to_cart,
    cart_view,
    catalog,
    category_detail,
    checkout,
    generate_qr,
    home,
    login_view,
    logout_view,
    order_success,
    profile,
    remove_from_cart,
    saree_detail,
    update_cart,
    verify_otp,
)

app_name = "store"

urlpatterns = [
    path("", login_view, name="login"),
    path("verify-otp/", verify_otp, name="verify_otp"),
    path("logout/", logout_view, name="logout"),
    path("profile/", profile, name="profile"),
    path("home/", home, name="home"),
    path("catalog/", catalog, name="catalog"),
    path("catalog/<str:tier>/", category_detail, name="category_detail"),
    path("saree/<slug:slug>/", saree_detail, name="saree_detail"),
    path("cart/", cart_view, name="cart"),
    path("cart/add/", add_to_cart, name="add_to_cart"),
    path("cart/update/<int:saree_id>/", update_cart, name="update_cart"),
    path("cart/remove/<int:saree_id>/", remove_from_cart, name="remove_from_cart"),
    path("checkout/", checkout, name="checkout"),
    path("qr.png", generate_qr, name="generate_qr"),
    path("order/<str:order_id>/", order_success, name="order_success"),
]
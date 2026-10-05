from django.apps import AppConfig


class StoreConfig(AppConfig):
    name = 'store'

    def ready(self):
        from .converters import OrderIdConverter

        from django.urls import register_converter

        register_converter(OrderIdConverter, "order_id")
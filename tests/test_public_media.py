from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from store.public_media import PublicMediaFiles


class PublicMediaFilesTests(SimpleTestCase):
    def test_new_uploads_are_served_without_restarting_the_wsgi_wrapper(self):
        with TemporaryDirectory() as media_root:
            site_directory = Path(media_root) / "site"
            site_directory.mkdir()
            response_state = {}

            def fallback(environ, start_response):
                start_response("404 Not Found", [])
                return [b"not found"]

            with override_settings(MEDIA_ROOT=media_root):
                app = PublicMediaFiles(fallback)
                uploaded_logo = site_directory / "new-navbar-logo.png"
                uploaded_logo.write_bytes(b"image saved after server startup")

                body = app(
                    {"PATH_INFO": "/media/site/new-navbar-logo.png", "REQUEST_METHOD": "GET"},
                    lambda status, headers: response_state.update(status=status, headers=dict(headers)),
                )

            self.assertEqual(response_state["status"], "200 OK")
            self.assertEqual(response_state["headers"]["Content-Type"], "image/png")
            self.assertEqual(b"".join(body), b"image saved after server startup")

    def test_customer_profile_images_are_public(self):
        with TemporaryDirectory() as media_root:
            customer_directory = Path(media_root) / "customers"
            customer_directory.mkdir()
            (customer_directory / "profile.png").write_bytes(b"profile image")
            response_state = {}

            def fallback(environ, start_response):
                start_response("404 Not Found", [])
                return [b"not found"]

            with override_settings(MEDIA_ROOT=media_root):
                body = PublicMediaFiles(fallback)(
                    {"PATH_INFO": "/media/customers/profile.png", "REQUEST_METHOD": "GET"},
                    lambda status, headers: response_state.update(status=status, headers=dict(headers)),
                )

            self.assertEqual(response_state["status"], "200 OK")
            self.assertEqual(response_state["headers"]["Content-Type"], "image/png")
            self.assertEqual(b"".join(body), b"profile image")

    def test_standard_wsgi_application_serves_customer_profile_images(self):
        from sareeshop.wsgi import application

        with TemporaryDirectory() as media_root:
            customer_directory = Path(media_root) / "customers"
            customer_directory.mkdir()
            (customer_directory / "profile.png").write_bytes(b"profile image")
            response_state = {}

            def start_response(status, headers):
                response_state.update(status=status, headers=dict(headers))

            with override_settings(MEDIA_ROOT=media_root):
                body = application(
                    {
                        "PATH_INFO": "/media/customers/profile.png",
                        "REQUEST_METHOD": "GET",
                    },
                    start_response,
                )

            self.assertEqual(response_state["status"], "200 OK")
            self.assertEqual(response_state["headers"]["Content-Type"], "image/png")
            self.assertEqual(b"".join(body), b"profile image")

    def test_payment_receipts_are_not_public(self):
        with TemporaryDirectory() as media_root:
            private_directory = Path(media_root) / "payment-proofs"
            private_directory.mkdir()
            (private_directory / "receipt.png").write_bytes(b"private receipt")
            fallback_status = []

            def fallback(environ, start_response):
                start_response("404 Not Found", [])
                return [b"not found"]

            with override_settings(MEDIA_ROOT=media_root):
                body = PublicMediaFiles(fallback)(
                    {"PATH_INFO": "/media/payment-proofs/receipt.png", "REQUEST_METHOD": "GET"},
                    lambda status, headers: fallback_status.append(status),
                )

            self.assertEqual(fallback_status, ["404 Not Found"])
            self.assertEqual(b"".join(body), b"not found")

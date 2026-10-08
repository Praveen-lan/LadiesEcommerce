import mimetypes
from pathlib import Path

from django.core.exceptions import SuspiciousFileOperation

from django.conf import settings
from django.http import FileResponse, Http404


def serve_customer_profile_image(request, path):
    try:
        file_path = Path(settings.MEDIA_ROOT).joinpath("customers", path).resolve()
        file_path.relative_to((Path(settings.MEDIA_ROOT) / "customers").resolve())
    except (OSError, ValueError, SuspiciousFileOperation):
        raise Http404 from None

    if not file_path.is_file():
        raise Http404

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    response = FileResponse(file_path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "public, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class PublicMediaFiles:
    """Serve public image uploads dynamically without exposing private uploads."""

    public_directories = {"banners", "categories", "customers", "payment-qr", "sarees", "site"}
    chunk_size = 64 * 1024

    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        path_info = environ.get("PATH_INFO", "")
        if not path_info.startswith("/media/"):
            return self.application(environ, start_response)

        relative_path = path_info[len("/media/") :]
        parts = relative_path.split("/")
        if (
            len(parts) < 2
            or parts[0] not in self.public_directories
            or any(part in {"", ".", ".."} or "\\" in part or "\x00" in part for part in parts)
        ):
            return self.application(environ, start_response)

        media_root = Path(settings.MEDIA_ROOT).resolve()
        directory_root = (media_root / parts[0]).resolve()
        file_path = directory_root.joinpath(*parts[1:]).resolve()
        try:
            directory_root.relative_to(media_root)
            file_path.relative_to(directory_root)
        except ValueError:
            return self.application(environ, start_response)

        if not file_path.is_file():
            return self.application(environ, start_response)

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(file_path.stat().st_size)),
            ("Cache-Control", "public, max-age=300"),
            ("X-Content-Type-Options", "nosniff"),
        ]
        start_response("200 OK", headers)

        if environ.get("REQUEST_METHOD") == "HEAD":
            return []

        return self._read_file(file_path)

    def _read_file(self, file_path):
        with file_path.open("rb") as media_file:
            while chunk := media_file.read(self.chunk_size):
                yield chunk

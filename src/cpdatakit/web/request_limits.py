"""Authenticate uploads and bound multipart resources before FastAPI reads them."""

from __future__ import annotations

from fastapi.routing import APIRoute
from python_multipart.multipart import parse_options_header
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect

_FORM_BYTES = 2 * 1024 * 1024 + 64 * 1024
_FRAMING_BYTES = 1024 * 1024
_PART_HEADER_BYTES = 8192
_CHUNK_BYTES = 16 * 1024


class _UploadLimitExceeded(MultiPartException):
    pass


class _BoundedMultipartParser(MultiPartParser):
    """Count before queueing writes; own every opened spool until form cleanup."""

    def __init__(self, headers, stream, *, upload_limit, max_files):
        super().__init__(headers, stream, max_files=max_files, max_fields=64)
        self.upload_limit = upload_limit
        self.file_bytes = 0
        self.field_bytes = 0
        self.header_bytes = 0
        self.complete = False

    def on_part_begin(self):
        super().on_part_begin()
        self.header_bytes = 0

    def on_part_data(self, data, start, end):
        if self._current_part.file is None:
            self.field_bytes += end - start
            if (
                self.field_bytes > _FORM_BYTES
                or len(self._current_part.data) + end - start > self.max_part_size
            ):
                raise _UploadLimitExceeded("Form fields exceed the upload request budget.")
        else:
            self.file_bytes += end - start
            if self.file_bytes > self.upload_limit:
                raise _UploadLimitExceeded("Uploaded files exceed the configured size limit.")
        super().on_part_data(data, start, end)

    def _count_header(self, count):
        self.header_bytes += count
        if self.header_bytes > _PART_HEADER_BYTES:
            raise _UploadLimitExceeded("Multipart headers exceed the request budget.")

    def on_header_field(self, data, start, end):
        self._count_header(end - start)
        super().on_header_field(data, start, end)

    def on_header_value(self, data, start, end):
        self._count_header(end - start)
        super().on_header_value(data, start, end)

    def on_headers_finished(self):
        try:
            super().on_headers_finished()
        except MultiPartException as exc:
            if self._current_files > self.max_files or self._current_fields > self.max_fields:
                raise _UploadLimitExceeded("Too many multipart files or fields.") from exc
            raise

    def on_end(self):
        self.complete = True

    async def parse(self):
        try:
            result = await super().parse()
            if not self.complete:
                raise MultiPartException("Incomplete multipart body.")
            return result
        except BaseException:
            # Also required with older supported Starlette versions whose
            # parser only closes spools on MultiPartException, not disconnects.
            for file in self._files_to_close_on_error:
                file.close()
            raise


async def _bounded_stream(request, limit):
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise _UploadLimitExceeded("Multipart request exceeds the size limit.")
        # ASGI servers choose their own receive-frame sizes. Bound parser work
        # and write queues even if a server supplies the whole body at once.
        for offset in range(0, len(chunk), _CHUNK_BYTES):
            yield chunk[offset : offset + _CHUNK_BYTES]


def upload_route_class(*, upload_limit, require_session, require_csrf, json_error):
    """Install on app.router before routes are registered; no global parser edits."""

    class BoundedUploadRoute(APIRoute):
        def get_route_handler(self):
            original = super().get_route_handler()
            file_limit = (
                min(upload_limit, 1024 * 1024) if self.path.endswith("/schemas") else upload_limit
            )
            max_files = 1000 if self.path.endswith("/inspect-zarr") else 1
            request_limit = file_limit + _FORM_BYTES + _FRAMING_BYTES

            async def handler(request):
                if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
                    return await original(request)
                error = require_session(request)
                if error is None and "X-CSRF-Token" in request.headers:
                    error = require_csrf(request)
                if error is not None:
                    return error
                media_type, _ = parse_options_header(request.headers.get("content-type"))
                if media_type.lower() != b"multipart/form-data":
                    return await original(request)

                form = None
                try:
                    content_length = request.headers.get("content-length")
                    if content_length is not None:
                        try:
                            length = int(content_length)
                        except ValueError as exc:
                            raise MultiPartException("Invalid Content-Length.") from exc
                        if length < 0:
                            raise MultiPartException("Invalid Content-Length.")
                        if length > request_limit:
                            raise _UploadLimitExceeded("Multipart request exceeds the size limit.")
                    parser = _BoundedMultipartParser(
                        request.headers,
                        _bounded_stream(request, request_limit),
                        upload_limit=file_limit,
                        max_files=max_files,
                    )
                    form = await parser.parse()
                    error = require_csrf(request, form.get("csrf_token"))
                    if error is not None:
                        return error
                    # FastAPI calls request.form() before dependencies. Reuse
                    # this bounded result instead of parsing and spooling twice.
                    request._form = form
                    return await original(request)
                except _UploadLimitExceeded:
                    return json_error(
                        413,
                        "upload_too_large",
                        "The upload exceeds the configured request limit.",
                        "Choose smaller files or increase the local upload limit.",
                    )
                except (MultiPartException, ClientDisconnect):
                    return json_error(
                        400,
                        "upload_rejected",
                        "The multipart upload is incomplete or invalid.",
                        "Select the file again and retry the upload.",
                    )
                finally:
                    if form is not None:
                        # Async close delegates rolled files to a worker; an
                        # already cancelled request may skip that await. These
                        # are our own temporary files and must close now.
                        for _, value in form.multi_items():
                            if isinstance(value, UploadFile):
                                value.file.close()

            return handler

    return BoundedUploadRoute

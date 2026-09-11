from __future__ import annotations

from flask import Response, redirect, request

from .config import NOTICE_PASSWORD_FILE, PASSWORD_FILE, PRINT_ADMIN_PASSWORD_FILE
from .storage import check_password, read_password_hash


def _basic_auth_required(f, *, password_path, realm: str, message: str, setup_response=None):
    import functools

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if setup_response is not None and not read_password_hash(password_path):
            return setup_response()
        auth = request.authorization
        if not auth or not check_password(auth.password, password_path):
            return Response(
                message,
                401,
                {"WWW-Authenticate": f'Basic realm="{realm}"'},
            )
        return f(*args, **kwargs)

    return decorated


def require_admin(f):
    return _basic_auth_required(
        f,
        password_path=PASSWORD_FILE,
        realm="Propared Calendar Displays Admin",
        message="Admin access required.",
        setup_response=lambda: redirect("/admin/setup"),
    )


def require_notice_auth(f):
    return _basic_auth_required(
        f,
        password_path=NOTICE_PASSWORD_FILE,
        realm="Notice Board",
        message="Notice access required.",
    )


def require_shared_media_auth(f):
    return _basic_auth_required(
        f,
        password_path=NOTICE_PASSWORD_FILE,
        realm="Notice Board",
        message="Shared media access required.",
        setup_response=lambda: Response("Shared media password not set. Visit /media-admin first.", 403),
    )


def require_print_admin_auth(f):
    return _basic_auth_required(
        f,
        password_path=PRINT_ADMIN_PASSWORD_FILE,
        realm="Print Admin",
        message="Print Admin access required.",
        setup_response=lambda: Response("Print Admin password not set. Visit /print-admin/setup first.", 403),
    )

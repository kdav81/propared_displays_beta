from __future__ import annotations

from flask import Response, redirect, request

from .config import NOTICE_PASSWORD_FILE, PASSWORD_FILE
from .storage import check_password, read_password_hash


def require_admin(f):
    import functools

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not read_password_hash(PASSWORD_FILE):
            return redirect("/admin/setup")
        auth = request.authorization
        if not auth or not check_password(auth.password, PASSWORD_FILE):
            return Response(
                "Admin access required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Propared Calendar Displays Admin"'},
            )
        return f(*args, **kwargs)

    return decorated


def require_notice_auth(f):
    import functools

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_password(auth.password, NOTICE_PASSWORD_FILE):
            return Response(
                "Notice access required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Notice Board"'},
            )
        return f(*args, **kwargs)

    return decorated


def require_shared_media_auth(f):
    import functools

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not read_password_hash(NOTICE_PASSWORD_FILE):
            return Response("Shared media password not set. Visit /media-admin first.", 403)
        auth = request.authorization
        if not auth or not check_password(auth.password, NOTICE_PASSWORD_FILE):
            return Response(
                "Shared media access required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Notice Board"'},
            )
        return f(*args, **kwargs)

    return decorated


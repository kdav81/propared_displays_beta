from __future__ import annotations

import functools

from flask import Response, redirect, request

from classroom_server.core import NOTICE_PASSWORD_FILE, PASSWORD_FILE
from classroom_server.storage import check_pw, read_pw_file


def require_admin(func):
    @functools.wraps(func)
    def decorated(*args, **kwargs):
        if not read_pw_file(PASSWORD_FILE):
            return redirect("/admin/setup")
        auth = request.authorization
        if not auth or not check_pw(auth.password, PASSWORD_FILE):
            return Response(
                "Admin access required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Classroom Display Admin"'},
            )
        return func(*args, **kwargs)

    return decorated


def require_notice_auth(func):
    @functools.wraps(func)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_pw(auth.password, NOTICE_PASSWORD_FILE):
            return Response(
                "Notice access required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Notice Board"'},
            )
        return func(*args, **kwargs)

    return decorated


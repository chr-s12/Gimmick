"""Helpers shared by every Blueprint (SDS 2.3.1, Controller Layer)."""
from functools import wraps

from flask import abort, current_app, g


def svc(name: str):
    """One of the services built in app.create_app: accounts, routines, availability, booking,
    clientele, occupancy, reports, notifications."""
    return current_app.extensions["gymmick"][name]


def myId() -> str:
    return g.user["uwiId"]


def rolesAllowed(*roles):
    """Checked on every request, not just when a page first loads (SRS 3.2.2)."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.get("user") is None or g.user.get("role") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def formRows(form, *names):
    """Lists of repeated form fields, e.g. the builder's exercise rows."""
    return [form.getlist(n) for n in names]

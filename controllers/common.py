"""Helpers shared by every Blueprint (SDS 2.3.1, Controller Layer)."""
from functools import wraps

from flask import abort, current_app, g, request

OUT_OF_SCOPE = "This is outside what your account can do."
# What a user with the wrong role is told (test plan TC-0.1.3, TC-0.6.7, TC-07.13)
DENIED_MESSAGES = {
    "clients.assign": "Only personal trainers can assign routines to students.",
    "clients": "Only personal trainers can view clients.",
    "reports": "Only the gym operator can generate or export usage reports.",
    "availability": "Only personal trainers can manage availability and respond to bookings.",
    "booking": "Only students can book trainers.",
    "progress": "Only students can log workouts and view their progress.",
    "routines": "Only students and personal trainers can build routines.",
    "occupancy.member": "Only students can view the member occupancy page and request entry.",
    "occupancy.memberStatus": "Only students can view the member occupancy page and request entry.",
    "occupancy.requestEntry": "Only students can view the member occupancy page and request entry.",
    "occupancy": "Only gym staff can use the front desk.",
    "home.settings": "Only students and personal trainers have profile settings.",
    "home.resetPassword": "Only gym staff can reset passwords.",
    "home.backup": "Only the gym operator can download a backup.",
}


def deny():
    """Stop the request with a 403 that says who the page is for."""
    endpoint = request.endpoint or ""
    message = DENIED_MESSAGES.get(endpoint) or DENIED_MESSAGES.get(endpoint.split(".")[0])
    abort(403, description=f"{message} {OUT_OF_SCOPE}" if message else None)


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
                deny()
            return view(*args, **kwargs)
        return wrapped
    return decorator


def formRows(form, *names):
    """Lists of repeated form fields, e.g. the builder's exercise rows."""
    return [form.getlist(n) for n in names]

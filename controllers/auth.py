"""Sign-up, login and logout (SRS 3.2.2)."""
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from accounts import AccountError, LoginError

from .common import svc

auth = Blueprint("auth", __name__)


def _safeNext(target: str) -> str:
    """Only follow links back into this app after login."""
    if target and target.startswith("/") and not urlparse(target).netloc and not target.startswith("//"):
        return target
    return url_for("home.index")


@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uwiId = request.form.get("uwiId", "")
        try:
            user = svc("accounts").login(uwiId, request.form.get("password", ""))
        except LoginError as e:
            flash(str(e), "error")
            return render_template("auth/login.html", uwiId=uwiId), 401
        session.clear()
        session.permanent = True
        session["uwiId"] = user["uwiId"]
        flash(f"Welcome back, {user['name']}.", "success")
        return redirect(_safeNext(request.form.get("next", "")))
    if session.get("uwiId"):
        return redirect(url_for("home.index"))
    return render_template("auth/login.html", uwiId="", next=request.args.get("next", ""))


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    form = request.form
    if request.method == "POST":
        try:
            user = svc("accounts").register(form.get("uwiId"), form.get("name"), form.get("password"),
                                            form.get("confirm"), form.get("role"), form.get("specialisations"),
                                            form.get("bio"))
        except AccountError as e:
            flash(str(e), "error")
            return render_template("auth/signup.html", form=form), 400
        session.clear()
        session.permanent = True
        session["uwiId"] = user["uwiId"]
        flash("Your account is ready.", "success")
        return redirect(url_for("home.index"))
    return render_template("auth/signup.html", form={})


@auth.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))

"""Loopback-only enrollment tool. The runtime, never Flask, owns the camera."""

from collections import deque
from datetime import timedelta
from functools import wraps
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit


def _authority(value):
    try:
        parsed = urlsplit("http://" + value)
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return None
        if parsed.hostname not in ("localhost", "127.0.0.1"):
            return None
        return parsed.hostname, parsed.port or 80
    except (ValueError, TypeError):
        return None


def local_request_allowed(host, origin):
    """Reject DNS rebinding and cross-origin requests, including other local ports."""
    authority = _authority(host)
    if authority is None:
        return False
    if origin is None:
        return True
    try:
        parsed = urlsplit(origin)
        if parsed.scheme != "http" or parsed.path or parsed.query or parsed.fragment:
            return False
        return _authority(parsed.netloc) == authority
    except (ValueError, TypeError):
        return False


class LoginLimiter:
    """Bounded process-local throttle; lockout expires without a background task."""

    def __init__(self, limit=5, window=60):
        self.limit = limit
        self.window = window
        self.failures = deque(maxlen=limit)
        self.lock = threading.Lock()

    def allowed(self, now):
        with self.lock:
            while self.failures and now - self.failures[0] >= self.window:
                self.failures.popleft()
            return len(self.failures) < self.limit

    def failure(self, now):
        with self.lock:
            self.failures.append(now)

    def success(self):
        with self.lock:
            self.failures.clear()


def private_secret(state_dir):
    """Create a durable session key atomically, never in the checkout."""
    state_dir = Path(state_dir)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = state_dir / "session.key"
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink():
            raise ValueError("Session key cannot be a symbolic link.")
    else:
        with os.fdopen(fd, "wb") as stream:
            stream.write(secrets.token_bytes(32))
    os.chmod(str(path), 0o600)
    key = path.read_bytes()
    if len(key) < 32:
        raise ValueError("Session key is invalid; regenerate it with the service stopped.")
    return key


def create_app(store, control, state_dir):
    """Build the authenticated local setup app around the running module.

    No hardware imports occur here. `control` owns capture and transient samples.
    The caller must serve this application ONLY on 127.0.0.1.
    """
    from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
    from flask_wtf import CSRFProtect, FlaskForm
    from wtforms import BooleanField, PasswordField, StringField, TextAreaField
    from wtforms.validators import InputRequired, Length, Optional
    from werkzeug.security import check_password_hash

    state_dir = Path(state_dir)
    app = Flask(__name__)
    app.secret_key = private_secret(state_dir)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=False,  # loopback HTTP; never expose on a network
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=15),
        MAX_CONTENT_LENGTH=16 * 1024,
        WTF_CSRF_TIME_LIMIT=15 * 60,
    )
    limiter = LoginLimiter()

    class ActionForm(FlaskForm):
        pass

    class LoginForm(FlaskForm):
        password = PasswordField(
            "Caregiver password", validators=[InputRequired(), Length(max=256)]
        )

    class PersonForm(FlaskForm):
        name = StringField("Name", validators=[InputRequired(), Length(max=100)])
        relationship = StringField(
            "Relationship to wearer", validators=[Optional(), Length(max=100)]
        )
        pronunciation = StringField(
            "Name pronunciation (optional)", validators=[Optional(), Length(max=100)]
        )
        note = TextAreaField(
            "Caregiver-approved contextual note", validators=[Optional(), Length(max=500)]
        )
        active = BooleanField("Allow recognition", default=True)
        confirmed = BooleanField("I confirm these samples belong to this person")

    @app.before_request
    def local_only():
        if not local_request_allowed(request.host, request.headers.get("Origin")):
            abort(403)
        if request.remote_addr not in ("127.0.0.1", "::1"):
            abort(403)
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            abort(403)

    CSRFProtect(app)

    @app.after_request
    def private_headers(response):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        return response

    def authenticated(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("authenticated"):
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    def checked_action():
        form = ActionForm()
        if not form.validate_on_submit():
            abort(400)
        return form

    def existing(person_id):
        person = store.person(person_id)
        if person is None:
            abort(404)
        return person

    @app.route("/login", methods=["GET", "POST"])
    def login():
        password_path = state_dir / "password.hash"
        if not password_path.is_file() or password_path.is_symlink():
            return (
                render_template(
                    "message.html",
                    title="Setup required",
                    message="Set the caregiver password using the cognisight password command on this Pi.",
                ),
                503,
            )
        form = LoginForm()
        if request.method == "POST":
            if not limiter.allowed(time.monotonic()):
                return (
                    render_template(
                        "message.html",
                        title="Please wait",
                        message="Too many unsuccessful attempts. Try again in one minute.",
                    ),
                    429,
                )
            if form.validate_on_submit():
                try:
                    password_hash = password_path.read_text().strip()
                    valid = check_password_hash(password_hash, form.password.data)
                except (OSError, ValueError):
                    valid = False
                if valid:
                    limiter.success()
                    session.clear()
                    session["authenticated"] = True
                    session.permanent = True
                    return redirect(url_for("index"))
                limiter.failure(time.monotonic())
                flash("Password not accepted.")
        return render_template("login.html", form=form)

    @app.post("/logout")
    @authenticated
    def logout():
        checked_action()
        control.cancel_enrollment()
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @authenticated
    def index():
        return render_template(
            "index.html", people=store.people(), health=control.status(), action=ActionForm()
        )

    @app.post("/enroll/begin")
    @authenticated
    def begin():
        checked_action()
        try:
            control.begin_enrollment()
        except (ValueError, RuntimeError):
            flash("Unable to start enrollment. Check camera and module health.")
            return redirect(url_for("index"))
        session.pop("enrollment_target", None)
        return redirect(url_for("enroll"))

    @app.post("/people/<person_id>/samples")
    @authenticated
    def more_samples(person_id):
        checked_action()
        existing(person_id)
        try:
            control.begin_enrollment(person_id)
        except (ValueError, RuntimeError):
            flash("Unable to start additional capture. Check module health.")
            return redirect(url_for("index"))
        session["enrollment_target"] = person_id
        return redirect(url_for("enroll"))

    def enrollment_page(form=None, code=200):
        target = (
            store.person(session.get("enrollment_target"))
            if session.get("enrollment_target")
            else None
        )
        form = form if form is not None else PersonForm(data=target or {})
        return (
            render_template(
                "enroll.html",
                form=form,
                target=target,
                action=ActionForm(),
                health=control.status(),
            ),
            code,
        )

    @app.get("/enroll")
    @authenticated
    def enroll():
        return enrollment_page()

    @app.post("/enroll/capture")
    @authenticated
    def capture():
        checked_action()
        try:
            result = control.capture_sample()
            if result["accepted"]:
                flash("Accepted sample %s. Continue with varied views." % result["count"])
            else:
                flash("Sample not accepted: %s" % result["reason"])
        except (ValueError, RuntimeError):
            flash("Capture unavailable. Check camera status and restart enrollment if necessary.")
        return redirect(url_for("enroll"))

    @app.post("/enroll/cancel")
    @authenticated
    def cancel():
        checked_action()
        control.cancel_enrollment()
        session.pop("enrollment_target", None)
        flash("Enrollment cancelled. Samples discarded.")
        return redirect(url_for("index"))

    @app.post("/enroll/finish")
    @authenticated
    def finish():
        form = PersonForm()
        if not form.validate_on_submit() or not form.confirmed.data:
            flash("Enter a name and confirm the identity of the captured person.")
            return enrollment_page(form, 400)
        try:
            control.finish_enrollment(
                form.name.data.strip(),
                (form.relationship.data or "").strip(),
                (form.note.data or "").strip(),
                (form.pronunciation.data or "").strip(),
            )
        except ValueError as error:
            flash(str(error))
            return enrollment_page(form, 400)
        except (RuntimeError, OSError):
            flash("Enrollment could not be saved. Check module and storage status.")
            return enrollment_page(form, 503)
        session.pop("enrollment_target", None)
        flash("Face samples saved. Recognition will resume.")
        return redirect(url_for("index"))

    @app.route("/people/<person_id>", methods=["GET", "POST"])
    @authenticated
    def edit(person_id):
        person = existing(person_id)
        form = PersonForm(data=person)
        if request.method == "POST" and form.validate_on_submit():
            try:
                store.update(
                    person_id,
                    form.name.data.strip(),
                    (form.relationship.data or "").strip(),
                    (form.note.data or "").strip(),
                    (form.pronunciation.data or "").strip(),
                    bool(form.active.data),
                )
            except ValueError as error:
                flash(str(error))
                return (
                    render_template("person.html", form=form, person=person, action=ActionForm()),
                    400,
                )
            flash("Profile updated.")
            return redirect(url_for("index"))
        return render_template("person.html", form=form, person=person, action=ActionForm()), (
            400 if request.method == "POST" else 200
        )

    @app.post("/people/<person_id>/delete")
    @authenticated
    def delete(person_id):
        checked_action()
        existing(person_id)
        store.delete(person_id)
        flash("Profile, face samples, and associated recognition history deleted.")
        return redirect(url_for("index"))

    @app.post("/history/clear")
    @authenticated
    def clear_history():
        checked_action()
        control.clear_history()
        flash("Recognition history cleared.")
        return redirect(url_for("index"))

    return app

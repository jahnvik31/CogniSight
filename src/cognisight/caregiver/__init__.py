"""Read-only caregiver monitoring; camera/enrollment remain private to the Pi."""

from .web import create_dashboard_app, create_dashboard_blueprint

__all__ = ["create_dashboard_app", "create_dashboard_blueprint"]

from flask import Blueprint, render_template

from routes.helpers import login_required, services

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    return render_template("dashboard.html", data=services().dashboard.summary(),
                           multiplier=services().settings.price_multiplier)

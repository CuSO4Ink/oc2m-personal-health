from flask import Blueprint, jsonify


system_bp = Blueprint("system", __name__)


@system_bp.get("/health")
def health_check():
    return jsonify({"status": "ok", "service": "personal-health-api"})


@system_bp.get("/modules")
def modules():
    return jsonify(
        {
            "modules": [
                {"key": "overview", "name": "Overview", "status": "in-development"},
                {"key": "records", "name": "Health Records", "status": "in-development"},
                {"key": "insights", "name": "Health Insights", "status": "planned"},
                {"key": "sharing", "name": "Sharing & Privacy", "status": "planned"},
                {"key": "services", "name": "Care Services", "status": "planned"},
                {"key": "community", "name": "Community", "status": "optional"},
            ]
        }
    )


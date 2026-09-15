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
                {"key": "overview", "name": "Overview", "status": "implemented"},
                {"key": "records", "name": "Health Records", "status": "implemented"},
                {"key": "insights", "name": "Health Insights", "status": "implemented"},
                {"key": "sharing", "name": "Sharing & Privacy", "status": "implemented"},
                {"key": "services", "name": "Care Services", "status": "implemented"},
                {"key": "community", "name": "Community", "status": "implemented"},
            ]
        }
    )

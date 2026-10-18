import os
from dataclasses import dataclass


@dataclass
class CameraSpec:
    """One monitored space: a video source plus the detector settings
    specific to it. Passed to CameraProcessor.add_camera() via main.py."""
    name: str
    source: str              # RTSP URL, device index as string ("0"), or file path
    max_capacity: int = None
    count_threshold: int = 15
    density_threshold: float = None
    roi: list = None
    use_sahi: bool = False
    output_path: str = None  # None = don't save an annotated video for this camera


# Replace with real cameras, or load this list from JSON/YAML/DB instead.
DEFAULT_CAMERAS = [
    CameraSpec(name="Library Reading Hall", source="0",
               max_capacity=60, count_threshold=50),
    CameraSpec(name="Seminar Hall A", source="rtsp://192.168.1.10:554/stream1",
               max_capacity=150, count_threshold=120, use_sahi=True),
    CameraSpec(name="CS Lab 2", source="rtsp://192.168.1.11:554/stream1",
               max_capacity=40, count_threshold=35),
]

NOTIFICATION = {
    "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "587")),
    "smtp_user": os.getenv("SMTP_USER", ""),
    "smtp_password": os.getenv("SMTP_PASSWORD", ""),
    "alert_emails": [e for e in os.getenv("ALERT_EMAILS", "").split(",") if e],

    "twilio_sid": os.getenv("TWILIO_SID", ""),
    "twilio_auth_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
    "twilio_from": os.getenv("TWILIO_FROM", ""),
    "alert_phones": [p for p in os.getenv("ALERT_PHONES", "").split(",") if p],

    "enable_mqtt": os.getenv("ENABLE_MQTT", "false").lower() == "true",
    "mqtt_broker": os.getenv("MQTT_BROKER", "localhost"),
    "mqtt_port": int(os.getenv("MQTT_PORT", "1883")),
}

DB_PATH = os.getenv("DB_PATH", "campus_monitoring.db")
MODEL_PATH = os.getenv("MODEL_PATH", "yolov8n.pt")
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "120"))
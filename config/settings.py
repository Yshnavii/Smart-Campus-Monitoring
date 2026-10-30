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


# One entry per room. Each name must be unique: it is the room button in the dashboard.
# The sources below all play download.mp4 as a stand-in; replace each with that room's
# own camera. A webcam ("0") can only be used by one room at a time.
DEFAULT_CAMERAS = [
    CameraSpec(name="Classroom 1", source="0",
               max_capacity=30, count_threshold=15),            # laptop webcam
    CameraSpec(name="Library", source="http://10.218.239.114:8080/video",
               max_capacity=60, count_threshold=15),            # phone camera
    CameraSpec(name="Lab A", source="tcp://192.168.1.60:8888",
               max_capacity=20, count_threshold=15),            # Raspberry Pi
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
DB_LOG_INTERVAL_SECONDS = int(os.getenv("DB_LOG_INTERVAL_SECONDS", "5"))
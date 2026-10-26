import argparse

from config.settings import DEFAULT_CAMERAS, NOTIFICATION, DB_PATH, MODEL_PATH, ALERT_COOLDOWN_SECONDS
from detectors.yolo_detector import OvercrowdingDetector
from detectors.sahi_detector import SAHIOvercrowdingDetector
from processors.camera_processor import CameraProcessor
from alerts.alert_handler import AlertHandler
from alerts.notifiers import EmailNotifier, SMSNotifier, MQTTNotifier
from utils.database import Database


def build_detector(camera_spec):
    kwargs = dict(
        model_path=MODEL_PATH,
        count_threshold=camera_spec.count_threshold,
        density_threshold=camera_spec.density_threshold,
        roi=camera_spec.roi,
        max_capacity=camera_spec.max_capacity,
    )
    if camera_spec.use_sahi:
        return SAHIOvercrowdingDetector(**kwargs)
    return OvercrowdingDetector(**kwargs)


def build_notifiers():
    notifiers = []
    if NOTIFICATION["smtp_user"]:
        notifiers.append(EmailNotifier(
            NOTIFICATION["smtp_host"], NOTIFICATION["smtp_port"],
            NOTIFICATION["smtp_user"], NOTIFICATION["smtp_password"],
            NOTIFICATION["alert_emails"],
        ))
    if NOTIFICATION["twilio_sid"]:
        notifiers.append(SMSNotifier(
            NOTIFICATION["twilio_sid"], NOTIFICATION["twilio_auth_token"],
            NOTIFICATION["twilio_from"], NOTIFICATION["alert_phones"],
        ))
    if NOTIFICATION["enable_mqtt"]:
        notifiers.append(MQTTNotifier(NOTIFICATION["mqtt_broker"], NOTIFICATION["mqtt_port"]))
    return notifiers


def main():
    parser = argparse.ArgumentParser(description="Smart Campus Monitoring")
    parser.add_argument("--display", action="store_true", help="Show annotated video windows")
    args = parser.parse_args()

    database = Database(DB_PATH)
    alert_handler = AlertHandler(build_notifiers(), database=database,
                                  cooldown_seconds=ALERT_COOLDOWN_SECONDS)

    camera_processor = CameraProcessor()
    for camera_spec in DEFAULT_CAMERAS:
        detector = build_detector(camera_spec)
        detector.warmup()
        camera_processor.add_camera(
            camera_name=camera_spec.name,
            source=camera_spec.source,
            detector=detector,
            output_path=camera_spec.output_path,
            alert_callback=alert_handler.process,
            result_callback=database.insert_detection,
        )
        print(f"Registered: {camera_spec.name} ({camera_spec.source})")

    camera_processor.start_all(display=args.display)
    try:
        camera_processor.join_all()
    except KeyboardInterrupt:
        print("Shutting down...")
        camera_processor.stop_all()


if __name__ == "__main__":
    main()
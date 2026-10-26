import smtplib
import ssl
from abc import ABC, abstractmethod
from email.mime.text import MIMEText


class BaseNotifier(ABC):
    @abstractmethod
    def send(self, subject, message):
        """Send a notification. Returns True on success."""
        raise NotImplementedError


class EmailNotifier(BaseNotifier):
    def __init__(self, smtp_host, smtp_port, smtp_user, smtp_password, recipients):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.recipients = [r for r in recipients if r]

    def send(self, subject, message):
        if not self.recipients:
            return False
        try:
            msg = MIMEText(message)
            msg["Subject"] = subject
            msg["From"] = self.smtp_user
            msg["To"] = ", ".join(self.recipients)

            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, self.recipients, msg.as_string())
            return True
        except Exception as exc:
            print(f"[EmailNotifier] Failed to send email: {exc}")
            return False


class SMSNotifier(BaseNotifier):
    def __init__(self, twilio_sid, twilio_auth_token, twilio_from_number, phone_numbers):
        self.from_number = twilio_from_number
        self.phone_numbers = [p for p in phone_numbers if p]
        self._client = None
        if twilio_sid and twilio_auth_token:
            from twilio.rest import Client
            self._client = Client(twilio_sid, twilio_auth_token)

    def send(self, subject, message):
        if not self._client or not self.phone_numbers:
            return False
        ok = True
        for number in self.phone_numbers:
            try:
                self._client.messages.create(body=f"{subject}: {message}",
                                              from_=self.from_number, to=number)
            except Exception as exc:
                print(f"[SMSNotifier] Failed to text {number}: {exc}")
                ok = False
        return ok


class MQTTNotifier(BaseNotifier):
    def __init__(self, broker, port, topic_prefix="campus/monitoring"):
        self.topic_prefix = topic_prefix
        import paho.mqtt.client as mqtt
        self._client = mqtt.Client()
        try:
            self._client.connect(broker, port, keepalive=30)
        except Exception as exc:
            print(f"[MQTTNotifier] Could not connect to broker: {exc}")

    def send(self, subject, message):
        topic = f"{self.topic_prefix}/alerts"
        try:
            self._client.publish(topic, f"{subject}|{message}", qos=1)
            return True
        except Exception as exc:
            print(f"[MQTTNotifier] Publish failed: {exc}")
            return False
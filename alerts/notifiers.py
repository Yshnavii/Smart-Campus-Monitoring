import smtplib
import ssl
from abc import ABC, abstractmethod
from email.mime.text import MIMEText

from utils import alert_settings


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

    def _credentials(self):
        """(sender, password, recipients) to use for the next send."""
        return self.smtp_user, self.smtp_password, self.recipients

    def send_detailed(self, subject, message):
        """Returns (ok, error_text). The error text never contains the password."""
        user, password, recipients = self._credentials()
        if not recipients:
            return False, "No recipient emails are set."
        if not user or not password:
            return False, "Sender email or app password is missing."
        try:
            msg = MIMEText(message)
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = ", ".join(recipients)

            context = ssl.create_default_context()
            use_ssl = int(self.smtp_port) == 465   # 465 = implicit SSL, 587 = STARTTLS
            if use_ssl:
                server_cm = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=20, context=context)
            else:
                server_cm = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20)
            with server_cm as server:
                if not use_ssl:
                    server.starttls(context=context)
                server.login(user, password)
                server.sendmail(user, recipients, msg.as_string())
            return True, ""
        except smtplib.SMTPAuthenticationError:
            return False, ("The mail server rejected the login. Check the sender email and use an "
                           "app password (Gmail needs 2-step verification), not the normal password.")
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def send(self, subject, message):
        ok, error = self.send_detailed(subject, message)
        if not ok:
            print(f"[EmailNotifier] Failed to send email: {error}")
        return ok


class DynamicEmailNotifier(EmailNotifier):
    """
    EmailNotifier that reads the sender, app password and recipients saved from
    the dashboard each time it sends, so changes apply to the next alert without
    restarting main.py. The values passed to the constructor are only a fallback
    for when nothing has been saved yet.
    """

    def __init__(self, smtp_host, smtp_port, fallback_user="", fallback_password="",
                 fallback_recipients=()):
        super().__init__(smtp_host, smtp_port, fallback_user, fallback_password,
                         list(fallback_recipients))

    def _credentials(self):
        saved = alert_settings.load()
        if saved["sender_email"] and saved["app_password"]:
            user, password = saved["sender_email"], saved["app_password"]
        else:
            user, password = self.smtp_user, self.smtp_password
        saved_recipients = [e.strip() for e in saved["recipients"].split(",") if e.strip()]
        return user, password, (saved_recipients or self.recipients)


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
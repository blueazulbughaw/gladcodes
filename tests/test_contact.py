import smtplib
import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from services import mail


class ContactEmailTests(unittest.TestCase):
    """The form used to send to hello@gladcodes.com, a domain that doesn't
    exist, so Exim refused every message (550). Mail now goes to the admin
    Settings "Contact email" (MAIL_TO only as fallback), and failures log."""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, MAIL_TO="", SMTP_USER="", MAIL_FROM="noreply@glad.codes")

    def test_recipient_defaults_to_settings_contact_email(self):
        with self.app.app_context(), patch("services.mail.query_one", return_value={"setting_value": " glad@example.com "}):
            self.assertEqual(mail.contact_recipient(), "glad@example.com")

    def test_settings_contact_email_beats_a_stale_mail_to(self):
        self.app.config["MAIL_TO"] = "hello@gladcodes.com"
        with self.app.app_context(), patch("services.mail.query_one", return_value={"setting_value": "hello@glad.codes"}):
            self.assertEqual(mail.contact_recipient(), "hello@glad.codes")

    def test_mail_to_is_the_fallback_when_settings_is_empty(self):
        self.app.config["MAIL_TO"] = "fallback@example.com"
        with self.app.app_context(), patch("services.mail.query_one", return_value={"setting_value": ""}):
            self.assertEqual(mail.contact_recipient(), "fallback@example.com")

    def test_no_recipient_fails_cleanly_without_smtp(self):
        with self.app.app_context(), patch("services.mail.query_one", return_value=None), \
             patch("services.mail.smtplib.SMTP") as smtp:
            self.assertFalse(mail.send_contact_email("A", "a@b.co", "Surprise Me", "hi"))
            smtp.assert_not_called()

    def test_sends_to_contact_email_with_reply_to_sender(self):
        server = MagicMock()
        with self.app.app_context(), patch("services.mail.query_one", return_value={"setting_value": "glad@example.com"}), \
             patch("services.mail.smtplib.SMTP") as smtp:
            smtp.return_value.__enter__.return_value = server
            self.assertTrue(mail.send_contact_email("Ana", "ana@ex.com", "I Have a Job for You", "Let's talk"))
        sent = server.send_message.call_args[0][0]
        self.assertEqual(sent["To"], "glad@example.com")
        self.assertEqual(sent["Reply-To"], "ana@ex.com")
        self.assertIn("I Have a Job for You", sent["Subject"])

    def test_refused_recipient_is_logged_and_returns_false(self):
        server = MagicMock()
        server.send_message.side_effect = smtplib.SMTPRecipientsRefused({"x@gladcodes.com": (550, b"no such domain")})
        with self.app.app_context(), patch("services.mail.query_one", return_value={"setting_value": "x@gladcodes.com"}), \
             patch("services.mail.smtplib.SMTP") as smtp, self.assertLogs("services.mail", level="ERROR") as logs:
            smtp.return_value.__enter__.return_value = server
            self.assertFalse(mail.send_contact_email("A", "a@b.co", "Surprise Me", "hi"))
        self.assertIn("SMTPRecipientsRefused", logs.output[0])


class ContactPageTests(unittest.TestCase):
    def setUp(self):
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_page_uses_subject_dropdown_and_card_layout(self):
        with patch("blueprints.public.routes.query", return_value=[{"setting_key": "contact_email", "setting_value": "glad@example.com"}]):
            body = self.client.get("/contact").get_data(as_text=True)
        self.assertIn('<select name="subject" required>', body)
        self.assertIn('<option value="I Have a Job for You" >', body)
        self.assertNotIn("contact-chip", body)
        self.assertIn('href="mailto:glad@example.com"', body)
        self.assertNotIn('class="closing-cta"', body)
        self.assertNotIn("gc-admin", body)

    @patch("blueprints.public.routes.send_contact_email", return_value=True)
    def test_valid_post_sends_and_confirms(self, send):
        with patch("blueprints.public.routes.query", return_value=[]):
            resp = self.client.post("/contact", data={"name": "Ana", "email": "ana@ex.com", "subject": "Surprise Me", "message": "Hello!"},
                                    follow_redirects=True)
        send.assert_called_once_with("Ana", "ana@ex.com", "Surprise Me", "Hello!")
        self.assertIn("get back to you soon", resp.get_data(as_text=True))  # apostrophe is HTML-escaped

    @patch("blueprints.public.routes.send_contact_email")
    def test_honeypot_never_sends(self, send):
        with patch("blueprints.public.routes.query", return_value=[]):
            self.client.post("/contact", data={"company": "bot", "name": "x", "email": "x@x.co", "subject": "Surprise Me", "message": "spam"})
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()

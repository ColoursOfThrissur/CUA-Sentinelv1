import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class EmailEngine:
    """
    Gmail & SMTP Email Integration Engine.
    Handles IMAP email reading for morning digests and SMTP email dispatching.
    """

    def __init__(self, imap_server="imap.gmail.com", smtp_server="smtp.gmail.com", smtp_port=587):
        self.imap_server = imap_server
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

    def fetch_recent_emails(self, email_user: str, app_password: str, max_emails: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches unread/recent emails from Gmail INBOX using IMAP SSL.
        """
        results = []
        if not email_user or not app_password:
            return results

        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(email_user, app_password)
            mail.select("inbox")

            status, messages = mail.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                status, messages = mail.search(None, "ALL")

            mail_ids = messages[0].split()
            recent_ids = mail_ids[-max_emails:] if mail_ids else []

            for m_id in reversed(recent_ids):
                res, msg_data = mail.fetch(m_id, "(RFC822)")
                if res != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8", errors="ignore")

                        sender = msg.get("From", "Unknown")
                        date = msg.get("Date", "")
                        body = ""

                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                if content_type == "text/plain" and "attachment" not in content_disposition:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body = payload.decode(errors="ignore")
                                        break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body = payload.decode(errors="ignore")

                        results.append({
                            "subject": subject or "No Subject",
                            "sender": sender,
                            "date": date,
                            "snippet": body[:300].strip() if body else "No text body content"
                        })

            mail.logout()
            logger.info(f"Fetched {len(results)} recent emails from Gmail via IMAP.")
        except Exception as e:
            logger.error(f"Error fetching Gmail messages via IMAP: {e}")
            raise e

        return results

    def search_emails(self, email_user: str, app_password: str, query: str = "", max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Searches Gmail inbox via IMAP for specific keyword/query matching subject or body.
        """
        results = []
        if not email_user or not app_password:
            return results

        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(email_user, app_password)
            mail.select("inbox")

            import re
            stop_words = {"can", "you", "get", "find", "search", "my", "gmail", "email", "inbox", "the", "for", "from", "with", "a", "an", "is", "of", "to"}
            words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', query.lower()) if w not in stop_words]
            
            search_criterion = "ALL"
            if words:
                # Use the top key terms for IMAP TEXT search
                search_term = " ".join(words[:4])
                search_criterion = f'TEXT "{search_term}"'

            status, messages = mail.search(None, search_criterion)
            if (status != "OK" or not messages[0]) and words:
                # Fallback to single primary keyword search
                status, messages = mail.search(None, f'TEXT "{words[0]}"')
            if status != "OK" or not messages[0]:
                status, messages = mail.search(None, "ALL")

            mail_ids = messages[0].split()
            recent_ids = mail_ids[-max_results:] if mail_ids else []

            for m_id in reversed(recent_ids):
                res, msg_data = mail.fetch(m_id, "(RFC822)")
                if res != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8", errors="ignore")

                        sender = msg.get("From", "Unknown")
                        date = msg.get("Date", "")
                        body = ""

                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                if content_type == "text/plain" and "attachment" not in content_disposition:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body = payload.decode(errors="ignore")
                                        break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body = payload.decode(errors="ignore")

                        results.append({
                            "subject": subject or "No Subject",
                            "sender": sender,
                            "date": date,
                            "snippet": body[:1200].strip() if body else "No text body content"
                        })

            mail.logout()
            logger.info(f"Searched Gmail via IMAP for words={words}, found {len(results)} matches.")
        except Exception as e:
            logger.error(f"Error searching Gmail via IMAP: {e}")

        return results

    def send_email(
        self,
        email_user: str,
        app_password: str,
        recipient_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None
    ) -> bool:
        """
        Dispatches email notification/digest via SMTP TLS.
        """
        if not email_user or not app_password or not recipient_email:
            logger.warning("Email credentials or recipient missing.")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = email_user
            msg["To"] = recipient_email

            part1 = MIMEText(body_text, "plain")
            msg.attach(part1)

            if body_html:
                part2 = MIMEText(body_html, "html")
                msg.attach(part2)

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(email_user, app_password)
            server.sendmail(email_user, recipient_email, msg.as_string())
            server.quit()

            logger.info(f"Email successfully sent to {recipient_email} via SMTP.")
            return True
        except Exception as e:
            logger.error(f"SMTP email dispatch failed: {e}")
            raise e

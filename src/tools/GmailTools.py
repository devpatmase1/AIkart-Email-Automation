import os
import socket
import re
import uuid
import base64
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


import imaplib
import smtplib
import email
from email.header import decode_header

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

class GmailToolsClass:
    def __init__(self):
        self.service = self._get_gmail_service()
        
    def fetch_unanswered_emails(self, max_results=50):
        """
        Fetches all emails included in unanswered threads (via Gmail API or IMAP/SMTP).
        """
        # Try direct IMAP first if credentials are in .env
        imap_emails = self._fetch_via_imap()
        if imap_emails is not None:
            if imap_emails:
                print(f"[IMAP] Found {len(imap_emails)} unread emails in inbox!")
                return imap_emails
            else:
                print("[IMAP] No unread emails found in inbox.")
                return []

        if not self.service:
            print("Notice: Using simulated customer email. Set MY_EMAIL and EMAIL_PASSWORD in .env for direct live email automation!")
            return [
                {
                    "id": "sim_msg_101",
                    "threadId": "sim_thread_101",
                    "messageId": "<sim_101@client.com>",
                    "references": "",
                    "sender": "client@example.com",
                    "subject": "Inquiry regarding service plans and pricing",
                    "body": "Hello, I would like to learn more about your agency service plans, pricing tiers, and what features are included. Thanks!"
                }
            ]
        try:
            # Get recent emails and organize them into threads
            recent_emails = self.fetch_recent_emails(max_results)
            if not recent_emails: return []
            
            # Get all draft replies
            drafts = self.fetch_draft_replies()

            # Create a set of thread IDs that have drafts
            threads_with_drafts = {draft['threadId'] for draft in drafts}

            # Process new emails
            seen_threads = set()
            unanswered_emails = []
            for email in recent_emails:
                thread_id = email['threadId']
                if thread_id not in seen_threads and thread_id not in threads_with_drafts:
                    seen_threads.add(thread_id)
                    email_info = self._get_email_info(email['id'])
                    if self._should_skip_email(email_info):
                        continue
                    unanswered_emails.append(email_info)
            return unanswered_emails

        except Exception as e:
            print(f"An error occurred: {e}")
            return []

    def fetch_recent_emails(self, max_results=50):
        if not self.service: return []
        try:
            # Set delay of 8 hours
            now = datetime.now()
            delay = now - timedelta(hours=8)

            # Format for Gmail query
            after_timestamp = int(delay.timestamp())
            before_timestamp = int(now.timestamp())

            # Query to get emails from the last 8 hours
            query = f"after:{after_timestamp} before:{before_timestamp}"
            results = self.service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            messages = results.get("messages", [])
            
            return messages
        
        except Exception as error:
            print(f"An error occurred while fetching emails: {error}")
            return []
        
    def fetch_draft_replies(self):
        if not self.service: return []
        """
        Fetches all draft email replies from Gmail.
        """
        try:
            drafts = self.service.users().drafts().list(userId="me").execute()
            draft_list = drafts.get("drafts", [])
            return [
                {
                    "draft_id": draft["id"],
                    "threadId": draft["message"]["threadId"],
                    "id": draft["message"]["id"],
                }
                for draft in draft_list
            ]

        except Exception as error:
            print(f"An error occurred while fetching drafts: {error}")
            return []

    def create_draft_reply(self, initial_email, reply_text):
        if not self.service:
            print(f"\n[SIMULATED GMAIL DRAFT CREATED]\nTo: {initial_email.sender}\nSubject: Re: {initial_email.subject}\n\nBody:\n{reply_text}\n")
            return {"id": "sim_draft_id"}
        try:
            # Create the reply message
            message = self._create_reply_message(initial_email, reply_text)

            # Create draft with thread information
            draft = self.service.users().drafts().create(
                userId="me", body={"message": message}
            ).execute()

            return draft
        except Exception as error:
            print(f"An error occurred while creating draft: {error}")
            return None

    def send_reply(self, initial_email, reply_text):
        if self._send_via_smtp(initial_email.sender, initial_email.subject, reply_text):
            return {"id": "smtp_sent_id"}

        if not self.service:
            print(f"\n[SIMULATED GMAIL EMAIL SENT]\nTo: {initial_email.sender}\nSubject: Re: {initial_email.subject}\n\nBody:\n{reply_text}\n")
            return {"id": "sim_sent_id"}
        try:
            # Create the reply message
            message = self._create_reply_message(initial_email, reply_text, send=True)

            # Send the message with thread ID
            sent_message = self.service.users().messages().send(
                userId="me", body=message
            ).execute()
            
            return sent_message

        except Exception as error:
            print(f"An error occurred while sending reply: {error}")
            return None
        
    def _create_reply_message(self, email, reply_text, send=False):
        # Create message with proper headers
        message = self._create_html_email_message(
            recipient=email.sender,
            subject=email.subject,
            reply_text=reply_text
        )

        # Set threading headers
        if email.messageId:
            message["In-Reply-To"] = email.messageId
            # Combine existing references with the original message ID
            message["References"] = f"{email.references} {email.messageId}".strip()
            
            if send:
                # Generate a new Message-ID for this reply
                message["Message-ID"] = f"<{uuid.uuid4()}@gmail.com>"
                
        # Construct email body
        body = {
            "raw": base64.urlsafe_b64encode(message.as_bytes()).decode(),
            "threadId": email.threadId
        }

        return body

        
    def _get_gmail_service(self):
        try:
            creds = None
            if os.path.exists('token.json'):
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                elif os.path.exists('credentials.json'):
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                else:
                    return None
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
            
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            print(f"Gmail credentials not loaded: {e}")
            return None
    
    def _should_skip_email(self, email_info):
        return os.environ['MY_EMAIL'] in email_info['sender']

    def _get_email_info(self, msg_id):
        message = self.service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        payload = message.get('payload', {})
        headers = {header["name"].lower(): header["value"] for header in payload.get("headers", [])}

        return {
            "id": msg_id,
            "threadId": message.get("threadId"),
            "messageId": headers.get("message-id"),
            "references": headers.get("references", ""),
            "sender": headers.get("from", "Unknown"),
            "subject": headers.get("subject", "No Subject"),
            "body": self._get_email_body(payload),
        }
    
    def _get_email_body(self, payload):
        """
        Extract the email body, prioritizing text/plain over text/html.
        Handles multipart messages, avoids duplicating content, and strips HTML if necessary.
        """
        def decode_data(data):
            """Decode base64-encoded data."""
            return base64.urlsafe_b64decode(data).decode('utf-8').strip() if data else ""

        def extract_body(parts):
            """Recursively extract text content from parts."""
            for part in parts:
                mime_type = part.get('mimeType', '')
                data = part['body'].get('data', '')
                if mime_type == 'text/plain':
                    return decode_data(data)
                if mime_type == 'text/html':
                    html_content = decode_data(data)
                    return self._extract_main_content_from_html(html_content)
                if 'parts' in part:
                    result = extract_body(part['parts'])
                    if result:
                        return result
            return ""

        # Process single or multipart payload
        if 'parts' in payload:
            body = extract_body(payload['parts'])
        else:
            data = payload['body'].get('data', '')
            body = decode_data(data)
            if payload.get('mimeType') == 'text/html':
                body = self._extract_main_content_from_html(body)

        return self._clean_body_text(body)

    def _extract_main_content_from_html(self, html_content):
        """
        Extract main visible content from HTML.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        for tag in soup(['script', 'style', 'head', 'meta', 'title']):
            tag.decompose()
        return soup.get_text(separator='\n', strip=True)

    def _clean_body_text(self, text):
        """
        Clean up the email body text by removing extra spaces and newlines.
        """
        return re.sub(r'\s+', ' ', text.replace('\r', '').replace('\n', '')).strip()
    
    def _create_html_email_message(self, recipient, subject, reply_text):
        """
        Creates a simple HTML email message with proper formatting and plaintext fallback.
        """
        message = MIMEMultipart("alternative")
        message["to"] = recipient
        message["subject"] = f"Re: {subject}" if not subject.startswith("Re: ") else subject

        # Simplified HTML Template
        html_text = reply_text.replace("\n", "<br>").replace("\\n", "<br>")
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body>{html_text}</body>
        </html>
        """

        html_part = MIMEText(html_content, "html")

        # message.attach(text_part)
        message.attach(html_part)

        return message

    def _fetch_via_imap(self):
        email_user = os.getenv("MY_EMAIL", "")
        email_pass = os.getenv("EMAIL_PASSWORD", "") or os.getenv("SMTP_PASSWORD", "")
        if not email_user or not email_pass or email_pass == "your_app_password_here":
            return None
        
        try:
            imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
            mail = imaplib.IMAP4_SSL(imap_server, 993)
            mail.login(email_user, email_pass)
            mail.select("inbox")
            
            status, messages = mail.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                mail.logout()
                return []
                
            email_list = []
            for num in messages[0].split()[:10]:
                _, data = mail.fetch(num, "(RFC822)")
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                subject, encoding = decode_header(msg.get("Subject", "No Subject"))[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding or "utf-8", errors="ignore")
                    
                sender = msg.get("From", "Unknown")
                
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                    
                email_list.append({
                    "id": str(num),
                    "threadId": str(num),
                    "messageId": msg.get("Message-ID", ""),
                    "references": msg.get("References", ""),
                    "sender": sender,
                    "subject": subject,
                    "body": body.strip()
                })
            mail.logout()
            return email_list
        except Exception as e:
            print(f"IMAP fetch info: {e}")
            return None

    def _send_via_smtp(self, recipient, subject, reply_text):
        email_user = os.getenv("MY_EMAIL", "")
        email_pass = os.getenv("EMAIL_PASSWORD", "") or os.getenv("SMTP_PASSWORD", "")
        if not email_user or not email_pass or email_pass == "your_app_password_here":
            return False
            
        try:
            smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            
            msg = MIMEMultipart()
            msg["From"] = email_user
            msg["To"] = recipient
            msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re: ") else subject
            msg.attach(MIMEText(reply_text, "plain"))
            
            try:
                addrs = [res[4][0] for res in socket.getaddrinfo(smtp_server, smtp_port, socket.AF_INET, socket.SOCK_STREAM)]
                target_smtp = addrs[0] if addrs else smtp_server
            except Exception:
                target_smtp = smtp_server

            if smtp_port == 465:
                server = smtplib.SMTP_SSL(target_smtp, smtp_port, timeout=15)
                server.server_hostname = smtp_server
            else:
                server = smtplib.SMTP(target_smtp, smtp_port, timeout=15)
                server.starttls()

            server.login(email_user, email_pass)
            server.send_message(msg)
            server.quit()
            print(f"\n[REAL EMAIL SENT VIA SMTP]\nTo: {recipient}\nSubject: {msg['Subject']}\n")
            return True
        except Exception as e:
            print(f"SMTP send info: {e}")
            return False
import smtplib
import os
from email.message import EmailMessage

def send_email(subject, body, recipient_email, attachment_path=None):
    EMAIL_ADDRESS = os.environ['EMAIL_ADDRESS']
    EMAIL_PASSWORD = os.environ['EMAIL_PASSWORD']

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = recipient_email
    msg.set_content(body)

    if attachment_path:
        with open(attachment_path, 'rb') as f:
            msg.add_attachment(
                f.read(), maintype='application', subtype='octet-stream',
                filename=attachment_path
            )

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

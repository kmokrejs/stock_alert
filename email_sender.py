from email.message import EmailMessage
import os
import smtplib

def send_email(subject, body, recipient_email, attachment_path=None, is_html=False):
    EMAIL_ADDRESS = os.environ['EMAIL_ADDRESS']
    EMAIL_PASSWORD = os.environ['EMAIL_PASSWORD']

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = recipient_email

    if is_html:
        msg.add_alternative(body, subtype='html')
    else:
        msg.set_content(body)

    if attachment_path:
        with open(attachment_path, 'rb') as f:
            msg.add_attachment(
                f.read(), maintype='application', subtype='octet-stream',
                filename=os.path.basename(attachment_path)
            )

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

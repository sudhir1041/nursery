from django.core.mail import EmailMessage
from settings_app.utils import get_email_connection, get_setting


def send_invoice_email(order):
    connection = get_email_connection()
    recipient = order.customer_email
    if not connection or not recipient:
        return
    from_email = get_setting('EMAIL_FROM') or get_setting('EMAIL_HOST_USER')
    subject = f"Invoice for Order {order.invoice_id}"
    body = (
        f"Dear {order.customer_name},\n\n"
        f"Thank you for your order {order.invoice_id}.\n"
        f"Total amount: {order.order_total}\n"
    )
    EmailMessage(subject, body, from_email, [recipient], connection=connection).send()

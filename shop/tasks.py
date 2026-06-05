import json
import time
from io import BytesIO

import qrcode
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from qrcode.image.svg import SvgPathImage

from .models import Order


def build_qr_svg(order):
    payload = {
        "type": "eshop_pickup",
        "order": order.order_number,
        "pickup_code": order.pickup_code,
        "total": str(order.total),
        "customer": order.customer_name,
    }
    image = qrcode.make(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        image_factory=SvgPathImage,
        box_size=8,
        border=2,
    )
    stream = BytesIO()
    image.save(stream)
    svg = stream.getvalue().decode("utf-8").strip()
    if svg.startswith("<?xml"):
        svg = svg.split("?>", 1)[1].strip()
    return svg


def complete_demo_payment(order_id):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id)
        if order.payment_status == Order.PaymentStatus.PAID and order.qr_svg:
            return order.id
        now = timezone.now()
        order.payment_status = Order.PaymentStatus.PAID
        order.status = Order.Status.READY
        order.paid_at = now
        order.ready_at = now
        order.qr_svg = build_qr_svg(order)
        order.save(update_fields=["payment_status", "status", "paid_at", "ready_at", "qr_svg"])
        return order.id


@shared_task
def process_order_payment(order_id):
    time.sleep(3)
    return complete_demo_payment(order_id)

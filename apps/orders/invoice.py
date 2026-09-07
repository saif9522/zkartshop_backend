"""
Order invoice / bill generation.

Produces a downloadable PDF bill for a single Order using reportlab (a pure
Python dependency, no system libraries needed). Called by the `invoice`
action on the customer and vendor order viewsets.
"""
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

GST_RATE_PERCENT = Decimal("5")  # keep in step with reports.services.GST_RATE_PERCENT

# Platform brand shown at the top of every bill. Change this one line to rebrand.
BRAND_NAME = "WWW.ZKART.SHOP"

# Brand colours (fall back gracefully if you rebrand later).
_INK = colors.HexColor("#1f2933")
_MUTED = colors.HexColor("#7b8794")
_LINE = colors.HexColor("#e4e7eb")
_ACCENT = colors.HexColor("#2f855a")


def _rupees(amount) -> str:
    value = Decimal(str(amount or 0))
    return f"Rs. {value:,.2f}"


def build_invoice_pdf_bytes(order) -> bytes:
    """Render `order` to PDF bytes. Assumes items/vendor/customer are loaded."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {order.order_number}",
    )

    styles = getSampleStyleSheet()
    h_shop = ParagraphStyle("shop", parent=styles["Title"], fontSize=18, textColor=_INK, spaceAfter=2)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, textColor=_MUTED, leading=12)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=8, textColor=_MUTED, leading=11)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, textColor=_INK, leading=13)
    right = ParagraphStyle("right", parent=body, alignment=2)
    right_small = ParagraphStyle("right_small", parent=small, alignment=2)

    vendor = order.vendor
    customer = order.customer
    addr = order.delivery_address

    elements = []

    # --- Header: brand + seller details (left) + invoice meta (right) ---
    seller = ParagraphStyle("seller", parent=styles["Normal"], fontSize=9.5, textColor=_INK, leading=13, spaceBefore=2)
    shop_lines = [Paragraph(BRAND_NAME, h_shop)]
    shop_lines.append(Paragraph(f"Sold by: <b>{vendor.shop_name}</b>", seller))
    shop_addr = ", ".join(x for x in [vendor.address_line, vendor.city, vendor.state, vendor.pincode] if x)
    if shop_addr:
        shop_lines.append(Paragraph(shop_addr, small))
    if vendor.gst_number:
        shop_lines.append(Paragraph(f"GSTIN: {vendor.gst_number}", small))
    if getattr(vendor, "whatsapp_number", ""):
        shop_lines.append(Paragraph(f"Contact: {vendor.whatsapp_number}", small))

    meta_lines = [
        Paragraph("TAX INVOICE", ParagraphStyle("inv", parent=right, fontSize=13, textColor=_ACCENT, spaceAfter=4)),
        Paragraph(f"Invoice No: <b>{order.order_number}</b>", right_small),
        Paragraph(f"Date: {order.placed_at.strftime('%d %b %Y, %I:%M %p')}", right_small),
        Paragraph(f"Payment: {order.get_payment_method_display()} ({order.get_payment_status_display()})", right_small),
        Paragraph(f"Status: {order.get_status_display()}", right_small),
    ]

    header = Table([[shop_lines, meta_lines]], colWidths=[95 * mm, 79 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 8))
    elements.append(_hr())
    elements.append(Spacer(1, 8))

    # --- Bill to ---
    bill_to = [Paragraph("BILL TO", label)]
    bill_to.append(Paragraph(customer.full_name or str(customer.phone or "Customer"), body))
    if customer.phone:
        bill_to.append(Paragraph(str(customer.phone), small))
    if addr:
        cust_addr = ", ".join(
            x for x in [addr.address_line, addr.landmark, addr.city, addr.state, addr.pincode] if x
        )
        bill_to.append(Paragraph(cust_addr, small))
    elements.append(Table([[bill_to]], colWidths=[174 * mm], style=TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ])))
    elements.append(Spacer(1, 10))

    # --- Items table ---
    data = [["#", "Item", "Unit", "Qty", "Price", "Amount"]]
    for i, item in enumerate(order.items.all(), start=1):
        data.append([
            str(i),
            Paragraph(item.product_name, body),
            item.unit or "-",
            str(item.quantity),
            _rupees(item.price),
            _rupees(item.subtotal),
        ])

    items_table = Table(data, colWidths=[8 * mm, 82 * mm, 22 * mm, 14 * mm, 24 * mm, 24 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (3, 0), (5, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, _LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 10))

    # --- Totals ---
    subtotal = Decimal(str(order.subtotal or 0))
    taxable = (subtotal / (1 + GST_RATE_PERCENT / 100)).quantize(Decimal("0.01"))
    gst_amount = (subtotal - taxable).quantize(Decimal("0.01"))

    totals_rows = [
        ["Items subtotal", _rupees(order.subtotal)],
    ]
    if order.discount_amount and Decimal(str(order.discount_amount)) > 0:
        code = f" ({order.coupon_code})" if order.coupon_code else ""
        totals_rows.append([f"Discount{code}", f"- {_rupees(order.discount_amount)}"])
    totals_rows.append(["Delivery charge", _rupees(order.delivery_charge)])
    for entry in (order.extra_charges_breakdown or []):
        try:
            label = entry.get("label", "Extra charge")
            amount = entry.get("amount", 0)
        except AttributeError:
            continue
        totals_rows.append([label, _rupees(amount)])
    totals_rows.append([f"Incl. GST @ {GST_RATE_PERCENT:g}% (est.)", _rupees(gst_amount)])
    totals_rows.append(["GRAND TOTAL", _rupees(order.grand_total)])

    totals = Table(totals_rows, colWidths=[130 * mm, 44 * mm])
    style = [
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), _INK),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, _INK),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("TEXTCOLOR", (0, -1), (-1, -1), _ACCENT),
        ("TOPPADDING", (0, -1), (-1, -1), 7),
    ]
    totals.setStyle(TableStyle(style))
    elements.append(totals)
    elements.append(Spacer(1, 16))

    # --- Footer ---
    elements.append(_hr())
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        "This is a computer-generated invoice and does not require a signature. "
        "GST shown is an estimate; refer to the shop's filed returns for exact tax details.",
        small,
    ))
    elements.append(Paragraph("Thank you for shopping with us.", ParagraphStyle(
        "thanks", parent=small, textColor=_ACCENT, spaceBefore=2,
    )))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def _hr():
    line = Table([[""]], colWidths=[174 * mm], rowHeights=[0.1])
    line.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.6, _LINE)]))
    return line


def invoice_pdf_response(order) -> HttpResponse:
    pdf = build_invoice_pdf_bytes(order)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice_{order.order_number}.pdf"'
    return response

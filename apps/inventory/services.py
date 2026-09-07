from apps.inventory.models import StockMovement


def record_stock_movement(product, movement_type, delta, reference="", notes="", actor=None):
    """
    Log one stock change. Call this right after product.stock_quantity has
    already been updated, so resulting_stock reflects the true post-change
    value.
    """
    StockMovement.objects.create(
        product=product,
        movement_type=movement_type,
        quantity_delta=delta,
        resulting_stock=product.stock_quantity,
        reference=reference,
        notes=notes,
        created_by=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
    )

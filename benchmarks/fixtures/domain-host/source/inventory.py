def reserve(available, quantity):
    if quantity > available:
        raise ValueError("insufficient stock")
    return available - quantity

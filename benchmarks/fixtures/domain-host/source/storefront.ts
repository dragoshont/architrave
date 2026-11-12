export function reserve(available: number, quantity: number): number {
  if (!Number.isInteger(available) || available < 0 ||
      !Number.isInteger(quantity) || quantity <= 0 || quantity > available) {
    throw new RangeError("invalid reservation");
  }
  return available - quantity;
}

export function reserveCart(stock: Record<string, number>, cart: Record<string, number>) {
  const next = { ...stock };
  for (const [sku, quantity] of Object.entries(cart)) {
    if (!(sku in stock)) throw new RangeError("unknown SKU");
    next[sku] = reserve(stock[sku], quantity);
  }
  return next;
}

// A collection entry as the forms hold it, and how /add-to-collection wants it.
export const EMPTY_ENTRY = { condition: 'NEAR_MINT', quantity: '1', price_paid: '' }

// What /add-to-collection expects. A blank price paid is "unknown" (null), not $0.
export function entryBody(entry, extra = {}) {
  return JSON.stringify({
    condition: entry.condition,
    quantity: parseInt(entry.quantity, 10) || 1,
    price_paid: entry.price_paid.trim() === '' ? null : entry.price_paid,
    ...extra,
  })
}

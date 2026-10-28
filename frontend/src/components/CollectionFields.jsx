import { useId } from 'react'
import { CONDITIONS, field, label } from './ui'

// Condition, quantity and price paid: the three things you say about a card you own.
// Used by "Add cards" on Collection and "Move to collection" on Watchlist.
export default function CollectionFields({ entry, setEntry, firstFieldRef }) {
  const id = useId()
  const set = key => e => setEntry({ ...entry, [key]: e.target.value })
  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="col-span-2">
        <label htmlFor={`${id}-cond`} className={label}>Condition</label>
        <select id={`${id}-cond`} ref={firstFieldRef} value={entry.condition} onChange={set('condition')} className={field}>
          {CONDITIONS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </div>
      <div>
        <label htmlFor={`${id}-qty`} className={label}>Quantity</label>
        <input id={`${id}-qty`} type="number" inputMode="numeric" min="1" max="999" step="1"
          value={entry.quantity} onChange={set('quantity')} className={field} />
      </div>
      <div>
        <label htmlFor={`${id}-paid`} className={label}>Price paid (each)</label>
        <input id={`${id}-paid`} type="number" inputMode="decimal" min="0" step="0.01" placeholder="Optional"
          value={entry.price_paid} onChange={set('price_paid')} className={field} />
      </div>
    </div>
  )
}

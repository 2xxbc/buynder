import { useState, useEffect } from 'react'
import { apiFetch } from '../config'
import ShareManager from '../components/ShareManager'
import QuickAdd from '../components/QuickAdd'
import CardImage from '../components/CardImage'
import Modal from '../components/Modal'
import Stat from '../components/Stat'
import { btn, field, label, money, signedMoney, upDown, conditionLabel } from '../components/ui'

function Collection() {
  const [items, setItems] = useState([])
  const [stats, setStats] = useState({ total_paid: 0, total_value: 0, unrealized_pnl: 0 })
  const [loading, setLoading] = useState(true)
  const [sellingItem, setSellingItem] = useState(null)
  const [sellForm, setSellForm] = useState({ sale_price: '', platform: '', notes: '' })
  const [pricingItem, setPricingItem] = useState(null) // the item whose "price paid" is being edited
  const [paidInput, setPaidInput] = useState('')
  const [paidError, setPaidError] = useState('')
  const [savingPaid, setSavingPaid] = useState(false)
  const [onlyUnpriced, setOnlyUnpriced] = useState(false)
  const [quickAdd, setQuickAdd] = useState(false)

  function loadCollection() {
    apiFetch('/collection')
      .then(res => res.json())
      .then(data => {
        setItems(data.items || [])
        setStats(data.stats || {})
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }

  useEffect(() => {
    loadCollection()
  }, [])

  function removeItem(collectionId) {
    if (!confirm('Remove this from your collection?')) return
    apiFetch(`/remove-from-collection/${collectionId}`, { method: 'DELETE' })
      .then(() => loadCollection())
  }

  function markSold() {
    if (!sellingItem) return

    apiFetch(`/mark-sold/${sellingItem.collection_id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sale_price: parseFloat(sellForm.sale_price) || 0,
        platform: sellForm.platform,
        notes: sellForm.notes
      })
    })
      .then(() => {
        setSellingItem(null)
        setSellForm({ sale_price: '', platform: '', notes: '' })
        loadCollection()
      })
  }

  function openPricing(item) {
    setPricingItem(item)
    setPaidInput(item.price_paid == null ? '' : String(item.price_paid))
    setPaidError('')
  }

  async function savePricePaid(e) {
    e.preventDefault()
    const raw = paidInput.trim()
    setSavingPaid(true)
    setPaidError('')
    try {
      const res = await apiFetch(`/update-price-paid/${pricingItem.collection_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ price_paid: raw === '' ? null : raw }),
      })
      const data = await res.json()
      if (!data.success) throw new Error(data.error || 'Could not save the price.')
      setPricingItem(null)
      loadCollection()
    } catch (err) {
      setPaidError(err.message || 'Could not save the price.')
    } finally {
      setSavingPaid(false)
    }
  }

  // "Paid" for one item: the amount (tap to edit) or a dash with an "Add price" link
  const paidCell = item => item.price_paid == null ? (
    <span className="inline-flex flex-wrap items-baseline gap-x-2">
      <span aria-hidden="true">—</span>
      <button type="button" onClick={() => openPricing(item)}
        className="text-sm font-semibold underline underline-offset-2 decoration-chalk/30 hover:decoration-chalk"
        aria-label={`Add the price you paid for ${item.name}`}>
        Add price
      </button>
    </span>
  ) : (
    <button type="button" onClick={() => openPricing(item)} title="Edit price paid"
      className="tabular-nums underline-offset-2 decoration-chalk/30 hover:underline"
      aria-label={`${money(item.price_paid)} paid for ${item.name}. Edit`}>
      {money(item.price_paid)}
    </button>
  )
  const pnl = item => item.profit_loss == null
    ? <span className="text-chalk-soft" aria-label="Unknown">—</span>
    : <span className={upDown(item.profit_loss)}>{signedMoney(item.profit_loss)}</span>

  const unpriced = stats.unpriced_count || 0
  // Once the last missing price is added the filter has nothing to show, so fall back to everything
  const shown = onlyUnpriced && unpriced > 0 ? items.filter(i => i.price_paid == null) : items

  const actions = item => (
    <div className="flex items-center gap-3">
      <button type="button" onClick={() => setSellingItem(item)}
        className="rounded-full bg-chalk text-stage text-sm font-semibold px-4 py-1.5 hover:bg-chalk/85 transition-colors">
        Sell
      </button>
      <button type="button" onClick={() => removeItem(item.collection_id)} className={btn.danger}
        aria-label={`Remove ${item.name} from collection`}>
        Remove
      </button>
    </div>
  )

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight">Collection</h1>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setQuickAdd(true)} className={btn.primary}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="w-4 h-4" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            Add cards
          </button>
          <ShareManager />
        </div>
      </div>

      <div className="mb-5 sm:mb-8">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4">
          <Stat label="Value" value={money(stats.total_value)} />
          <Stat label="Paid" value={money(stats.total_paid)} />
          <Stat label="Unrealized P&L" value={signedMoney(stats.unrealized_pnl)} valueClass={upDown(stats.unrealized_pnl)}
            className="col-span-2 sm:col-span-1"
            note={unpriced > 0 ? 'Only cards with a price paid' : undefined} />
        </div>

        {unpriced > 0 && (
          <p className="mt-3 text-sm text-chalk-soft">
            {unpriced === 1 ? '1 card has' : `${unpriced} cards have`} no price paid, so {unpriced === 1 ? "it's" : "they're"} left out of Paid and P&L.{' '}
            <button type="button" onClick={() => setOnlyUnpriced(v => !v)} aria-pressed={onlyUnpriced}
              className="font-semibold text-chalk underline underline-offset-2">
              {onlyUnpriced ? 'Show all cards' : unpriced === 1 ? 'Add its price' : 'Add their prices'}
            </button>
          </p>
        )}
      </div>

      {loading ? (
        <div className="h-64 rounded-panel shimmer" aria-hidden="true" />
      ) : items.length === 0 ? (
        <div className="glass rounded-panel text-center py-16 px-6">
          <p className="font-semibold">No cards in your collection yet.</p>
          <p className="text-sm text-chalk-soft mt-1">Search for your cards and add them, a few at a time or a whole binder page.</p>
          <button type="button" onClick={() => setQuickAdd(true)} className={`${btn.primary} mt-4`}>Add cards</button>
        </div>
      ) : (
        <div className="glass rounded-panel overflow-hidden">
          {/* Phones and tablets: stacked rows (the 8-column table needs a laptop-wide screen) */}
          <ul className="lg:hidden divide-y divide-chalk/10">
            {shown.map((item, i) => (
              <li key={item.collection_id ?? i} className="p-4 flex gap-3">
                <CardImage src={item.image_url} alt={item.name} className="w-14" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{item.name}</p>
                  <p className="text-sm text-chalk-soft truncate">{item.set_name}</p>
                  <p className="text-xs text-chalk-soft mt-1">
                    {conditionLabel(item.card_condition || 'NEAR_MINT')}, qty {item.quantity}
                    {item.priority === 'high' && ', high priority'}
                  </p>
                  <dl className="grid grid-cols-3 gap-2 mt-2 text-sm tabular-nums">
                    <div><dt className="text-xs text-chalk-soft">Paid</dt><dd>{paidCell(item)}</dd></div>
                    <div><dt className="text-xs text-chalk-soft">Now</dt><dd>{money(item.current_price || 0)}</dd></div>
                    <div><dt className="text-xs text-chalk-soft">P&L</dt><dd className="font-bold whitespace-nowrap">{pnl(item)}</dd></div>
                  </dl>
                  <div className="mt-3">{actions(item)}</div>
                </div>
              </li>
            ))}
          </ul>

          {/* Laptop + desktop: table */}
          <div className="hidden lg:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-chalk-soft">
                  <th scope="col" className="font-semibold px-5 py-3">Card</th>
                  <th scope="col" className="font-semibold px-3 py-3">Qty</th>
                  <th scope="col" className="font-semibold px-3 py-3 text-right">Paid</th>
                  <th scope="col" className="font-semibold px-3 py-3 text-right">Current</th>
                  <th scope="col" className="font-semibold px-3 py-3">Condition</th>
                  <th scope="col" className="font-semibold px-3 py-3 text-right">P&L</th>
                  <th scope="col" className="font-semibold px-3 py-3">Priority</th>
                  <th scope="col" className="px-5 py-3"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {shown.map((item, i) => (
                  <tr key={item.collection_id ?? i} className="border-t border-chalk/10">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <CardImage src={item.image_url} alt={item.name} className="w-11" />
                        <div className="min-w-0">
                          <p className="font-semibold">{item.name}</p>
                          <p className="text-chalk-soft">{item.set_name}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 tabular-nums">{item.quantity}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{paidCell(item)}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{money(item.current_price || 0)}</td>
                    <td className="px-3 py-3">
                      <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-chalk/[0.07] whitespace-nowrap">
                        {conditionLabel(item.card_condition || 'NEAR_MINT')}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right font-bold tabular-nums">{pnl(item)}</td>
                    <td className="px-3 py-3 capitalize">{item.priority}</td>
                    <td className="px-5 py-3">{actions(item)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {quickAdd && <QuickAdd onClose={() => setQuickAdd(false)} onAdded={loadCollection} />}

      {pricingItem && (
        <Modal title="Price paid" subtitle={`${pricingItem.name}, ${pricingItem.set_name}`} onClose={() => setPricingItem(null)}>
          <form onSubmit={savePricePaid} noValidate>
            <label htmlFor="paid-price" className={label}>What you paid for one card</label>
            <input id="paid-price" type="number" inputMode="decimal" step="0.01" min="0" placeholder="e.g. 12.50"
              value={paidInput} onChange={e => setPaidInput(e.target.value)} className={field}
              aria-describedby="paid-help" aria-invalid={paidError ? true : undefined} />
            <p id="paid-help" className="text-xs text-chalk-soft mt-2">
              {stats.zero_means_unknown
                ? "Leave it empty if you don't know. It stays out of P&L until you add it."
                : "Leave it empty if you don't know. Enter 0 if it was free (a gift or a pack pull)."}
            </p>
            {paidError && <p role="alert" className="text-sm text-down-bright font-semibold mt-2">{paidError}</p>}
            <div className="flex gap-3 mt-6">
              <button type="button" onClick={() => setPricingItem(null)} className={`${btn.secondary} flex-1`}>Cancel</button>
              <button type="submit" disabled={savingPaid} className={`${btn.primary} flex-1`}>{savingPaid ? 'Saving…' : 'Save'}</button>
            </div>
          </form>
        </Modal>
      )}

      {sellingItem && (
        <Modal title="Mark as sold" subtitle={`${sellingItem.name}, ${sellingItem.set_name}`} onClose={() => setSellingItem(null)}>
          <div className="space-y-4">
            <div>
              <label htmlFor="sell-price" className={label}>Sale price</label>
              <input id="sell-price" type="number" step="0.01" placeholder="0.00" value={sellForm.sale_price}
                onChange={e => setSellForm({ ...sellForm, sale_price: e.target.value })} className={field} />
            </div>
            <div>
              <label htmlFor="sell-platform" className={label}>Platform</label>
              <input id="sell-platform" type="text" placeholder="eBay, TCGPlayer, local…" value={sellForm.platform}
                onChange={e => setSellForm({ ...sellForm, platform: e.target.value })} className={field} />
            </div>
            <div>
              <label htmlFor="sell-notes" className={label}>Notes (optional)</label>
              <textarea id="sell-notes" rows="3" placeholder="Anything to remember about this sale" value={sellForm.notes}
                onChange={e => setSellForm({ ...sellForm, notes: e.target.value })} className={field} />
            </div>
          </div>
          <div className="flex gap-3 mt-6">
            <button type="button" onClick={() => setSellingItem(null)} className={`${btn.secondary} flex-1`}>Cancel</button>
            <button type="button" onClick={markSold} className={`${btn.primary} flex-1`}>Confirm sale</button>
          </div>
        </Modal>
      )}
    </>
  )
}

export default Collection

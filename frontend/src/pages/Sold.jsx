import { useState, useEffect } from 'react'
import { apiFetch } from '../config'
import CardImage from '../components/CardImage'
import Stat from '../components/Stat'
import { money } from '../components/ui'

function Sold() {
  const [items, setItems] = useState([])
  const [stats, setStats] = useState({ total_sold: 0, count: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/sold')
      .then(res => res.json())
      .then(data => {
        setItems(data.items || [])
        setStats(data.stats || {})
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  return (
    <>
      <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight mb-6">Sold</h1>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 mb-8">
        <Stat label="Total sales" value={money(stats.total_sold)} />
        <Stat label="Cards sold" value={stats.count ?? 0} />
      </div>

      {loading ? (
        <div className="h-64 rounded-panel shimmer" aria-hidden="true" />
      ) : items.length === 0 ? (
        <div className="glass rounded-panel text-center py-16 px-6">
          <p className="font-semibold">No sales yet.</p>
          <p className="text-sm text-chalk-soft mt-1">Mark a card as sold from your Collection.</p>
        </div>
      ) : (
        <div className="glass rounded-panel overflow-hidden">
          <ul className="md:hidden divide-y divide-chalk/10">
            {items.map(item => (
              <li key={item.sold_id} className="p-4 flex gap-3">
                <CardImage src={item.image_url} alt={item.name} className="w-12" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="font-semibold truncate">{item.name}</p>
                    <p className="font-bold tabular-nums shrink-0">{money(item.sale_price)}</p>
                  </div>
                  <p className="text-sm text-chalk-soft truncate">{item.set_name}</p>
                  <p className="text-xs text-chalk-soft mt-1">
                    {new Date(item.sold_at).toLocaleDateString()}{item.platform && `, ${item.platform}`}
                  </p>
                  {item.notes && <p className="text-sm text-chalk-soft mt-1 break-words">{item.notes}</p>}
                </div>
              </li>
            ))}
          </ul>

          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-chalk-soft">
                  <th scope="col" className="font-semibold px-5 py-3">Card</th>
                  <th scope="col" className="font-semibold px-3 py-3 text-right">Sold for</th>
                  <th scope="col" className="font-semibold px-3 py-3">Platform</th>
                  <th scope="col" className="font-semibold px-3 py-3">Date</th>
                  <th scope="col" className="font-semibold px-5 py-3">Notes</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.sold_id} className="border-t border-chalk/10">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <CardImage src={item.image_url} alt={item.name} className="w-11" />
                        <div className="min-w-0">
                          <p className="font-semibold">{item.name}</p>
                          <p className="text-chalk-soft">{item.set_name}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right font-bold tabular-nums">{money(item.sale_price)}</td>
                    <td className="px-3 py-3">{item.platform || '—'}</td>
                    <td className="px-3 py-3 text-chalk-soft whitespace-nowrap">{new Date(item.sold_at).toLocaleDateString()}</td>
                    <td className="px-5 py-3 text-chalk-soft max-w-xs break-words">{item.notes || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}

export default Sold

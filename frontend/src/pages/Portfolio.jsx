import { useState, useEffect } from 'react'
import { apiFetch } from '../config'
import CardImage from '../components/CardImage'
import Change from '../components/Change'
import Stat from '../components/Stat'
import { money, signedMoney, upDown } from '../components/ui'

function MoverPanel({ title, card }) {
  return (
    <section className="glass rounded-panel p-5 sm:p-6">
      <h2 className="font-semibold mb-4">{title}</h2>
      <div className="flex items-center gap-4">
        <CardImage src={card.image_url} alt={card.name} className="w-20 shadow-float" />
        <div className="min-w-0">
          <p className="font-display text-lg font-semibold leading-tight break-words">{card.name}</p>
          <p className="text-sm text-chalk-soft">{card.set_name}</p>
          <p className="mt-2 text-xl"><Change value={card.change_pct} /></p>
        </div>
      </div>
    </section>
  )
}

function Portfolio() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/portfolio')
      .then(res => res.json())
      .then(d => {
        setData(d)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4" aria-hidden="true">
        {[0, 1, 2, 3, 4, 5].map(i => <div key={i} className="h-24 rounded-panel shimmer" />)}
      </div>
    )
  }
  if (!data) return <p className="text-chalk-soft">No data.</p>

  return (
    <>
      <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight mb-6">Portfolio</h1>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4 mb-8">
        <Stat label="Binder worth" value={money(data.binder_worth)} />
        <Stat label="Total paid" value={money(data.total_paid)} />
        <Stat label="Unrealized P&L" value={signedMoney(data.unrealized_pnl)} valueClass={upDown(data.unrealized_pnl)}
          note={data.unpriced_count > 0 ? `Leaves out ${data.unpriced_count} ${data.unpriced_count === 1 ? 'card' : 'cards'} with no price paid` : undefined} />
        <Stat label="Total sold" value={money(data.total_sold)} />
        <Stat label="Realized P&L" value={signedMoney(data.realized_pnl)} valueClass={upDown(data.realized_pnl)} />
        <Stat label="Total P&L" value={signedMoney(data.total_pnl)} valueClass={upDown(data.total_pnl)} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {data.biggest_gainer && <MoverPanel title="Biggest gainer" card={data.biggest_gainer} />}
        {data.biggest_loser && <MoverPanel title="Biggest loser" card={data.biggest_loser} />}
      </div>
    </>
  )
}

export default Portfolio

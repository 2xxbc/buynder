// Shared class strings + helpers so buttons, fields and panels match on every page.
// Binder (light) side unless the name says otherwise.

export const btn = {
  // Light pill — the main action on a page
  primary: 'inline-flex items-center justify-center gap-2 rounded-full bg-chalk text-stage font-semibold px-5 py-3 hover:bg-chalk/85 disabled:opacity-50 disabled:cursor-not-allowed transition-colors',
  // Outline pill — everything else
  secondary: 'inline-flex items-center justify-center gap-2 rounded-full border border-chalk/15 text-chalk font-semibold px-5 py-3 hover:bg-chalk/5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors',
  // Small text button for destructive actions (remove, delete)
  danger: 'text-sm font-semibold text-down-bright hover:underline underline-offset-4',
  // Lime button — showroom (dark) side only
  volt: 'inline-flex items-center justify-center gap-2 rounded-[4px] bg-volt text-stage font-bold px-5 py-3 hover:bg-volt-deep disabled:opacity-50 transition-colors',
}

export const field = 'w-full bg-chalk/[0.06] border border-chalk/15 rounded-chip px-3.5 py-2.5 text-chalk placeholder:text-chalk-soft focus:border-chalk transition-colors'
export const label = 'block text-sm font-semibold text-chalk-soft mb-1.5'

// Small segmented chips (chart ranges, filters)
export const chip = active =>
  `px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${active ? 'bg-chalk text-stage' : 'text-chalk-soft hover:text-chalk hover:bg-chalk/5'}`

// $1,234.56 — or an em dash when there's no number
export const money = n => n == null || n === '' || Number.isNaN(Number(n))
  ? '—'
  : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

// +$12.00 / −$3.50 for profit & loss
export const signedMoney = n => n == null || Number.isNaN(Number(n))
  ? '—'
  : `${Number(n) >= 0 ? '+' : '−'}${money(Math.abs(Number(n)))}`
export const upDown = n => Number(n) >= 0 ? 'text-up-bright' : 'text-down-bright'

export const CONDITIONS = [
  { value: 'NEAR_MINT', label: 'Near mint' },
  { value: 'LIGHTLY_PLAYED', label: 'Lightly played' },
  { value: 'MODERATELY_PLAYED', label: 'Moderately played' },
  { value: 'HEAVILY_PLAYED', label: 'Heavily played' },
  { value: 'DAMAGED', label: 'Damaged' },
]
export const conditionLabel = value =>
  CONDITIONS.find(c => c.value === value)?.label
  ?? (value ? value.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()) : '')

// Read a design token (e.g. '--color-chalk') for places that can't use classes, like chart.js
export function token(name, alpha = 1) {
  const hex = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (alpha === 1 || !/^#[0-9a-f]{6}$/i.test(hex)) return hex
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16))
  return `rgb(${r} ${g} ${b} / ${alpha})`
}

// Where a card links to. Saved cards without a PokeTrace id use their watchlist id.
export const cardPath = card => card.poketrace_id ? `/card/${card.poketrace_id}` : `/card/saved/${card.id}`

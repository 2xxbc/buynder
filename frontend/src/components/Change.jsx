// "+12.4%" / "−3.1%" in the right up/down color for the background it sits on.
// tone: 'dark' (the site) or 'light' (the paper price ticket on the home page)
export default function Change({ value, tone = 'dark', className = '' }) {
  if (value == null || Number.isNaN(Number(value))) return null
  const n = Number(value)
  const up = n >= 0
  const color = tone === 'light' ? (up ? 'text-up' : 'text-down') : (up ? 'text-up-bright' : 'text-down-bright')
  return (
    <span className={`font-bold tabular-nums ${color} ${className}`}>
      {up ? '+' : '−'}{Math.abs(n).toFixed(1)}%
    </span>
  )
}

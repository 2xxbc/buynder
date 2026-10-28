// One number in a soft panel: small label on top, big tabular figure below,
// and an optional small note under it (e.g. what the number leaves out)
export default function Stat({ label, value, className = '', valueClass = '', note }) {
  return (
    <div className={`glass rounded-panel min-w-0 px-4 py-4 sm:px-6 sm:py-5 ${className}`}>
      <p className="text-sm text-chalk-soft">{label}</p>
      <p className={`mt-1 font-display text-lg sm:text-2xl lg:text-3xl font-semibold tabular-nums whitespace-nowrap overflow-hidden text-ellipsis ${valueClass}`}
        title={typeof value === 'string' ? value : undefined}>{value}</p>
      {note && <p className="mt-1 text-xs text-chalk-soft">{note}</p>}
    </div>
  )
}

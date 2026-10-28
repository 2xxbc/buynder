import { useEffect, useId, useRef } from 'react'

// Binder-style pop-up. Closes on Escape or a click outside, puts focus on the
// first field when it opens, and hands focus back to the button that opened it.
export default function Modal({ title, subtitle, onClose, children, wide = false }) {
  const titleId = useId()
  const panelRef = useRef(null)
  const closeRef = useRef(onClose)

  useEffect(() => { closeRef.current = onClose })

  useEffect(() => {
    const opener = document.activeElement
    panelRef.current?.querySelector('input, select, textarea, button')?.focus()
    const onKey = e => { if (e.key === 'Escape') closeRef.current() }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      opener?.focus?.()
    }
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-3 sm:p-4 bg-chalk/40 backdrop-blur-sm"
      onClick={onClose}>
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className={`relative w-full ${wide ? 'max-w-lg' : 'max-w-md'} max-h-[90vh] overflow-y-auto bg-stage-raised text-chalk rounded-panel p-6 shadow-float`}
        onClick={e => e.stopPropagation()}>
        <h2 id={titleId} className="font-display text-xl font-semibold pr-10">{title}</h2>
        {subtitle && <p className="text-sm text-chalk-soft mt-1">{subtitle}</p>}
        <div className="mt-5">{children}</div>
        {/* Last in the DOM so the first field gets focus, but shown top-right */}
        <button type="button" onClick={onClose} aria-label="Close"
          className="absolute top-5 right-5 w-9 h-9 rounded-full flex items-center justify-center text-chalk-soft hover:text-chalk hover:bg-chalk/5 transition-colors">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="w-4 h-4" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>
  )
}

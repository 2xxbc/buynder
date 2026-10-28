import { useEffect, useRef } from 'react'

// Closes a dropdown or panel when the user clicks/taps outside it or presses Escape.
//   const ref = useDismiss(open, () => setOpen(false))
//   <div ref={ref}> ...the thing that opens... </div>
export default function useDismiss(open, onDismiss) {
  const ref = useRef(null)
  const dismissRef = useRef(onDismiss)

  useEffect(() => { dismissRef.current = onDismiss })

  useEffect(() => {
    if (!open) return
    // pointerdown (not click) so a tap that starts outside closes it even if the finger drags
    const onPointer = e => { if (ref.current && !ref.current.contains(e.target)) dismissRef.current() }
    const onKey = e => { if (e.key === 'Escape') dismissRef.current() }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return ref
}

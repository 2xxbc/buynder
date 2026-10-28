import { useState } from 'react'

// One card image for the whole site.
// - Keeps the real Pokémon card shape (63 × 88) and always shows the whole card (never cropped)
// - If the image is missing or broken (~3.4% of PokeTrace images), shows a clean placeholder instead
//
// Usage:
//   <CardImage src={card.image_url} alt={card.name} className="w-16" />
//   <CardImage src={...} alt={...} className="w-64" tone="dark" />   ← on the showroom side
//
// className controls the WIDTH; the height follows automatically.
export default function CardImage({ src, alt = 'Pokémon card', className = '', tone = 'dark' }) {
  // Remember which URL failed, so a new card automatically gets a fresh chance to load
  const [brokenSrc, setBrokenSrc] = useState(null)
  const broken = brokenSrc === src

  // self-start: inside a flex row, a flex item is stretched to the row's height by default,
  // which beat the 63:88 shape on phones (a 56px-wide image became ~150px tall and got cropped).
  // A className with its own self-* (e.g. self-center) replaces it.
  const align = /(^|\s)self-/.test(className) ? '' : 'self-start'
  const shape = `aspect-[63/88] rounded-[6%/4.3%] shrink-0 ${align} ${className}`

  if (!src || broken) {
    const colors = tone === 'dark'
      ? 'bg-stage-raised border-stage-line text-chalk-soft'
      : 'bg-chalk/[0.06] border-chalk/10 text-chalk-soft'

    return (
      <div
        role="img"
        aria-label={`${alt} (image unavailable)`}
        className={`${shape} ${colors} border flex items-center justify-center overflow-hidden`}
      >
        {/* Simple card outline icon */}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-1/3 max-w-10" aria-hidden="true">
          <rect x="5" y="2.5" width="14" height="19" rx="2" />
          <circle cx="12" cy="10" r="3" />
          <path d="M8.5 17h7" strokeLinecap="round" />
        </svg>
      </div>
    )
  }

  // contain, not cover: always the WHOLE card. Scans are 0.71-0.74 wide per 1 tall, so a
  // slightly off one gets a hairline gap instead of losing its edges.
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      onError={() => setBrokenSrc(src)}
      className={`${shape} object-contain`}
    />
  )
}
import { Link } from 'react-router-dom'
import { TRENDING } from '../names'
import { btn } from '../components/ui'

// Shown for any URL that doesn't match a page
function NotFound() {
  return (
    <div className="max-w-lg mx-auto text-center glass rounded-panel px-6 py-12 sm:p-14 my-6 sm:my-12">
      <p className="font-display text-6xl sm:text-7xl font-semibold tracking-tight text-chalk/15" aria-hidden="true">404</p>
      <h1 className="font-display text-2xl sm:text-3xl font-semibold mt-2">This page isn't in the binder</h1>
      <p className="text-chalk-soft mt-3">The link may be old or mistyped. Try searching for the card from the Market.</p>
      <div className="flex flex-wrap gap-3 justify-center mt-7">
        <Link to="/" className={btn.primary}>Go to Market</Link>
        <Link to="/discovery" className={btn.secondary}>See {TRENDING}</Link>
      </div>
    </div>
  )
}

export default NotFound

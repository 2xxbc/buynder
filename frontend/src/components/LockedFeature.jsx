import { Link } from 'react-router-dom'
import { btn } from './ui'

function LockedFeature({ feature = 'this feature' }) {
  return (
    <div className="max-w-md mx-auto text-center glass rounded-panel px-6 py-10 sm:p-10 my-6 sm:my-12">
      <span className="w-14 h-14 mx-auto mb-5 rounded-full bg-chalk text-stage flex items-center justify-center" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6">
          <rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" />
        </svg>
      </span>
      <h1 className="font-display text-2xl font-semibold">Members only</h1>
      <p className="text-chalk-soft mt-2">Log in or create an account to use {feature}.</p>
      <div className="flex flex-wrap gap-3 justify-center mt-6">
        <Link to="/login" className={btn.secondary}>Log in</Link>
        <Link to="/signup" className={btn.primary}>Create account</Link>
      </div>
    </div>
  )
}

export default LockedFeature

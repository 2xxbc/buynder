import { Link } from 'react-router-dom'

// Full-screen frame for Login / Signup (these pages have no header)
export default function AuthShell({ title, subtitle, error, children, footer }) {
  return (
    <div className="min-h-screen bg-showroom text-chalk flex flex-col items-center justify-center px-4 py-10">
      <Link to="/" aria-label="Buynder home" className="mb-8 rounded-full">
        <img src="/buynder-logo.png" alt="Buynder" className="h-11 w-auto" />
      </Link>

      <main className="w-full max-w-[25rem] glass rounded-panel shadow-float px-6 py-8 sm:px-9 sm:py-10">
        <h1 className="font-display text-2xl sm:text-[1.75rem] font-semibold leading-tight tracking-tight">{title}</h1>
        <p className="text-chalk-soft mt-2 mb-7">{subtitle}</p>

        {error && (
          <p role="alert" className="mb-5 rounded-chip bg-chalk/[0.06] border border-down-bright/30 text-down-bright text-sm font-semibold px-3.5 py-2.5">
            {error}
          </p>
        )}

        {children}

        <p className="text-sm text-chalk-soft text-center mt-7">{footer}</p>
      </main>
    </div>
  )
}

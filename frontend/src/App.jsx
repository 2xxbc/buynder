import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Link, NavLink, Navigate, useLocation, useNavigationType } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import { TRENDING } from './names'
import Market from './pages/Market'
import CardDetail from './pages/CardDetail'
import Discovery from './pages/Discovery'
import Collection from './pages/Collection'
import Sold from './pages/Sold'
import Portfolio from './pages/Portfolio'
import Scanner from './pages/Scanner'
import Watchlist from './pages/Watchlist'
import Trades from './pages/Trades'
import Login from './pages/Login'
import Signup from './pages/Signup'
import SharedView from './pages/SharedView'
import SharedWithMe from './pages/SharedWithMe'
import LockedFeature from './components/LockedFeature'
import Footer from './components/Footer'
import NotFound from './pages/NotFound'

// The "My cards" group — one link in the nav, tabs inside
const MY_CARDS = [
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/collection', label: 'Collection' },
  { to: '/watchlist', label: 'Watchlist' },
  { to: '/sold', label: 'Sold' },
  { to: '/trades', label: 'Trades' },
  { to: '/shared-with-me', label: 'Shared' },
]
const isMyCards = path => MY_CARDS.some(l => path.startsWith(l.to))

// Classes for the header and phone nav (one dark theme since 2026-10-25)
const THEME = {
    bar: 'bg-stage/70 border-stage-line',
    idle: 'text-chalk-soft hover:text-chalk hover:bg-chalk/10',
    active: 'text-chalk bg-chalk/10',
    primary: 'bg-volt hover:bg-volt-deep text-stage',
    secondary: 'border border-stage-line text-chalk hover:bg-chalk/10',
    muted: 'text-chalk-soft',
    pill: 'bg-chalk text-stage',
    pillIdle: 'text-stage/60 hover:text-stage',
    pillActive: 'bg-stage text-chalk',
    pillFocus: 'focus-visible:outline-stage',
}

// ── Small line icons for the phone nav ──
const Icon = ({ children }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5" aria-hidden="true">
    {children}
  </svg>
)
const IconMarket = () => <Icon><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /></Icon>
const IconMovers = () => <Icon><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></Icon>
const IconScan = () => <Icon><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" /><rect x="9" y="8" width="6" height="8" rx="1" /></Icon>
const IconCards = () => <Icon><rect x="7" y="3" width="13" height="17" rx="2" /><path d="M4 7v12a2 2 0 0 0 2 2h9" /></Icon>

// Bouncer: if not logged in, show the "Members only" card instead of redirecting
function RequireAuth({ children, feature }) {
  const { user, loading } = useAuth()
  if (loading) {
    return <p className="text-chalk-soft text-center py-24" role="status">Loading…</p>
  }
  if (!user) {
    return <LockedFeature feature={feature} />
  }
  return children
}

// ── Top bar (desktop + phone) ──
function Header() {
  const { user, logout } = useAuth()
  const { pathname } = useLocation()
  const t = THEME

  const linkClass = active =>
    `px-4 py-2 rounded-full text-sm font-semibold transition-colors ${active ? t.active : t.idle}`

  return (
    <header className={`sticky top-0 z-30 border-b backdrop-blur-md ${t.bar}`}>
      <div className="max-w-7xl mx-auto px-4 md:px-6 h-16 md:h-20 flex items-center justify-between gap-4">
        <Link to="/" className="shrink-0" aria-label="Buynder home">
          <img src="/buynder-logo.png" alt="Buynder" className="h-9 md:h-11 w-auto" />
        </Link>

        {/* Desktop nav — 3 links + scan */}
        <nav aria-label="Main" className="hidden md:flex items-center gap-1">
          <NavLink to="/" end className={({ isActive }) => linkClass(isActive)}>Market</NavLink>
          <NavLink to="/discovery" className={({ isActive }) => linkClass(isActive)}>{TRENDING}</NavLink>
          <Link to="/portfolio" className={linkClass(isMyCards(pathname))}
            aria-current={isMyCards(pathname) ? 'page' : undefined}>
            My cards
          </Link>
          <NavLink to="/scanner" className={({ isActive }) => `${linkClass(isActive)} flex items-center gap-2`}>
            <IconScan /> Scan
          </NavLink>
        </nav>

        {/* Account */}
        <div className="flex items-center gap-2 text-sm font-semibold">
          {user ? (
            <>
              <span className={`hidden sm:inline ${t.muted}`}>{user.username}</span>
              <button onClick={logout} className={`px-4 py-2 rounded-full transition-colors ${t.secondary}`}>
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className={`px-3 py-2 rounded-full transition-colors ${t.idle}`}>Log in</Link>
              <Link to="/signup" className={`px-4 py-2 rounded-full transition-colors ${t.primary}`}>Sign up</Link>
            </>
          )}
        </div>
      </div>
    </header>
  )
}

// ── Floating pill nav (phones only) ──
function BottomNav() {
  const { pathname } = useLocation()
  const t = THEME

  const items = [
    { to: '/', label: 'Market', icon: <IconMarket />, active: pathname === '/' },
    { to: '/discovery', label: TRENDING, icon: <IconMovers />, active: pathname === '/discovery' },
    { to: '/scanner', label: 'Scan', icon: <IconScan />, active: pathname === '/scanner' },
    { to: '/portfolio', label: 'My cards', icon: <IconCards />, active: isMyCards(pathname) },
  ]

  return (
    <nav aria-label="Main"
      className="md:hidden fixed inset-x-0 z-40 flex justify-center pointer-events-none"
      style={{ bottom: 'calc(1rem + env(safe-area-inset-bottom))' }}>
      <div className={`pointer-events-auto flex items-center gap-1 rounded-full p-1.5 shadow-float ${t.pill}`}>
        {items.map(i => (
          <Link key={i.to} to={i.to} aria-current={i.active ? 'page' : undefined}
            className={`flex flex-col items-center justify-center gap-0.5 w-[4.25rem] h-12 rounded-full text-[10px] font-semibold transition-colors focus-visible:outline-offset-1 ${t.pillFocus} ${i.active ? t.pillActive : t.pillIdle}`}>
            {i.icon}
            {i.label}
          </Link>
        ))}
      </div>
    </nav>
  )
}

// ── Tabs shown on every "My cards" page ──
function MyCardsTabs() {
  return (
    <nav aria-label="My cards" className="mb-8 -mx-4 px-4 overflow-x-auto">
      <div className="inline-flex gap-1 p-1 rounded-full glass">
        {MY_CARDS.map(l => (
          <NavLink key={l.to} to={l.to}
            className={({ isActive }) =>
              `px-4 py-2 rounded-full text-sm font-semibold whitespace-nowrap transition-colors ${
                isActive ? 'bg-chalk text-stage' : 'text-chalk-soft hover:text-chalk'
              }`}>
            {l.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}

// Opening a new page starts at the top. Without this the browser keeps the old scroll
// position, so a card opened from far down a list showed its bottom half and the Back
// button was off-screen. Back/forward (POP) is left alone.
function ScrollToTop() {
  const { pathname } = useLocation()
  const navType = useNavigationType()
  useEffect(() => {
    if (navType !== 'POP') window.scrollTo(0, 0)
  }, [pathname, navType])
  return null
}

// Wraps a page with the header, the right background, and the phone nav
function WithLayout({ children }) {
  const { pathname } = useLocation()

  return (
    // Phones: room at the bottom for the floating nav pill (60px tall, 16px up, plus the iPhone
    // home-bar inset), so the end of every page can scroll fully above it
    <div className={`min-h-screen flex flex-col pb-[calc(6rem+env(safe-area-inset-bottom))] md:pb-0 bg-showroom text-chalk`}>
      <Header />
      <main className="max-w-7xl mx-auto px-4 md:px-6 pt-6 md:pt-10 pb-12 md:pb-16 w-full flex-1">
        {isMyCards(pathname) && <MyCardsTabs />}
        {children}
      </main>
      <Footer />
      <BottomNav />
    </div>
  )
}

// /trending → /discovery, keeping any ?set=… filter
function TrendingRedirect() {
  const { search } = useLocation()
  return <Navigate to={`/discovery${search}`} replace />
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ScrollToTop />
        <Routes>
          {/* Full-screen, no header */}
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Public */}
          <Route path="/" element={<WithLayout><Market /></WithLayout>} />
          <Route path="/card/saved/:productId" element={<WithLayout><CardDetail /></WithLayout>} />
          <Route path="/card/:poketraceId" element={<WithLayout><CardDetail /></WithLayout>} />
          <Route path="/shared/:token" element={<WithLayout><SharedView /></WithLayout>} />
          <Route path="/shared-with-me" element={<WithLayout><RequireAuth feature="shared collections"><SharedWithMe /></RequireAuth></WithLayout>} />
          <Route path="/discovery" element={<WithLayout><Discovery /></WithLayout>} />
          {/* The page is called Trending (names.js); its address stays /discovery so old links keep working */}
          <Route path="/trending" element={<TrendingRedirect />} />

          {/* Protected — shows "Members only" card if logged out */}
          <Route path="/portfolio" element={<WithLayout><RequireAuth feature="your portfolio"><Portfolio /></RequireAuth></WithLayout>} />
          <Route path="/collection" element={<WithLayout><RequireAuth feature="your collection"><Collection /></RequireAuth></WithLayout>} />
          <Route path="/watchlist" element={<WithLayout><RequireAuth feature="your watchlist"><Watchlist /></RequireAuth></WithLayout>} />
          <Route path="/sold" element={<WithLayout><RequireAuth feature="your sold history"><Sold /></RequireAuth></WithLayout>} />
          <Route path="/trades" element={<WithLayout><RequireAuth feature="trades"><Trades /></RequireAuth></WithLayout>} />
          <Route path="/scanner" element={<WithLayout><RequireAuth feature="the scanner"><Scanner /></RequireAuth></WithLayout>} />

          {/* Anything else */}
          <Route path="*" element={<WithLayout><NotFound /></WithLayout>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
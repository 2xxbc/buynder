import { useState } from 'react';
import { BrowserRouter, Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import Market from './pages/Market';
import Discovery from './pages/Discovery';
import Collection from './pages/Collection';
import Sold from './pages/Sold';
import Portfolio from './pages/Portfolio';
import Scanner from './pages/Scanner';
import Trades from './pages/Trades';
import Login from './pages/Login';
import Signup from './pages/Signup';
import SharedView from './pages/SharedView';
import SharedWithMe from './pages/SharedWithMe';
import LockedFeature from './components/LockedFeature';
import Footer from './components/Footer';
import './App.css';
function RequireAuth({
  children,
  feature
}) {
  const {
    user,
    loading
  } = useAuth();
  if (loading) {
    return <div className="text-slate-400 text-center py-24">Loading...</div>;
  }
  if (!user) {
    return <LockedFeature feature={feature} />;
  }
  return children;
}
function Header() {
  const {
    user,
    logout
  } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const links = [{
    to: '/',
    label: 'Market'
  }, {
    to: '/discovery',
    label: 'Movers'
  }, {
    to: '/portfolio',
    label: 'Portfolio'
  }, {
    to: '/collection',
    label: 'Collection'
  }, {
    to: '/sold',
    label: 'Sold'
  }, {
    to: '/trades',
    label: 'Trades'
  }, {
    to: '/shared-with-me',
    label: 'Shared'
  }, {
    to: '/scanner',
    label: 'Scanner'
  }];
  return <header className="border-b border-slate-700 bg-slate-800">
      <div className="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
        <Link to="/" className="flex items-center" onClick={() => setMenuOpen(false)}>
          <img src="/icon_buynder4.png" alt="Buynder" className="h-14 md:h-20 w-auto" />
        </Link>

        
        <nav className="hidden md:flex gap-6 text-sm text-slate-300 items-center">
          {links.map(l => <Link key={l.to} to={l.to} className="hover:text-white">{l.label}</Link>)}
          {user ? <div className="flex items-center gap-3 pl-6 border-l border-slate-700">
              <span className="text-slate-400">{user.username}</span>
              <button onClick={logout} className="text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 px-3 py-1 rounded transition-colors">
                Log out
              </button>
            </div> : <div className="flex items-center gap-3 pl-6 border-l border-slate-700">
              <Link to="/login" className="text-slate-300 hover:text-white">Log in</Link>
              <Link to="/signup" className="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded transition-colors">
                Sign up
              </Link>
            </div>}
        </nav>

        
        <button onClick={() => setMenuOpen(!menuOpen)} className="md:hidden text-slate-300 hover:text-white p-2" aria-label="Menu">
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {menuOpen ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /> : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />}
          </svg>
        </button>
      </div>

      
      {menuOpen && <nav className="md:hidden border-t border-slate-700 bg-slate-800 px-6 py-4 flex flex-col gap-1">
          {links.map(l => <Link key={l.to} to={l.to} onClick={() => setMenuOpen(false)} className="py-3 text-slate-300 hover:text-white border-b border-slate-700/50">
              {l.label}
            </Link>)}
          {user ? <div className="pt-4 flex items-center justify-between">
              <span className="text-slate-400">{user.username}</span>
              <button onClick={() => {
          logout();
          setMenuOpen(false);
        }} className="text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 px-4 py-2 rounded transition-colors">
                Log out
              </button>
            </div> : <div className="pt-4 flex gap-3">
              <Link to="/login" onClick={() => setMenuOpen(false)} className="flex-1 text-center text-slate-300 hover:text-white bg-slate-700 py-2 rounded">
                Log in
              </Link>
              <Link to="/signup" onClick={() => setMenuOpen(false)} className="flex-1 text-center bg-red-500 hover:bg-red-600 text-white py-2 rounded transition-colors">
                Sign up
              </Link>
            </div>}
        </nav>}
    </header>;
}
function WithLayout({
  children
}) {
  return <div className="min-h-screen bg-slate-900 text-white flex flex-col">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-10 w-full flex-1">
        {children}
      </main>
      <Footer />
    </div>;
}
function App() {
  return <AuthProvider>
      <BrowserRouter>
        <Routes>
          
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          
          <Route path="/" element={<WithLayout><Market /></WithLayout>} />
          <Route path="/shared/:token" element={<WithLayout><SharedView /></WithLayout>} />
          <Route path="/shared-with-me" element={<WithLayout><RequireAuth feature="shared collections"><SharedWithMe /></RequireAuth></WithLayout>} />
          <Route path="/discovery" element={<WithLayout><Discovery /></WithLayout>} />

          
          <Route path="/portfolio" element={<WithLayout><RequireAuth feature="your portfolio"><Portfolio /></RequireAuth></WithLayout>} />
          <Route path="/collection" element={<WithLayout><RequireAuth feature="your collection"><Collection /></RequireAuth></WithLayout>} />
          <Route path="/sold" element={<WithLayout><RequireAuth feature="your sold history"><Sold /></RequireAuth></WithLayout>} />
          <Route path="/trades" element={<WithLayout><RequireAuth feature="trades"><Trades /></RequireAuth></WithLayout>} />
          <Route path="/scanner" element={<WithLayout><RequireAuth feature="the scanner"><Scanner /></RequireAuth></WithLayout>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>;
}
export default App;

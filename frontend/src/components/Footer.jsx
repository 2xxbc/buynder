import { useState } from 'react';
const DISCORD_USERNAME = '2xxbc';
const SOCIALS = [{
  name: 'Instagram',
  href: 'https://www.instagram.com/2xxbc_/',
  icon: <path d="M12 2.2c3.2 0 3.6 0 4.9.07 1.2.05 1.8.25 2.2.42.6.22 1 .48 1.4.9.4.4.7.8.9 1.4.2.4.4 1 .4 2.2.1 1.3.1 1.7.1 4.9s0 3.6-.1 4.9c0 1.2-.2 1.8-.4 2.2-.2.6-.5 1-.9 1.4-.4.4-.8.7-1.4.9-.4.2-1 .4-2.2.4-1.3.1-1.7.1-4.9.1s-3.6 0-4.9-.1c-1.2 0-1.8-.2-2.2-.4-.6-.2-1-.5-1.4-.9-.4-.4-.7-.8-.9-1.4-.2-.4-.4-1-.4-2.2-.1-1.3-.1-1.7-.1-4.9s0-3.6.1-4.9c0-1.2.2-1.8.4-2.2.2-.6.5-1 .9-1.4.4-.4.8-.7 1.4-.9.4-.2 1-.4 2.2-.4C8.4 2.2 8.8 2.2 12 2.2m0-2.2C8.7 0 8.3 0 7 .1 5.7.1 4.8.3 4.1.6c-.8.3-1.4.7-2 1.4-.7.6-1.1 1.2-1.4 2-.3.7-.5 1.6-.5 2.9C0 8.3 0 8.7 0 12s0 3.7.1 5c.1 1.3.3 2.2.6 2.9.3.8.7 1.4 1.4 2 .6.7 1.2 1.1 2 1.4.7.3 1.6.5 2.9.5 1.3.1 1.7.1 5 .1s3.7 0 5-.1c1.3 0 2.2-.2 2.9-.5.8-.3 1.4-.7 2-1.4.7-.6 1.1-1.2 1.4-2 .3-.7.5-1.6.5-2.9.1-1.3.1-1.7.1-5s0-3.7-.1-5c0-1.3-.2-2.2-.5-2.9-.3-.8-.7-1.4-1.4-2-.6-.7-1.2-1.1-2-1.4-.7-.3-1.6-.5-2.9-.5C15.7 0 15.3 0 12 0z M12 5.8a6.2 6.2 0 100 12.4 6.2 6.2 0 000-12.4zm0 10.2a4 4 0 110-8 4 4 0 010 8z M18.4 4.2a1.4 1.4 0 100 2.9 1.4 1.4 0 000-2.9z" />
}, {
  name: 'X',
  href: 'https://x.com/2xxBc',
  icon: <path d="M18.9 1.2h3.7l-8.1 9.2 9.5 12.6h-7.5l-5.8-7.7-6.7 7.7H.3l8.6-9.9L-.2 1.2h7.7l5.3 7 6.1-7zm-1.3 19.6h2L6.5 3.3H4.3l13.3 17.5z" />
}, {
  name: 'YouTube',
  href: 'https://www.youtube.com/@2xxBc',
  icon: <path d="M23.5 6.2a3 3 0 00-2.1-2.1C19.5 3.6 12 3.6 12 3.6s-7.5 0-9.4.5A3 3 0 00.5 6.2 31 31 0 000 12a31 31 0 00.5 5.8 3 3 0 002.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 002.1-2.1A31 31 0 0024 12a31 31 0 00-.5-5.8zM9.5 15.6V8.4l6.3 3.6-6.3 3.6z" />
}];
const DISCORD_ICON = <path d="M20.3 4.4A19.8 19.8 0 0015.4 3l-.2.5c1.6.4 3 1 4.4 1.9a16.6 16.6 0 00-15.2 0c1.4-.9 2.9-1.6 4.4-1.9L8.6 3a19.8 19.8 0 00-4.9 1.4C.6 9 0 13.4.3 17.8a19.9 19.9 0 006 3c.5-.7.9-1.4 1.3-2.1-.7-.3-1.4-.6-2-1 .2-.1.3-.3.5-.4a14.2 14.2 0 0011.9 0c.2.1.3.3.5.4-.6.4-1.3.7-2 1 .4.7.8 1.4 1.3 2.1a19.9 19.9 0 006-3c.4-5.1-.6-9.5-3.5-13.4zM8.1 15.1c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.2 1.1 2.2 2.4-1 2.4-2.2 2.4zm7.8 0c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.2 1.1 2.2 2.4-1 2.4-2.2 2.4z" />;
const iconClass = "w-10 h-10 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-amber-500 flex items-center justify-center text-slate-400 hover:text-amber-400 transition-colors";
function Footer() {
  const [copied, setCopied] = useState(false);
  function copyDiscord() {
    navigator.clipboard.writeText(DISCORD_USERNAME);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return <footer className="border-t border-slate-800 bg-slate-900/50 mt-20">
      <div className="max-w-7xl mx-auto px-6 py-10">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6 mb-8">
          <div>
            <p className="text-xl font-bold">
              <span className="text-red-500">Buynder</span><span className="text-white">Market</span>
            </p>
            <p className="text-sm text-slate-500 mt-1">Pokémon card price tracking & collection management.</p>
          </div>

          <div className="flex items-center gap-3">
            {SOCIALS.map(s => <a key={s.name} href={s.href} target="_blank" rel="noopener noreferrer" aria-label={s.name} title={s.name} className={iconClass}>
                <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">{s.icon}</svg>
              </a>)}

            <button onClick={copyDiscord} aria-label="Copy Discord username" title={copied ? 'Copied!' : `Discord: ${DISCORD_USERNAME}`} className={iconClass}>
              <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">{DISCORD_ICON}</svg>
            </button>

            {copied && <span className="text-xs text-amber-400">Copied {DISCORD_USERNAME}</span>}
          </div>
        </div>

        <div className="border-t border-slate-800 pt-6 space-y-3">
          <p className="text-xs text-slate-500 leading-relaxed">
            Pokémon and all respective names are trademarks and © of Nintendo, The Pokémon Company,
            Creatures Inc., and GAME FREAK inc. 1996–{new Date().getFullYear()}. BuynderMarket is an
            independent, fan-made price-tracking service and is not affiliated with, endorsed by, or
            sponsored by Nintendo, The Pokémon Company, Creatures Inc., GAME FREAK inc., TCGPlayer,
            eBay, or any grading company. All card names and imagery are used solely for
            identification and price-tracking purposes.
          </p>
          <p className="text-xs text-slate-500">
            Price data is provided for informational purposes only and may be delayed or inaccurate.
            Nothing here is financial advice.
          </p>
          <p className="text-xs text-slate-600">
            © {new Date().getFullYear()} BuynderMarket. All rights reserved.
          </p>
        </div>
      </div>
    </footer>;
}
export default Footer;

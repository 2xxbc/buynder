import { Link } from 'react-router-dom';
function LockedFeature({
  feature = 'this feature'
}) {
  return <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl p-10 max-w-md">
        <div className="w-14 h-14 mx-auto mb-5 rounded-full bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center text-2xl">
          🔒
        </div>
        <h2 className="text-2xl font-bold mb-2">Members only</h2>
        <p className="text-slate-400 mb-6">
          Log in or create an account to use {feature}.
        </p>
        <div className="flex gap-3 justify-center">
          <Link to="/login" className="px-5 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white font-semibold transition-colors">
            Log in
          </Link>
          <Link to="/signup" className="px-5 py-2 rounded-lg bg-gradient-to-r from-amber-500 to-orange-600 hover:opacity-90 text-white font-semibold transition-opacity">
            Create account
          </Link>
        </div>
      </div>
    </div>;
}
export default LockedFeature;

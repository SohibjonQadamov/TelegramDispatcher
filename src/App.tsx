import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Dashboard } from './pages/Dashboard';
import { Products } from './pages/Products';
import { Orders } from './pages/Orders';
import { Analytics } from './pages/Analytics';
import { Settings } from './pages/Settings';

type Page = 'dashboard' | 'products' | 'orders' | 'analytics' | 'settings';

export default function App() {
  const [page, setPage] = useState<Page>('dashboard');

  const renderPage = () => {
    switch (page) {
      case 'dashboard': return <Dashboard />;
      case 'products': return <Products />;
      case 'orders': return <Orders />;
      case 'analytics': return <Analytics />;
      case 'settings': return <Settings />;
    }
  };

  const navItems = [
    { id: 'dashboard' as Page, label: 'Asosiy', icon: '📊' },
    { id: 'products' as Page, label: 'Maxsulotlar', icon: '🍕' },
    { id: 'orders' as Page, label: 'Buyurtmalar', icon: '📋' },
    { id: 'analytics' as Page, label: 'Analitika', icon: '📈' },
    { id: 'settings' as Page, label: 'Sozlamalar', icon: '⚙️' },
  ];

  return (
    <div className="min-h-screen bg-surface pb-24">
      <header className="fixed top-0 w-full z-50 bg-surface border-b border-outline-variant px-4 py-3 flex justify-between items-center">
        <h1 className="text-xl font-bold tracking-tight">Lazzat Admin</h1>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-primary-container text-white flex items-center justify-center text-sm font-bold">A</div>
        </div>
      </header>

      <main className="pt-16 px-4 max-w-5xl mx-auto">
        <AnimatePresence mode="wait">
          <motion.div key={page} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.3 }}>
            {renderPage()}
          </motion.div>
        </AnimatePresence>
      </main>

      <nav className="fixed bottom-0 w-full bg-primary-container flex justify-around py-2 px-1 rounded-t-2xl z-50">
        {navItems.map(item => (
          <button key={item.id} onClick={() => setPage(item.id)} className={`flex flex-col items-center gap-1 px-3 py-2 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all ${page === item.id ? 'bg-secondary text-white' : 'text-white/60'}`}>
            <span className="text-lg">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
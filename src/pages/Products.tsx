import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { PRODUCTS } from '../constants';

export function Products() {
  const [filter, setFilter] = useState('all');
  const categories = ['all', 'Pitsalar', 'Burgerlar', 'Ichimliklar'];
  const filtered = filter === 'all' ? PRODUCTS : PRODUCTS.filter(p => p.category === filter);

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold mt-2">Mahsulotlar</h2>

      <div className="flex gap-2 overflow-x-auto no-scrollbar">
        {categories.map(c => (
          <button key={c} onClick={() => setFilter(c)} className={`px-4 py-2 rounded-full text-[11px] font-bold uppercase tracking-wider whitespace-nowrap transition-all ${filter===c?'bg-secondary text-white':'bg-white border border-outline-variant'}`}>
            {c==='all'?'Barchasi':c}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <AnimatePresence>
          {filtered.map(p => (
            <motion.div key={p.id} layout initial={{ opacity:0, scale:0.9 }} animate={{ opacity:1, scale:1 }} exit={{ opacity:0, scale:0.9 }} className="bg-white rounded-2xl overflow-hidden border border-outline-variant">
              <img src={p.image} alt={p.name} className="w-full h-28 object-cover" />
              <div className="p-3">
                <div className="font-bold text-sm">{p.name}</div>
                <div className="text-[10px] text-on-surface-variant">{p.category} • {p.weight}</div>
                <div className="font-bold text-secondary mt-1">{p.price.toLocaleString()} so'm</div>
                <span className={`inline-block px-2 py-0.5 rounded-lg text-[9px] font-bold uppercase mt-1 ${p.status==='sotuvda'?'bg-green-100 text-green-700':'bg-red-100 text-red-700'}`}>{p.status}</span>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
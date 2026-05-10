import { useState } from 'react';
import { motion } from 'motion/react';
import { ORDERS } from '../constants';

export function Orders() {
  const [filter, setFilter] = useState('all');
  const statuses = ['all', 'yangi', 'jarayonda', 'yetkazilmoqda'];
  const filtered = filter === 'all' ? ORDERS : ORDERS.filter(o => o.status === filter);

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold mt-2">Buyurtmalar</h2>

      <div className="flex gap-2 overflow-x-auto no-scrollbar">
        {statuses.map(s => (
          <button key={s} onClick={() => setFilter(s)} className={`px-4 py-2 rounded-full text-[11px] font-bold uppercase tracking-wider whitespace-nowrap transition-all ${filter===s?'bg-secondary text-white':'bg-white border border-outline-variant'}`}>
            {s==='all'?'Barchasi':s}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {filtered.map(o => (
          <motion.div key={o.id} initial={{ opacity:0, y:10 }} animate={{ opacity:1, y:0 }} className="bg-white rounded-2xl p-4 border border-outline-variant border-l-4" style={{ borderLeftColor: o.status==='yangi'?'#af2b3e':o.status==='jarayonda'?'#f59e0b':'#059669' }}>
            <div className="flex justify-between items-start">
              <div>
                <div className="text-xs font-bold text-secondary">{o.id} • {o.time}</div>
                <div className="font-bold mt-1">{o.customerName}</div>
                <div className="text-[11px] text-on-surface-variant">📞 {o.phone}</div>
              </div>
            </div>
            <div className="text-xl font-bold mt-3">{o.amount.toLocaleString()} UZS</div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
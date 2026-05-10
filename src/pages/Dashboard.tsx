import { motion } from 'motion/react';

export function Dashboard() {
  const stats = [
    { label:'Bugungi buyurtmalar', value:'142', trend:'+12%', color:'bg-primary-fixed', icon:'📦' },
    { label:'Daromad', value:'14.2M', trend:'+8.4%', color:'bg-secondary-fixed', icon:'💰' },
    { label:'Faol kuryerlar', value:'24', trend:'', color:'bg-green-50', icon:'🚗' },
    { label:'Reyting', value:'4.85', trend:'', color:'bg-yellow-50', icon:'⭐' },
  ];

  const chartData = [75,50,80,65,100,60,90];
  const days = ['Du','Se','Ch','Pa','Ju','Sh','Ya'];

  return (
    <div className="space-y-5">
      <h2 className="text-2xl font-bold mt-2">Dashboard</h2>

      <div className="grid grid-cols-2 gap-3">
        {stats.map((s, i) => (
          <motion.div key={i} initial={{ opacity:0, scale:0.9 }} animate={{ opacity:1, scale:1 }} transition={{ delay: i*0.1 }} className="bg-white rounded-2xl p-4 border border-outline-variant">
            <div className="w-9 h-9 rounded-xl bg-surface-container flex items-center justify-center text-lg mb-2">{s.icon}</div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">{s.label}</div>
            <div className="text-2xl font-bold mt-0.5">{s.value}</div>
            {s.trend && <div className="text-[10px] font-bold text-green-600 mt-0.5">{s.trend}</div>}
          </motion.div>
        ))}
      </div>

      <div className="bg-white rounded-2xl p-5 border border-outline-variant">
        <h3 className="font-bold mb-4">Haftalik daromad</h3>
        <div className="flex items-end justify-between h-28">
          {chartData.map((v, i) => (
            <div key={i} className="text-center">
              <motion.div initial={{ height: 0 }} animate={{ height: v }} transition={{ delay: i*0.1 }} className={`w-7 rounded-t-md ${i===4?'bg-secondary':'bg-primary-container'}`} style={{ height: v+'%', minHeight: 4 }} />
              <div className="text-[9px] text-on-surface-variant mt-1">{days[i]}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <button className="w-full py-3.5 bg-primary text-white rounded-xl font-bold">➕ Mahsulot qo'shish</button>
        <button className="w-full py-3.5 bg-white border border-outline-variant rounded-xl font-bold">📝 Menyuni tahrirlash</button>
      </div>
    </div>
  );
}
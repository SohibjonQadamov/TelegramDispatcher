import { useState } from 'react';

export function Settings() {
  const [notifOrders, setNotifOrders] = useState(true);
  const [notifChat, setNotifChat] = useState(true);

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold mt-2">Sozlamalar</h2>

      <div className="bg-white rounded-2xl p-5 border border-outline-variant space-y-4">
        <h3 className="font-bold">Asosiy ma'lumotlar</h3>
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Restoran nomi</label>
          <input className="w-full p-3 mt-1 rounded-xl border border-outline-variant bg-surface-container-low" defaultValue="Lazzat Premium Grill" />
        </div>
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Manzil</label>
          <input className="w-full p-3 mt-1 rounded-xl border border-outline-variant bg-surface-container-low" defaultValue="Toshkent, Yunusobod" />
        </div>
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Telefon</label>
          <input className="w-full p-3 mt-1 rounded-xl border border-outline-variant bg-surface-container-low" defaultValue="+998 90 123 45 67" />
        </div>
      </div>

      <div className="bg-white rounded-2xl p-5 border border-outline-variant space-y-3">
        <h3 className="font-bold">Bildirishnomalar</h3>
        <div className="flex justify-between items-center">
          <span className="text-sm">Yangi buyurtmalar</span>
          <button onClick={() => setNotifOrders(!notifOrders)} className={`w-11 h-6 rounded-full transition-all relative ${notifOrders?'bg-secondary':'bg-outline-variant'}`}>
            <div className={`w-5 h-5 rounded-full bg-white absolute top-0.5 transition-all ${notifOrders?'left-[22px]':'left-0.5'}`} />
          </button>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm">Xabarlar</span>
          <button onClick={() => setNotifChat(!notifChat)} className={`w-11 h-6 rounded-full transition-all relative ${notifChat?'bg-secondary':'bg-outline-variant'}`}>
            <div className={`w-5 h-5 rounded-full bg-white absolute top-0.5 transition-all ${notifChat?'left-[22px]':'left-0.5'}`} />
          </button>
        </div>
      </div>
    </div>
  );
}
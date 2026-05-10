import { Product, Order } from './types';

export const PRODUCTS: Product[] = [
  { id:'1', name:'Margarita Pitsa', category:'Pitsalar', weight:'450g', price:65000, status:'sotuvda', image:'https://images.unsplash.com/photo-1574071318508-1cdbad80ad50?w=400&q=80' },
  { id:'2', name:'Double Burger', category:'Burgerlar', weight:'380g', price:48000, status:'sotuvda', image:'https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=400&q=80' },
  { id:'3', name:'Klassik Limonad', category:'Ichimliklar', weight:'0.5L', price:22000, status:'tugagan', image:'https://images.unsplash.com/photo-1621506289937-a8e4df240d0b?w=400&q=80' },
  { id:'4', name:'Pepperoni', category:'Pitsalar', weight:'480g', price:72000, status:'sotuvda', image:'https://images.unsplash.com/photo-1628840042765-356cda07504e?w=400&q=80' },
];

export const ORDERS: Order[] = [
  { id:'#A8492', customerName:'Alisher Usmonov', phone:'+998 90 123 45 67', time:'12:45', amount:113000, status:'yangi' },
  { id:'#A8495', customerName:'Malika Ergasheva', phone:'+998 99 987 65 43', time:'13:10', amount:45000, status:'jarayonda' },
  { id:'#A8496', customerName:'Javohir Karimov', phone:'+998 93 456 78 90', time:'12:55', amount:185000, status:'yetkazilmoqda' },
];
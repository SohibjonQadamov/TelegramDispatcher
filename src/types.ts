export interface Product {
  id: string;
  name: string;
  category: string;
  weight: string;
  price: number;
  status: 'sotuvda' | 'tugagan';
  image: string;
}

export interface Order {
  id: string;
  customerName: string;
  phone: string;
  time: string;
  amount: number;
  status: 'yangi' | 'jarayonda' | 'yetkazilmoqda';
}
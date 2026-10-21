"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { Order, localTime, money, statusLabel } from "../../lib/types";
export default function Orders() {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const token = localStorage.getItem("stitchcore_access");
    if (!token) { location.replace("/login"); return; }
    api<Order[]>("/orders/", {}, token).then(setOrders).catch(() => setError("Could not load your orders. Please sign in again or retry."));
  }, []);
  return <section><h1>Your orders</h1>{error && <p role="alert" className="notice">{error}</p>}
    {!orders && !error && <p>Loading orders…</p>}
    {orders?.length === 0 && <p>No orders yet. <a href="/order/new">Arrange your first pickup.</a></p>}
    <div className="grid">{orders?.map(order => <a className="card" href={`/orders/${order.id}`} key={order.id}>
      <p className="eyebrow">{statusLabel(order.status)}</p><h2>{order.order_number}</h2>
      <p>{localTime(order.created_at)}</p><strong>{money(order.total_paise)}</strong>
    </a>)}</div>
  </section>;
}

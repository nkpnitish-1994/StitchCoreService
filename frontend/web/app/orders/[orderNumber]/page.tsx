"use client";
import { use, useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { Order, localTime, money, statusLabel } from "../../../lib/types";
export default function OrderDetail({ params }: { params: Promise<{ orderNumber: string }> }) {
  const { orderNumber } = use(params);
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const token = localStorage.getItem("stitchcore_access");
    if (!token) { location.replace("/login"); return; }
    async function load() {
      try {
        const orders = await api<Order[]>("/orders/", {}, token!);
        const found = orders.find(o => o.id === orderNumber || o.order_number === orderNumber);
        if (!found) { setError("Order not found in your account."); return; }
        setOrder(await api<Order>(`/orders/${found.id}/`, {}, token!));
      } catch { setError("Could not load this order. Please sign in again or retry."); }
    }
    void load();
  }, [orderNumber]);
  if (error) return <p role="alert" className="notice">{error}</p>;
  if (!order) return <p>Loading your order…</p>;
  return <section><p className="eyebrow">{statusLabel(order.status)}</p><h1>{order.order_number}</h1>
    <p>Total {money(order.total_paise)} · Pickup {order.pickup_window}</p>
    <p>{order.address.line1}, {order.address.city} {order.address.postal_code}</p>
    <p>{order.expected_delivery_date ? `Expected return: ${order.expected_delivery_date}` : "Our team will confirm your return date."}</p>
    <h2>Your garments</h2><div className="grid">{order.garments.map(g => <article className="card" key={g.id}>
      <h3>{g.quantity} × {g.colour} {g.garment_type}</h3><p>{g.qr_code}</p>
      {g.alterations.map((a, i) => <p key={i}>{statusLabel(a.service_code.split(".").pop() ?? a.service_code)}{a.notes ? ` · ${a.notes}` : ""}</p>)}
    </article>)}</div>
    <h2>Order timeline</h2><ol className="timeline">{order.status_events.map(event => <li key={event.id}>
      <strong>{statusLabel(event.to_status)}</strong><p>{localTime(event.created_at)}</p>{event.note && <p>{event.note}</p>}
    </li>)}</ol><a className="button secondary" href="/orders">All orders</a>
  </section>;
}

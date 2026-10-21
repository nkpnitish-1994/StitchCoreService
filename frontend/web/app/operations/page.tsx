"use client";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import { Order, localTime, money, statusLabel } from "../../lib/types";

type Options = { logistics_partners: { id: number; username: string; first_name: string }[]; vendors: { id: number; name: string }[]; transitions: Record<string, string[]> };
export default function Operations() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [options, setOptions] = useState<Options | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const token = () => localStorage.getItem("stitchcore_access") ?? undefined;
  async function load() {
    const user = await api<{ role: string }>("/auth/me", {}, token());
    if (user.role !== "admin") { location.replace("/orders"); return; }
    const [data, choices] = await Promise.all([api<Order[]>("/orders/", {}, token()), api<Options>("/operations/options", {}, token())]);
    setOrders(data); setOptions(choices); setReady(true);
  }
  useEffect(() => {
    if (!token()) { location.replace("/login"); return; }
    load().catch(() => setError("Could not load operations. Sign in again or retry."));
  }, []);
  return <section><p className="eyebrow">OPERATIONS · RESTRICTED BETA</p><h1>Manage orders</h1>
    <p>Assign collection and record each handover. Every action is saved to the customer timeline.</p>
    {error && <p className="notice" role="alert">{error}</p>}
    <div className="toolbar"><label>Search orders<input value={filter} placeholder="Order number or status" onChange={e => setFilter(e.target.value)} /></label>
      <button className="secondary" onClick={() => load().catch(() => setError("Refresh failed. Please retry."))}>Refresh orders</button></div>
    {!ready ? <p>Loading operations…</p> : !orders.length ? <div className="card">No orders yet. Place a request using the beta customer account.</div> : orders.filter(o => `${o.order_number} ${o.status}`.toLowerCase().includes(filter.toLowerCase())).map(order =>
      <OrderActions key={order.id} order={order} options={options!} reload={load} />)}
  </section>;
}

function OrderActions({ order, options, reload }: { order: Order; options: Options; reload: () => Promise<void> }) {
  const [partner, setPartner] = useState(String(order.logistics_partner_id ?? ""));
  const [vendor, setVendor] = useState(String(order.vendor_id ?? ""));
  const [next, setNext] = useState("");
  const [note, setNote] = useState("");
  const [proof, setProof] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function action(path: string, body: object) {
    setBusy(true); setMessage("");
    try {
      await api(`/orders/${order.id}/${path}/`, { method: "POST", body: JSON.stringify(body) }, localStorage.getItem("stitchcore_access") ?? undefined);
      await reload(); setNext(""); setNote(""); setProof(""); setMessage("Saved to the order timeline.");
    } catch (error) { setMessage((error as ApiError).message ?? "Could not save. Please retry."); }
    finally { setBusy(false); }
  }
  function assign(e: FormEvent) {
    e.preventDefault();
    void action("assign", { ...(partner ? { logistics_partner_id: Number(partner) } : {}), ...(vendor ? { vendor_id: Number(vendor) } : {}) });
  }
  return <article className="card operation-order"><p className="eyebrow">{statusLabel(order.status)}</p><h2><a href={`/orders/${order.id}`}>{order.order_number}</a></h2>
    <p>{localTime(order.created_at)} · {money(order.total_paise)} · Pickup {order.pickup_window}</p>
    <p>{order.address.line1}, {order.address.city} {order.address.postal_code}</p>
    <ul>{order.garments.map(g => <li key={g.id}>{g.quantity} × {g.colour} {g.garment_type} · {g.qr_code}</li>)}</ul>
    {!["delivered", "cancelled"].includes(order.status) && <form className="form" onSubmit={assign}>
      <label>Logistics partner<select value={partner} onChange={e => setPartner(e.target.value)}><option value="">Choose a partner</option>{options.logistics_partners.map(p => <option key={p.id} value={p.id}>{p.first_name || p.username}</option>)}</select></label>
      <label>Alteration vendor<select value={vendor} onChange={e => setVendor(e.target.value)}><option value="">Choose a vendor</option>{options.vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>
      <button disabled={busy || (!partner && !vendor)}>Save assignment</button>
    </form>}
    {!!options.transitions[order.status]?.length && <form className="form" onSubmit={e => { e.preventDefault(); void action("status", { status: next, note, proof_url: proof }); }}>
      <label>Next status<select required value={next} onChange={e => setNext(e.target.value)}><option value="">Choose a valid next step</option>{options.transitions[order.status].map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}</select></label>
      <label>Custody / quality notes<textarea maxLength={1000} value={note} onChange={e => setNote(e.target.value)} /></label>
      <label>Proof URL (optional)<input type="url" value={proof} onChange={e => setProof(e.target.value)} /></label>
      <button disabled={busy || !next}>{busy ? "Saving…" : "Record status"}</button>
    </form>}
    {message && <p className="notice" role="status">{message}</p>}
  </article>;
}

"use client";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError } from "../../../lib/api";
import { Address, Order, Service, money } from "../../../lib/types";

type Garment = { service_code: string; colour: string; quantity: number; mode: string; amount: number; unit: string; notes: string };
const blank = (): Garment => ({ service_code: "", colour: "", quantity: 1, mode: "pickup_measurement", amount: 1, unit: "in", notes: "" });
export default function NewOrder() {
  const [services, setServices] = useState<Service[]>([]);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [addressId, setAddressId] = useState("");
  const [garments, setGarments] = useState<Garment[]>([blank()]);
  const [window, setWindow] = useState("17:00–20:00");
  const [address, setAddress] = useState({ label: "Home", line1: "", city: "", postal_code: "" });
  const [quote, setQuote] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [ready, setReady] = useState(false);
  const token = () => localStorage.getItem("stitchcore_access") ?? undefined;
  useEffect(() => {
    if (!token()) { location.replace("/login"); return; }
    Promise.all([api<Service[]>("/catalog/services"), api<Address[]>("/addresses/", {}, token())])
      .then(([catalog, saved]) => { setServices(catalog); setAddresses(saved); setAddressId(saved[0] ? String(saved[0].id) : ""); setReady(true); })
      .catch(() => setMessage("We could not load your order details. Sign in again or retry."));
  }, []);
  function change(index: number, values: Partial<Garment>) {
    setGarments(items => items.map((item, i) => i === index ? { ...item, ...values } : item));
    setQuote(null);
  }
  function payload() {
    return garments.map(g => {
      const service = services.find(s => s.code === g.service_code);
      if (!service) throw { message: "Choose an alteration for every garment." };
      const key = g.service_code.endsWith("reduce_waist") ? "waist_reduce_by" : "shorten_by";
      return { garment_type: service.garment_type, colour: g.colour, quantity: g.quantity,
        alterations: [{ service_code: g.service_code, notes: g.notes, measurement_data: {
          schema_version: 1, measurement_mode: g.mode, unit: g.unit,
          values: g.mode === "pickup_measurement" ? {} : { [key]: g.amount },
        } }] };
    });
  }
  async function saveAddress(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMessage("");
    try {
      const saved = await api<Address>("/addresses/", { method: "POST", body: JSON.stringify(address) }, token());
      setAddresses(items => [...items, saved]); setAddressId(String(saved.id)); setQuote(null);
      setMessage("Pickup address saved.");
    } catch (error) { setMessage((error as ApiError).message ?? "Could not save your address."); }
    finally { setBusy(false); }
  }
  async function price() {
    setBusy(true); setMessage("");
    try {
      const items = payload();
      const result = await api<{ total_paise: number }>("/orders/quote", { method: "POST", body: JSON.stringify({
        address_id: Number(addressId),
        garments: items.map(g => ({ ...g, alterations: g.alterations.map(a => ({ service_code: a.service_code, measurement: a.measurement_data })) })),
      }) }, token());
      setQuote(result.total_paise);
    } catch (error) { setMessage((error as ApiError).message ?? "Please check your details."); }
    finally { setBusy(false); }
  }
  async function confirm() {
    setBusy(true); setMessage("");
    try {
      const body = JSON.stringify({ address_id: Number(addressId), pickup_window: window, garments: payload() });
      const previous = JSON.parse(sessionStorage.getItem("stitchcore_order_attempt") ?? "null");
      const attempt = previous?.body === body ? previous : { body, key: crypto.randomUUID() };
      sessionStorage.setItem("stitchcore_order_attempt", JSON.stringify(attempt));
      const order = await api<Order>("/orders/", { method: "POST", body, headers: { "Idempotency-Key": attempt.key } }, token());
      sessionStorage.removeItem("stitchcore_order_attempt");
      location.href = `/orders/${order.id}`;
    } catch (error) { setMessage((error as ApiError).message ?? "Could not place your order. You can safely retry."); }
    finally { setBusy(false); }
  }
  return <section><p className="eyebrow">YOUR NEXT PERFECT FIT</p><h1>Tell us what needs fixing</h1>
    {message && <p className="notice" role="status">{message}</p>}
    {!ready ? <p>Loading your saved details…</p> : <>
      <h2>1. Pickup address</h2>
      {!!addresses.length && <label className="form">Choose an address<select value={addressId} onChange={e => { setAddressId(e.target.value); setQuote(null); }}>
        {addresses.map(a => <option key={a.id} value={a.id}>{a.label}: {a.line1}, {a.city}</option>)}
      </select></label>}
      <details open={!addresses.length}><summary>Add a pickup address</summary>
        <form className="form" onSubmit={saveAddress}>
          <label>Street and apartment<input required autoComplete="street-address" value={address.line1} onChange={e => setAddress({ ...address, line1: e.target.value })} /></label>
          <label>City<input required autoComplete="address-level2" value={address.city} onChange={e => setAddress({ ...address, city: e.target.value })} /></label>
          <label>PIN code<input required inputMode="numeric" pattern="[0-9]{6}" autoComplete="postal-code" value={address.postal_code} onChange={e => setAddress({ ...address, postal_code: e.target.value })} /></label>
          <button disabled={busy}>Save address</button>
        </form>
      </details>
      <h2>2. Garments and alterations</h2>
      {garments.map((g, index) => <fieldset className="card form" key={index}><legend>Garment {index + 1}</legend>
        <label>Alteration<select required value={g.service_code} onChange={e => change(index, { service_code: e.target.value })}>
          <option value="">Choose an alteration</option>{services.map(s => <option key={s.code} value={s.code}>{s.name} · {money(s.base_price_paise)}</option>)}
        </select></label>
        <label>Colour<input value={g.colour} onChange={e => change(index, { colour: e.target.value })} /></label>
        <label>Number of garments<input type="number" min="1" max="10" value={g.quantity} onChange={e => change(index, { quantity: Number(e.target.value) })} /></label>
        <label>Measurements<select value={g.mode} onChange={e => change(index, { mode: e.target.value })}>
          <option value="pickup_measurement">Help me measure at pickup</option><option value="alteration_delta">I know how much to reduce / shorten</option>
        </select></label>
        {g.mode === "alteration_delta" && <><label>Reduce or shorten by<input type="number" min="0.1" step="0.1" value={g.amount} onChange={e => change(index, { amount: Number(e.target.value) })} /></label>
          <label>Unit<select value={g.unit} onChange={e => change(index, { unit: e.target.value })}><option value="in">Inches</option><option value="cm">Centimetres</option></select></label></>}
        <label>Anything we should know?<textarea value={g.notes} onChange={e => change(index, { notes: e.target.value })} /></label>
        {garments.length > 1 && <button type="button" className="secondary" onClick={() => { setGarments(items => items.filter((_, i) => i !== index)); setQuote(null); }}>Remove garment</button>}
      </fieldset>)}
      {!services.length && <p>Our service catalogue is being prepared. Please check back soon.</p>}
      <button className="secondary" onClick={() => { setGarments(items => [...items, blank()]); setQuote(null); }}>Add another garment</button>
      <h2>3. Review pickup</h2>
      <label className="form">Preferred pickup window<input value={window} onChange={e => { setWindow(e.target.value); setQuote(null); }} /></label>
      <p>Operations will confirm availability and the return date before collection.</p>
      <button disabled={busy || !addressId || !services.length} onClick={price}>{busy ? "Please wait…" : "Review price"}</button>
      {quote !== null && <div className="card review"><h2>Total: {money(quote)}</h2><p>Review your details above. Online payment is not available in this beta.</p>
        <button disabled={busy} onClick={confirm}>{busy ? "Placing your order…" : "Confirm pickup request"}</button></div>}
    </>}
  </section>;
}

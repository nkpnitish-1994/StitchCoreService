export type Service = { code: string; name: string; garment_type: string; base_price_paise: number };
export type Address = { id: number; label: string; line1: string; city: string; postal_code: string };
export type Order = {
  id: string; order_number: string; status: string; total_paise: number;
  pickup_window: string; created_at: string; expected_delivery_date: string | null;
  logistics_partner_id: number | null; vendor_id: number | null;
  garments: { id: string; garment_type: string; colour: string; quantity: number; qr_code: string;
    alterations: { service_code: string; notes: string }[] }[];
  address: Address;
  status_events: { id: number; to_status: string; note: string; created_at: string }[];
};
export const money = (paise: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(paise / 100);
export const statusLabel = (value: string) => value.replaceAll("_", " ");
export const localTime = (value: string) => new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short",
}).format(new Date(value));

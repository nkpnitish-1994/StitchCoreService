"use client";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
export default function Login() {
  const [phone, setPhone] = useState("+91");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [message, setMessage] = useState("");
  const [beta, setBeta] = useState<boolean | null>(null);
  const [username, setUsername] = useState("beta-customer");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ beta_sign_in: boolean }>("/auth/config").then(data => setBeta(data.beta_sign_in))
      .catch(() => setMessage("Sign-in is temporarily unavailable. Please refresh to retry."));
  }, []);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMessage("");
    try {
      if (!beta && !sent) {
        await api("/auth/otp/request", { method: "POST", body: JSON.stringify({ phone }) });
        setSent(true); setMessage("OTP sent. Enter the six-digit code.");
      } else {
        const data = await api<{ access: string; refresh: string; user: { role: string } }>(beta ? "/auth/beta/session" : "/auth/otp/verify",
          { method: "POST", body: JSON.stringify(beta ? { username, password } : { phone, code }) });
        localStorage.setItem("stitchcore_access", data.access);
        localStorage.setItem("stitchcore_refresh", data.refresh);
        location.href = data.user.role === "admin" ? "/operations" : "/order/new";
      }
    } catch (error) { setMessage((error as ApiError).message ?? "Could not sign in. Please try again."); }
    finally { setBusy(false); }
  }
  return <section><p className="eyebrow">{beta ? "RESTRICTED BETA" : "WELCOME BACK"}</p><h1>Sign in</h1>
    {beta && <p>Use the test-account password shared by your administrator. This beta does not send phone OTPs or accept payments.</p>}
    <form className="form" onSubmit={submit}>
      {beta ? <><label>Test account<input required autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label>Password<input required type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label></>
        : <><label>Phone number<input required type="tel" autoComplete="tel" value={phone} onChange={e => setPhone(e.target.value)} /></label>
          {sent && <label>OTP<input required inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={e => setCode(e.target.value)} /></label>}</>}
      <button disabled={busy || beta === null}>{busy ? "Please wait…" : beta ? "Sign in to beta" : sent ? "Verify and continue" : "Send OTP"}</button>
      {message && <p className="notice" role="status">{message}</p>}
    </form><p><a href="/admin/">Staff operations sign-in</a></p>
  </section>;
}

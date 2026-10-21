"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
export default function SessionNav() {
  const [role, setRole] = useState("");
  useEffect(() => {
    const token = localStorage.getItem("stitchcore_access");
    if (token) api<{ role: string }>("/auth/me", {}, token).then(user => setRole(user.role)).catch(() => {});
  }, []);
  return <nav>{role === "admin" && <a href="/operations">Operations</a>}<a href="/orders">My orders</a>{role ? <button className="nav-button" onClick={() => {
    localStorage.removeItem("stitchcore_access"); localStorage.removeItem("stitchcore_refresh"); sessionStorage.clear(); location.assign("/login");
  }}>Sign out</button> : <a href="/login">Sign in</a>}</nav>;
}

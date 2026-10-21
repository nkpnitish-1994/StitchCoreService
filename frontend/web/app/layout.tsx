import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = { title: "StitchCore", description: "Alterations, collected and returned." };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><header><a href="/">STITCHCORE</a><nav><a href="/orders">My orders</a><a href="/login">Sign in</a></nav></header><main>{children}</main><footer>Alterations, collected and returned.</footer></body></html>;
}


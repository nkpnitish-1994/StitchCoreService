import type { Metadata } from "next";
import "./styles.css";
import SessionNav from "./session-nav";

export const metadata: Metadata = { title: "StitchCore", description: "Alterations, collected and returned." };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><header><a href="/">STITCHCORE</a><SessionNav /></header><main>{children}</main><footer>StitchCore beta · Test accounts only. No real pickups or payments.</footer></body></html>;
}


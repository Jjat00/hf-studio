import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { Nav } from "@/components/nav";
import "./globals.css";

// Inter con eje óptico (opsz 14–32): en tamaños grandes se comporta como Inter Display.
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], axes: ["opsz"] });
const grotesk = Space_Grotesk({ variable: "--font-grotesk", subsets: ["latin"], weight: ["500", "700"] });

export const metadata: Metadata = {
  title: "HF Studio",
  description: "Your own AI video and image studio on top of Higgsfield",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${grotesk.variable} h-full`}>
      <body className="flex min-h-full flex-col" style={{ fontOpticalSizing: "auto" }}>
        <Nav />
        <main className="flex min-h-0 flex-1 flex-col">{children}</main>
      </body>
    </html>
  );
}

import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { I18nProvider } from "@/components/i18n";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], axes: ["opsz"] });
const grotesk = Space_Grotesk({ variable: "--font-grotesk", subsets: ["latin"], weight: ["500", "700"] });

// Dominio de producción que da Vercel (o uno propio con NEXT_PUBLIC_SITE_URL).
const SITE =
  process.env.NEXT_PUBLIC_SITE_URL ??
  (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : "http://localhost:3100");

const title = "HF Studio · Tu propio estudio de IA, open source";
const description =
  "Estudio de IA open source sobre Higgsfield y ElevenLabs: 82 modelos de video e imagen, voces, música y efectos, y un servidor MCP para que Claude Code o Codex generen por ti.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title,
  description,
  openGraph: { title, description, type: "website", images: ["/og.jpg"] },
  twitter: { card: "summary_large_image", title, description, images: ["/og.jpg"] },
};

export const viewport: Viewport = { themeColor: "#0b0b0b" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" className={`${inter.variable} ${grotesk.variable}`}>
      <body style={{ fontOpticalSizing: "auto" }}>
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}

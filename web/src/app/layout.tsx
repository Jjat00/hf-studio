import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { I18nProvider } from "@/components/i18n-provider";
import { Nav } from "@/components/nav";
import { getDict, getLocale } from "@/lib/i18n/server";
import "./globals.css";

// Inter con eje óptico (opsz 14–32): en tamaños grandes se comporta como Inter Display.
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], axes: ["opsz"] });
const grotesk = Space_Grotesk({ variable: "--font-grotesk", subsets: ["latin"], weight: ["500", "700"] });

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return { title: "HF Studio", description: t.meta.description };
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  return (
    <html lang={locale} className={`${inter.variable} ${grotesk.variable} h-full`}>
      <body className="flex min-h-full flex-col" style={{ fontOpticalSizing: "auto" }}>
        <I18nProvider locale={locale}>
          <Nav />
          <main className="flex min-h-0 flex-1 flex-col">{children}</main>
        </I18nProvider>
      </body>
    </html>
  );
}

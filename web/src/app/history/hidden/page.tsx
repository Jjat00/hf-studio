import type { Metadata } from "next";
import { HistoryView } from "@/components/generations/history-view";

// Ocultas: ningún enlace lleva aquí; se entra escribiendo la dirección.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function HiddenHistoryPage() {
  return <HistoryView hidden />;
}

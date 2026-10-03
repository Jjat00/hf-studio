/** Marca propia de HF Studio: dos ondas (señal → video). No reutiliza el logotipo de Higgsfield. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="9" fill="#fff" />
      <path d="M7 13.5c2.2-3 4.4-3 6.6 0s4.4 3 6.6 0 3.3-2.2 4.8-1.5" fill="none" stroke="#131517" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M7 20.5c2.2-3 4.4-3 6.6 0s4.4 3 6.6 0 3.3-2.2 4.8-1.5" fill="none" stroke="#131517" strokeWidth="2.6" strokeLinecap="round" opacity=".45" />
    </svg>
  );
}

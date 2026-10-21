/** The Angan logo (a courtyard arch) and wordmark. */
export const APP_NAME = "Angan";

export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden="true" className="logo">
      <rect width="64" height="64" rx="16" fill="var(--accent)" />
      <path d="M18 50V30c0-8 6-14 14-14s14 6 14 14v20" fill="none" stroke="#fff6ec" strokeWidth="5" strokeLinecap="round" />
      <path d="M26 50V34a6 6 0 0 1 12 0v16" fill="none" stroke="#f3c98b" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

export default function Brand({ size = 32, showName = true }: { size?: number; showName?: boolean }) {
  return (
    <span className="brand">
      <Logo size={size} />
      {showName ? <span className="brand-name">{APP_NAME}</span> : <span className="sr-only">{APP_NAME}</span>}
    </span>
  );
}

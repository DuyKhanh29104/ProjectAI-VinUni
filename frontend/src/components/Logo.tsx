export function Logo({
  size = 24,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`project-logo ${className}`}
    >
      {/* Shield Outline */}
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      {/* Bounding box brackets representing labeled AI frames */}
      <path d="M9 8H8v1" strokeWidth="1.5" />
      <path d="M15 8h1v1" strokeWidth="1.5" />
      <path d="M9 16H8v-1" strokeWidth="1.5" />
      <path d="M15 16h1v-1" strokeWidth="1.5" />
      {/* Core point representing safety & assurance */}
      <circle cx="12" cy="12" r="1.5" fill="currentColor" />
    </svg>
  );
}

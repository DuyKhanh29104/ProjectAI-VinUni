import { Logo } from "./Logo";

export function LoginVisualPanel() {
  return (
    <aside
      className="login-visual"
      aria-label="Label Guardian perception quality workspace preview"
    >
      <div className="login-visual-overlay" />
      <svg
        className="login-wave"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path d="M0,0 H23 C7,18 28,34 18,53 C6,75 31,85 13,100 H0 Z" />
      </svg>
      <div className="login-visual-content">
        <span className="visual-status">
          <span /> Live quality intelligence
        </span>
        <div className="visual-copy">
          <Logo size={40} />
          <p>
            Protect every label.
            <br />
            Trust every frame.
          </p>
          <span>AI-assisted review for safer perception datasets.</span>
        </div>
        <div className="visual-metrics" aria-hidden="true">
          <div>
            <strong>98.4%</strong>
            <span>review confidence</span>
          </div>
          <div>
            <strong>24/7</strong>
            <span>quality monitoring</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

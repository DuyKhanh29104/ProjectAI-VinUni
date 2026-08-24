import { Eye, EyeOff, LockKeyhole, Mail, ShieldCheck, UserRound } from "lucide-react";
import { useState, type CSSProperties, type FormEvent } from "react";
import authBackground from "../data/background.png";

export function AuthenticatedLoginScreen({
  loading,
  configurationError,
  onSignIn,
  onRegister,
}: {
  loading: boolean;
  configurationError?: string;
  onSignIn: (email: string, password: string) => Promise<void>;
  onRegister: (name: string, email: string, password: string) => Promise<string>;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      if (mode === "login") {
        await onSignIn(email.trim(), password);
      } else {
        setMessage(await onRegister(name.trim(), email.trim(), password));
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Không thể xác thực người dùng.");
    }
  };

  return (
    <div
      className="mock-login-screen"
      style={{ "--auth-background-image": `url("${authBackground}")` } as CSSProperties}
    >
      <div className="mock-login-card">
        <section className="login-form-panel">
          <header className="mock-login-brand">
            <span className="login-brand-mark"><ShieldCheck size={21} /></span>
            <span className="login-brand-name">Label Guardian</span>
          </header>
          <div className={`login-form-content login-form-content-${mode}`} key={mode}>
            <span className="login-eyebrow">Secure perception QA</span>
            <h1>{mode === "login" ? "Welcome back" : "Create account"}<span>.</span></h1>
            <p className="login-intro">
              {mode === "login"
                ? "Đăng nhập bằng tài khoản Supabase Auth của workspace."
                : "Tài khoản mới mặc định là Annotator; Admin có thể thay đổi vai trò sau."}
            </p>
            <form className="login-form" onSubmit={submit}>
              {mode === "register" ? (
                <label className="login-field">
                  <span>Full name</span>
                  <span className="login-input-shell">
                    <UserRound size={17} />
                    <input value={name} onChange={(event) => setName(event.target.value)} required />
                  </span>
                </label>
              ) : null}
              <label className="login-field">
                <span>Email</span>
                <span className="login-input-shell">
                  <Mail size={17} />
                  <input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
                </span>
              </label>
              <label className="login-field">
                <span>Password</span>
                <span className="login-input-shell">
                  <LockKeyhole size={17} />
                  <input
                    type={showPassword ? "text" : "password"}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    minLength={8}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <button
                    className="login-password-toggle"
                    type="button"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    onClick={() => setShowPassword((visible) => !visible)}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </span>
              </label>
              {configurationError || error ? (
                <p className="login-form-error" role="alert">{configurationError || error}</p>
              ) : null}
              {message ? <p className="login-form-success">{message}</p> : null}
              <div className="login-actions">
                <button className="login-button login-button-primary" type="submit" disabled={loading}>
                  {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
                </button>
              </div>
            </form>
            <p className="login-switch-copy">
              {mode === "login" ? "Chưa có tài khoản?" : "Đã có tài khoản?"}{" "}
              <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); setMessage(""); }}>
                {mode === "login" ? "Đăng ký" : "Đăng nhập"}
              </button>
            </p>
            <p className="login-footnote">Identity by Supabase Auth · Roles enforced by Label Guardian API</p>
          </div>
        </section>
        <aside className="login-visual" aria-label="Label Guardian secure workspace">
          <div className="login-visual-overlay" />
          <div className="login-visual-content">
            <span>Role-based annotation QA</span>
            <h2>Protect datasets, decisions and revision history.</h2>
          </div>
        </aside>
      </div>
    </div>
  );
}

import {
  ArrowRight,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useState, type CSSProperties, type FormEvent } from "react";
import { roleLabels } from "../config/informationArchitecture";
import authBackground from "../data/background.png";
import type { Role, User } from "../domain/types";
import { LoginVisualPanel } from "./LoginVisualPanel";

const demoLoginRoles: Role[] = ["annotator", "reviewer", "admin"];

export function AuthenticatedLoginScreen({
  loading,
  configurationError,
  demoUsers,
  onSignIn,
  onDemoSignIn,
  onRegister,
}: {
  loading: boolean;
  configurationError?: string;
  demoUsers: User[];
  onSignIn: (email: string, password: string) => Promise<void>;
  onDemoSignIn: (role: Role) => Promise<void>;
  onRegister: (
    name: string,
    email: string,
    password: string,
  ) => Promise<string>;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [demoRoleLoading, setDemoRoleLoading] = useState<Role | null>(null);

  const quickSignIn = async (role: Role) => {
    setError("");
    setMessage("");
    setDemoRoleLoading(role);
    try {
      await onDemoSignIn(role);
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Unable to start the demo session.",
      );
    } finally {
      setDemoRoleLoading(null);
    }
  };

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
      setError(
        nextError instanceof Error
          ? nextError.message
          : "Không thể xác thực người dùng.",
      );
    }
  };

  return (
    <div
      className="mock-login-screen"
      style={
        {
          "--auth-background-image": `url("${authBackground}")`,
        } as CSSProperties
      }
    >
      <div className="mock-login-card">
        <section className="login-form-panel">
          <a
            className="mock-login-brand"
            href="/"
            aria-label="Back to Label Guardian landing page"
          >
            <span className="login-brand-mark">
              <ShieldCheck size={21} />
            </span>
            <span className="login-brand-name">Label Guardian</span>
          </a>
          <div
            className={`login-form-content login-form-content-${mode}`}
            key={mode}
          >
            <span className="login-eyebrow">Secure perception QA</span>
            <h1>
              {mode === "login" ? "Welcome back" : "Create account"}
              <span>.</span>
            </h1>
            <p className="login-intro">
              {mode === "login"
                ? "Đăng nhập bằng tài khoản Supabase Auth của workspace."
                : "Tài khoản mới mặc định là Annotator; Admin có thể thay đổi vai trò sau."}
            </p>
            {mode === "login" ? (
              <section
                className="demo-quick-login"
                aria-labelledby="supabase-demo-login-title"
              >
                <div className="demo-quick-login-heading">
                  <div>
                    <strong id="supabase-demo-login-title">
                      Quick demo access
                    </strong>
                    <span>Open a workspace instantly with any role.</span>
                  </div>
                  <small>No password required</small>
                </div>
                <div className="demo-quick-login-grid">
                  {demoLoginRoles.map((role) => {
                    const demoUser = demoUsers.find(
                      (user) => user.role === role,
                    );
                    return (
                      <button
                        className={`demo-quick-role-button is-${role}`}
                        type="button"
                        key={role}
                        aria-label={`Quick login as ${roleLabels[role]}`}
                        disabled={loading || demoRoleLoading !== null}
                        onClick={() => void quickSignIn(role)}
                      >
                        <span className="demo-role-avatar" aria-hidden="true">
                          {demoUser?.avatarInitials ??
                            role.slice(0, 2).toUpperCase()}
                        </span>
                        <span>
                          <strong>{roleLabels[role]}</strong>
                          <small>{demoUser?.name ?? "Demo user"}</small>
                        </span>
                        <ArrowRight size={14} aria-hidden="true" />
                      </button>
                    );
                  })}
                </div>
                <div className="demo-login-divider">
                  <span>or sign in with Supabase</span>
                </div>
              </section>
            ) : null}
            <form className="login-form" onSubmit={submit}>
              {mode === "register" ? (
                <label className="login-field">
                  <span>Full name</span>
                  <span className="login-input-shell">
                    <UserRound size={17} />
                    <input
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      required
                    />
                  </span>
                </label>
              ) : null}
              <label className="login-field">
                <span>Email</span>
                <span className="login-input-shell">
                  <Mail size={17} />
                  <input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </span>
              </label>
              <label className="login-field">
                <span>Password</span>
                <span className="login-input-shell">
                  <LockKeyhole size={17} />
                  <input
                    type={showPassword ? "text" : "password"}
                    autoComplete={
                      mode === "login" ? "current-password" : "new-password"
                    }
                    minLength={8}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <button
                    className="login-password-toggle"
                    type="button"
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                    onClick={() => setShowPassword((visible) => !visible)}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </span>
              </label>
              {configurationError || error ? (
                <p className="login-form-error" role="alert">
                  {configurationError || error}
                </p>
              ) : null}
              {message ? <p className="login-form-success">{message}</p> : null}
              <div className="login-actions">
                <button
                  className="login-button login-button-primary"
                  type="submit"
                  disabled={loading}
                >
                  {loading
                    ? "Please wait…"
                    : mode === "login"
                      ? "Sign in"
                      : "Create account"}
                </button>
              </div>
            </form>
            <p className="login-switch-copy">
              {mode === "login" ? "Chưa có tài khoản?" : "Đã có tài khoản?"}{" "}
              <button
                type="button"
                onClick={() => {
                  setMode(mode === "login" ? "register" : "login");
                  setError("");
                  setMessage("");
                }}
              >
                {mode === "login" ? "Đăng ký" : "Đăng nhập"}
              </button>
            </p>
            <p className="login-footnote">
              Identity by Supabase Auth · Roles enforced by Label Guardian API
            </p>
          </div>
        </section>
        <LoginVisualPanel />
      </div>
    </div>
  );
}

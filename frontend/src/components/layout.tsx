import {
  useState,
  type CSSProperties,
  type FormEvent,
  type PropsWithChildren,
} from "react";
import {
  ArrowRight,
  Activity,
  BarChart3,
  Bell,
  BookOpen,
  Check,
  Database,
  GitBranch,
  Home,
  LayoutDashboard,
  ListChecks,
  Settings,
  Tags,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  ShieldCheck,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { isApiDataSourceEnabled } from "../api/labelGuardianApi";
import type { AppRouteDefinition } from "../config/informationArchitecture";
import { roleLabels } from "../config/informationArchitecture";
import authBackground from "../data/background.png";
import type { Dataset, QaRun, Role, User } from "../domain/types";
import { Badge, Button } from "./ui";
import { Logo } from "./Logo";
import { LoginVisualPanel } from "./LoginVisualPanel";

const routeLabels: Record<PrimaryViewId, { en: string; vi: string }> = {
  overview: { en: "QA Overview", vi: "Tổng quan QA" },
  "qa-queue": { en: "QA Queue", vi: "Hàng đợi QA" },
  "qa-cases": { en: "QA Cases", vi: "Danh sách Case" },
  "dataset-run": { en: "Datasets & Runs", vi: "Dữ liệu & Tiến trình" },
  pipeline: { en: "QA Pipeline", vi: "Quy trình QA" },
  "annotator-workspace": { en: "2D Editor", vi: "Trình sửa 2D" },
  reports: { en: "Reports", vi: "Báo cáo" },
  settings: { en: "Settings", vi: "Cài đặt" },
  tutorial: { en: "Tutorial", vi: "Hướng dẫn" },
  "case-detail": { en: "Case Detail", vi: "Chi tiết Case" },
};

export type PrimaryViewId =
  | "overview"
  | "qa-queue"
  | "qa-cases"
  | "reports"
  | "dataset-run"
  | "pipeline"
  | "annotator-workspace"
  | "settings"
  | "tutorial"
  | "case-detail";

const routeIcons: Record<PrimaryViewId, LucideIcon> = {
  overview: LayoutDashboard,
  "qa-queue": ListChecks,
  "qa-cases": ShieldCheck,
  reports: BarChart3,
  "dataset-run": Database,
  pipeline: GitBranch,
  "annotator-workspace": Tags,
  settings: Settings,
  tutorial: BookOpen,
  "case-detail": ShieldCheck,
};

const routeOrder: Record<PrimaryViewId, number> = {
  overview: 0,
  "qa-queue": 1,
  "qa-cases": 2,
  "dataset-run": 3,
  pipeline: 4,
  "annotator-workspace": 5,
  reports: 6,
  settings: 7,
  tutorial: 8,
  "case-detail": 9,
};

interface AppShellProps extends PropsWithChildren {
  activeView: PrimaryViewId;
  activeRole: Role;
  activeUser: User;
  selectedDataset: Dataset;
  qaRun: QaRun;
  datasets: Dataset[];
  routes: AppRouteDefinition[];
  onNavigate: (view: PrimaryViewId) => void;
  onRoleChange: (role: Role) => void;
  allowRoleSwitch?: boolean;
  onDatasetChange: (datasetId: string) => void;
  onSignOut: () => void;
  onReset: () => void;
  lang: "en" | "vi";
  onChangeLang: (lang: "en" | "vi") => void;
}

export function AppShell({
  activeView,
  activeRole,
  activeUser,
  selectedDataset,
  qaRun,
  datasets,
  routes,
  onNavigate,
  onRoleChange,
  allowRoleSwitch = true,
  onDatasetChange,
  onSignOut,
  onReset,
  lang,
  onChangeLang,
  children,
}: AppShellProps) {
  const [accountOpen, setAccountOpen] = useState(false);
  const apiDataSourceEnabled = isApiDataSourceEnabled();
  const visibleRoutes = (
    routes.filter(
      (route) =>
        route.id !== "case-detail" &&
        route.id !== "pipeline" &&
        route.allowedRoles.includes(activeRole) &&
        route.id in routeIcons,
    ) as Array<AppRouteDefinition & { id: PrimaryViewId }>
  ).sort((first, second) => routeOrder[first.id] - routeOrder[second.id]);
  const activeRoute = routes.find((route) => route.id === activeView);

  const t = (en: string, vi: string) => (lang === "en" ? en : vi);

  return (
    <div className="app-shell app-shell-dark">
      <header className="topbar app-topbar">
        <div className="topbar-mobile-brand">
          <Logo size={20} />
          <div>
            <div className="brand-name">Label Guardian</div>
            <div className="brand-subtitle">Perception QA workspace</div>
          </div>
        </div>

        <div className="topbar-context">
          <span className="eyebrow">
            {t("AI Label Quality Assurance", "Đảm bảo chất lượng nhãn AI")}
          </span>
          <strong>
            {activeRoute
              ? (routeLabels[activeRoute.id as PrimaryViewId]?.[lang] ??
                activeRoute.label)
              : t("QA Overview", "Tổng quan QA")}
          </strong>
        </div>

        <div className="topbar-actions">
          <div className="topbar-lang-switcher">
            <button
              type="button"
              className={lang === "en" ? "is-active" : undefined}
              aria-pressed={lang === "en"}
              onClick={() => onChangeLang("en")}
            >
              EN
            </button>
            <span aria-hidden="true">|</span>
            <button
              type="button"
              className={lang === "vi" ? "is-active" : undefined}
              aria-pressed={lang === "vi"}
              onClick={() => onChangeLang("vi")}
            >
              VI
            </button>
          </div>

          <a
            className="workspace-home-link"
            href="/"
            aria-label="Back to Label Guardian landing page"
            title="Back to landing page"
          >
            <Home size={15} aria-hidden="true" />
            <span>{t("Landing", "Trang chủ")}</span>
          </a>

          {!apiDataSourceEnabled ? (
            <label className="dataset-switcher">
              <span className="sr-only">Dataset đang chọn</span>
              <Database size={15} aria-hidden="true" />
              <select
                value={selectedDataset.id}
                onChange={(event) => onDatasetChange(event.target.value)}
              >
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.format} · {dataset.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          {!apiDataSourceEnabled ? (
            <span className={`topbar-run-status run-${qaRun.status}`}>
              <Activity size={14} />
              <span>QA run</span>
              <strong>
                {qaRun.status === "running"
                  ? `${qaRun.progress}%`
                  : qaRun.status}
              </strong>
            </span>
          ) : null}

          {allowRoleSwitch ? (
            <label className="role-switcher">
              <span className="sr-only">Mock role</span>
              <select
                value={activeRole}
                onChange={(event) => onRoleChange(event.target.value as Role)}
              >
                {Object.entries(roleLabels).map(([role, label]) => (
                  <option key={role} value={role}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <span
              className="role-switcher authenticated-role"
              title="Role do quản trị viên cấp"
            >
              <ShieldCheck size={14} aria-hidden="true" />
              {roleLabels[activeRole]}
            </span>
          )}

          {!apiDataSourceEnabled ? (
            <button
              className="topbar-notification"
              type="button"
              aria-label="Notifications"
            >
              <Bell size={16} />
              <span>2</span>
            </button>
          ) : null}

          <div className="account-menu">
            <button
              className="user-chip account-trigger"
              type="button"
              aria-expanded={accountOpen}
              onClick={() => setAccountOpen((open) => !open)}
            >
              <span className="avatar">{activeUser.avatarInitials}</span>
              <span className="account-trigger-copy">
                <strong>{activeUser.name}</strong>
                <small>{roleLabels[activeRole]}</small>
              </span>
              <span className="account-chevron">⌄</span>
            </button>
            {accountOpen ? (
              <div className="account-popover">
                <div className="account-popover-header">
                  <strong>{activeUser.name}</strong>
                  <span>{activeUser.email}</span>
                </div>
                <Badge tone="info">
                  {allowRoleSwitch
                    ? t("Mock session", "Phiên demo")
                    : t("Authenticated session", "Phiên xác thực")}
                </Badge>
                {allowRoleSwitch ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setAccountOpen(false);
                      onReset();
                    }}
                  >
                    {t("Reset mock data", "Khôi phục dữ liệu demo")}
                  </Button>
                ) : null}
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => {
                    setAccountOpen(false);
                    onSignOut();
                  }}
                >
                  {t("Log out", "Đăng xuất")}
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className="workspace-layout">
        <aside className="sidebar">
          <div className="sidebar-brand">
            <Logo size={20} />
            <div className="sidebar-brand-copy">
              <div className="brand-name">Label Guardian</div>
              <div className="brand-subtitle">Human-in-the-loop QA</div>
            </div>
          </div>

          <nav className="sidebar-nav" aria-label="Điều hướng chính">
            {visibleRoutes.map((route) => {
              const RouteIcon = routeIcons[route.id];
              const displayLabel = routeLabels[route.id]?.[lang] ?? route.label;
              return (
                <button
                  className={`sidebar-nav-item ${activeView === route.id ? "is-active" : ""}`}
                  key={route.id}
                  type="button"
                  aria-label={displayLabel}
                  title={displayLabel}
                  aria-current={activeView === route.id ? "page" : undefined}
                  onClick={() => onNavigate(route.id)}
                >
                  <span className="sidebar-nav-icon" aria-hidden="true">
                    <RouteIcon size={16} strokeWidth={1.8} />
                  </span>
                  <span>{displayLabel}</span>
                  {route.id === "qa-cases" && !apiDataSourceEnabled ? (
                    <span className="nav-count">6</span>
                  ) : null}
                </button>
              );
            })}
          </nav>

          <div className="sidebar-spacer" />
        </aside>

        <main className="workspace-main">{children}</main>
      </div>

      <footer className="footer-bar app-footer">
        <span>
          Label Guardian ·{" "}
          {apiDataSourceEnabled
            ? t("API V1 production mode", "Chế độ production API V1")
            : t("Mock-only frontend", "Chế độ demo frontend")}
        </span>
        <span>
          {t("Role", "Vai trò")}: {roleLabels[activeRole]}
          {apiDataSourceEnabled
            ? t(" · Cloud dataset", " · Tập dữ liệu cloud")
            : ` · Dataset: ${selectedDataset.format}`}
        </span>
      </footer>
    </div>
  );
}

export function MockLoginScreen({
  users,
  onSignIn,
  onRegister,
}: {
  users: User[];
  onSignIn: (role: Role, email?: string) => void;
  onRegister: (profile: Pick<User, "name" | "email" | "role">) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [selectedRole, setSelectedRole] = useState<Role>("reviewer");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState(
    users.find((user) => user.role === "reviewer")?.email ?? "",
  );
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [formError, setFormError] = useState("");
  const selectedUser = users.find((user) => user.role === selectedRole);
  const availableRoles = Array.from(new Set(users.map((user) => user.role)));
  const demoLoginRoles: Role[] = ["annotator", "reviewer", "admin"];

  const quickSignIn = (role: Role) => {
    const demoUser = users.find((user) => user.role === role);
    onSignIn(role, demoUser?.email);
  };

  const selectRole = (role: Role) => {
    setSelectedRole(role);
    setFormError("");
    if (mode === "login") {
      setEmail(users.find((user) => user.role === role)?.email ?? "");
    }
  };

  const switchMode = (nextMode: "login" | "register") => {
    setMode(nextMode);
    setFormError("");
    setPassword("");
    setShowPassword(false);
    setEmail(
      nextMode === "login"
        ? (users.find((user) => user.role === selectedRole)?.email ?? "")
        : "",
    );
  };

  const changeMethod = () => {
    const roleIndex = availableRoles.indexOf(selectedRole);
    const nextRole = availableRoles[(roleIndex + 1) % availableRoles.length];
    if (nextRole) selectRole(nextRole);
  };

  const submitForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");

    if (mode === "login") {
      const normalizedEmail = email.trim().toLowerCase();
      const user = users.find(
        (candidate) => candidate.email.toLowerCase() === normalizedEmail,
      );
      if (!user || password.trim().length < 4) {
        setFormError(
          "Demo email was not found or the password has fewer than 4 characters.",
        );
        return;
      }
      onSignIn(user.role, user.email);
      return;
    }

    if (firstName.trim().length < 1 || lastName.trim().length < 1) {
      setFormError("Please enter your first and last name.");
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setFormError("Please enter a valid email address.");
      return;
    }
    if (password.length < 4) {
      setFormError(
        "Password must contain at least 4 characters for this demo.",
      );
      return;
    }
    onRegister({
      name: `${firstName.trim()} ${lastName.trim()}`,
      email: email.trim(),
      role: selectedRole,
    });
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
            <Logo size={24} />
            <span className="login-brand-name">Label Guardian</span>
          </a>

          <div
            className={`login-form-content login-form-content-${mode}`}
            key={mode}
          >
            <span className="login-eyebrow">Secure perception QA</span>
            <h1>
              {mode === "login" ? "Welcome back" : "Create new account"}
              <span>.</span>
            </h1>
            <p className="login-intro">
              {mode === "login"
                ? "Sign in to keep every annotation accurate, traceable, and ready for review."
                : "Start reviewing perception data with a workspace built for confident decisions."}
            </p>

            {mode === "login" ? (
              <section
                className="demo-quick-login"
                aria-labelledby="demo-quick-login-title"
              >
                <div className="demo-quick-login-heading">
                  <div>
                    <strong id="demo-quick-login-title">Quick demo access</strong>
                    <span>Open a workspace instantly with any role.</span>
                  </div>
                  <small>No password required</small>
                </div>
                <div className="demo-quick-login-grid">
                  {demoLoginRoles.map((role) => {
                    const demoUser = users.find((user) => user.role === role);
                    return (
                      <button
                        className={`demo-quick-role-button is-${role}`}
                        type="button"
                        key={role}
                        aria-label={`Quick login as ${roleLabels[role]}`}
                        onClick={() => quickSignIn(role)}
                      >
                        <span className="demo-role-avatar" aria-hidden="true">
                          {demoUser?.avatarInitials ?? role.slice(0, 2).toUpperCase()}
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
                  <span>or use demo credentials</span>
                </div>
              </section>
            ) : null}

            <form className="login-form" onSubmit={submitForm}>
              {mode === "register" ? (
                <div className="login-name-row">
                  <label className="login-field">
                    <span>First name</span>
                    <span className="login-input-shell">
                      <UserRound size={17} aria-hidden="true" />
                      <input
                        autoComplete="given-name"
                        value={firstName}
                        onChange={(event) => setFirstName(event.target.value)}
                        placeholder="Alex"
                      />
                    </span>
                  </label>
                  <label className="login-field">
                    <span>Last name</span>
                    <span className="login-input-shell login-input-shell-plain">
                      <input
                        autoComplete="family-name"
                        value={lastName}
                        onChange={(event) => setLastName(event.target.value)}
                        placeholder="Morgan"
                      />
                    </span>
                  </label>
                </div>
              ) : null}

              <label className="login-field">
                <span>Email address</span>
                <span className="login-input-shell">
                  <Mail size={17} aria-hidden="true" />
                  <input
                    autoComplete="email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@company.com"
                  />
                </span>
              </label>

              <label className="login-field">
                <span>Password</span>
                <span className="login-input-shell">
                  <LockKeyhole size={17} aria-hidden="true" />
                  <input
                    autoComplete={
                      mode === "login" ? "current-password" : "new-password"
                    }
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Enter your password"
                  />
                  <button
                    className="login-password-toggle"
                    type="button"
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword((visible) => !visible)}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </span>
              </label>

              {mode === "login" ? (
                <div className="login-options">
                  <label className="login-remember">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(event) => setRememberMe(event.target.checked)}
                    />
                    <span className="login-checkbox" aria-hidden="true">
                      {rememberMe ? <Check size={13} strokeWidth={3} /> : null}
                    </span>
                    Remember me
                  </label>
                  <button
                    className="login-text-button"
                    type="button"
                    onClick={() =>
                      setFormError("Password recovery is not connected yet.")
                    }
                  >
                    Forgot password?
                  </button>
                </div>
              ) : null}

              {formError ? (
                <p className="login-form-error" role="alert">
                  {formError}
                </p>
              ) : null}

              <div className="login-actions">
                <button
                  className="login-button login-button-secondary"
                  type="button"
                  onClick={changeMethod}
                >
                  <span>Change method</span>
                  <small>
                    {selectedUser
                      ? roleLabels[selectedUser.role]
                      : roleLabels[selectedRole]}
                  </small>
                </button>
                <button
                  className="login-button login-button-primary"
                  type="submit"
                >
                  {mode === "login" ? "Sign in" : "Create account"}
                  <ArrowRight size={18} aria-hidden="true" />
                </button>
              </div>
            </form>

            <p className="login-switch-copy">
              {mode === "login"
                ? "Don't have an account?"
                : "Already a member?"}{" "}
              <button
                type="button"
                onClick={() =>
                  switchMode(mode === "login" ? "register" : "login")
                }
              >
                {mode === "login" ? "Sign up" : "Log in"}
              </button>
            </p>
            <p className="login-footnote">
              Demo workspace · Authentication API is not connected
            </p>
          </div>
        </section>

        <LoginVisualPanel />
      </div>
    </div>
  );
}

import type { ButtonHTMLAttributes, HTMLAttributes, PropsWithChildren } from "react";
import type { ReviewStatus, Severity } from "../domain/types";

export function Card({
  children,
  className = "",
  ...props
}: PropsWithChildren<HTMLAttributes<HTMLDivElement>>) {
  return (
    <div className={`card ${className}`.trim()} {...props}>
      {children}
    </div>
  );
}

export function Button({
  children,
  variant = "secondary",
  size = "md",
  className = "",
  type = "button",
  ...props
}: PropsWithChildren<
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md";
  }
>) {
  return (
    <button
      type={type}
      className={`button button-${variant} button-${size} ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: PropsWithChildren<{ tone?: Severity | "neutral" | "info" | "success" }>) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

const statusLabels: Record<ReviewStatus, string> = {
  unreviewed: "Chưa review",
  in_review: "Đang review",
  confirmed: "Đã xác nhận",
  corrected: "Đã sửa",
  rejected: "Bác bỏ",
  skipped: "Bỏ qua",
};

export function StatusBadge({ status }: { status: ReviewStatus }) {
  const tone =
    status === "corrected" || status === "confirmed"
      ? "success"
      : status === "rejected"
        ? "neutral"
        : status === "skipped"
          ? "low"
          : status === "in_review"
            ? "info"
            : "high";

  return <Badge tone={tone}>{statusLabels[status]}</Badge>;
}

export function StatCard({
  label,
  value,
  detail,
  tone = "blue",
}: {
  label: string;
  value: string | number;
  detail: string;
  tone?: "blue" | "orange" | "green" | "purple";
}) {
  return (
    <div className={`stat-card stat-${tone}`}>
      <span className="eyebrow">{label}</span>
      <strong>{value}</strong>
      <span className="muted">{detail}</span>
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="section-heading">
      <span className="eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      {description ? <p className="muted">{description}</p> : null}
    </div>
  );
}

import type { PropsWithChildren } from "react";
import type { DemoMode } from "../domain/types";
import { Button, Card } from "./ui";

const modeCopy: Record<Exclude<DemoMode, "ready" | "success" | "rejected">, { title: string; description: string }> = {
  loading: {
    title: "Đang tải dữ liệu mock",
    description: "Màn hình đang mô phỏng trạng thái chờ dữ liệu từ repository.",
  },
  empty: {
    title: "Không có dữ liệu phù hợp",
    description: "Không có record nào trong trạng thái demo hiện tại. Bạn có thể thử lại hoặc reset mock data.",
  },
  error: {
    title: "Không thể tải dữ liệu mock",
    description: "Đây là lỗi giả lập cho QA flow; không phải lỗi backend thật.",
  },
};

export function DemoStateBoundary({
  mode,
  viewLabel,
  onReset,
  children,
}: PropsWithChildren<{
  mode: DemoMode;
  viewLabel: string;
  onReset: () => void;
}>) {
  if (mode === "loading" || mode === "empty" || mode === "error") {
    const copy = modeCopy[mode];
    return (
      <div className="page-container view-page demo-state-page" aria-busy={mode === "loading"}>
        <span className="eyebrow">FE-25 · {viewLabel}</span>
        <Card className={`demo-state-card demo-state-card-${mode}`} role={mode === "error" ? "alert" : "status"}>
          <div className="demo-state-icon" aria-hidden="true">{mode === "loading" ? "…" : mode === "empty" ? "∅" : "!"}</div>
          <h1>{copy.title}</h1>
          <p>{copy.description}</p>
          <div className="demo-state-actions">
            <Button variant="primary" onClick={onReset}>{mode === "error" ? "Thử lại" : "Hiển thị dữ liệu"}</Button>
            <Button variant="ghost" onClick={onReset}>Reset state demo</Button>
          </div>
        </Card>
      </div>
    );
  }

  if (mode === "success" || mode === "rejected") {
    const success = mode === "success";
    return (
      <div className="demo-state-shell">
        <div className={`demo-outcome-banner demo-outcome-${mode}`} role={success ? "status" : "alert"}>
          <span aria-hidden="true">{success ? "✓" : "!"}</span>
          <div><strong>{success ? "Thao tác thành công (demo)" : "Thao tác bị từ chối (demo)"}</strong><small>{success ? "State mock đã nhận thay đổi thành công." : "Permission/state guard đã chặn thay đổi; dữ liệu gốc vẫn an toàn."}</small></div>
          <button type="button" onClick={onReset}>Ẩn</button>
        </div>
        {children}
      </div>
    );
  }

  return <>{children}</>;
}

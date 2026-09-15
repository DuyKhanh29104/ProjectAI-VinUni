import { Badge, Button, Card, SectionHeading } from "../components/ui";
import { useAuth } from "../auth/AuthProvider";
import {
  useApplicationUsersQuery,
  useUpdateApplicationUserRoleMutation,
} from "../api/queries";
import type { Role } from "../domain/types";
import { useMockData } from "../state/MockDataProvider";

const categoryLabels: Record<string, string> = {
  geometry: "Geometry",
  temporal: "Temporal",
  context: "Context",
  model: "Model",
};

export function SettingsView() {
  const { state, actions } = useMockData();
  const auth = useAuth();
  const liveAuth = auth.enabled && !auth.isDemoSession;
  const activeRole = auth.user?.role ?? state.activeRole;
  const usersQuery = useApplicationUsersQuery(liveAuth && activeRole === "admin");
  const updateRole = useUpdateApplicationUserRoleMutation();

  if (activeRole !== "admin") {
    return (
      <div className="page-container view-page access-denied-page">
        <Badge tone="high">Admin only</Badge>
        <h1>Không có quyền truy cập</h1>
        <p className="page-description">Chỉ tài khoản có role Admin mới được xem và chỉnh cấu hình.</p>
      </div>
    );
  }

  return (
    <div className="page-container view-page settings-page">
      <div className="page-heading">
        <div><span className="eyebrow">Access & configuration</span><h1>Cấu hình QA</h1><p className="page-description">{liveAuth ? "Quản lý role người dùng cho API production." : "Bật/tắt rule và điều chỉnh threshold trong frontend state mock."}</p></div>
        <Badge tone="info">Admin workspace</Badge>
      </div>

      <Card className="privacy-safe-card settings-safe-card">
        <div className="privacy-safe-icon">i</div>
        <div>
          <strong>{liveAuth ? "RBAC đang hoạt động" : "Configuration sandbox"}</strong>
          <p>{liveAuth
            ? "Phân quyền người dùng được lưu qua API và PostgreSQL."
            : "Không có model, rule engine hoặc API thật được gọi từ màn hình này. Cấu hình được lưu trong localStorage mock."}</p>
        </div>
        <Badge tone="success">{liveAuth ? "Auth live" : "Demo session"}</Badge>
      </Card>

      {liveAuth ? (
        <Card>
          <div className="settings-card-heading">
            <SectionHeading
              eyebrow="Access control"
              title="Người dùng và phân quyền"
              description="Role được lưu trong PostgreSQL; thay đổi có hiệu lực ở request kế tiếp. Người dùng không thể tự đổi role."
            />
            <Badge tone="info">{usersQuery.data?.count ?? 0} users</Badge>
          </div>
          {usersQuery.isPending ? <p>Đang tải danh sách người dùng…</p> : null}
          {usersQuery.isError ? <p className="login-form-error">{usersQuery.error.message}</p> : null}
          <div className="config-list">
            {usersQuery.data?.results.map((user) => (
              <div className="config-row" key={user.id}>
                <div className="config-row-heading">
                  <div>
                    <strong>{user.displayName}</strong>
                    <small>{user.email}{user.id === auth.user?.id ? " · tài khoản hiện tại" : ""}</small>
                  </div>
                  <label className="toggle-control">
                    <span>Role</span>
                    <select
                      aria-label={`Role của ${user.email}`}
                      value={user.role}
                      disabled={updateRole.isPending || user.id === auth.user?.id}
                      onChange={(event) => updateRole.mutate({
                        userId: user.id,
                        role: event.target.value as Role,
                      })}
                    >
                      <option value="annotator">Annotator</option>
                      <option value="reviewer">QA Reviewer</option>
                      <option value="admin">Admin</option>
                    </select>
                  </label>
                </div>
              </div>
            ))}
          </div>
          {updateRole.isError ? <p className="login-form-error">{updateRole.error.message}</p> : null}
        </Card>
      ) : null}

      {!liveAuth ? <div className="settings-grid">
        <Card>
          <div className="settings-card-heading"><SectionHeading eyebrow="Rule registry" title="QA rules" description="Threshold sẽ được chụp vào QA run khi bạn bấm Start." /><Badge tone="info">{state.rules.filter((rule) => rule.enabled).length}/{state.rules.length} enabled</Badge></div>
          <div className="config-list">{state.rules.map((rule) => <div className="config-row" key={rule.id}>
            <div className="config-row-heading"><div><strong>{rule.name}</strong><small>{categoryLabels[rule.category]} · {rule.id}</small></div><label className="toggle-control"><input type="checkbox" checked={rule.enabled} onChange={(event) => actions.updateRule(rule.id, { enabled: event.target.checked })} /><span>{rule.enabled ? "Enabled" : "Disabled"}</span></label></div>
            <p>{rule.description}</p>
            <div className="threshold-control"><label><span>{rule.unit}</span><input type="range" min={rule.min} max={rule.max} step={rule.step} value={rule.threshold} onChange={(event) => actions.updateRule(rule.id, { threshold: Number(event.target.value) })} /></label><input className="threshold-number" type="number" min={rule.min} max={rule.max} step={rule.step} value={rule.threshold} onChange={(event) => actions.updateRule(rule.id, { threshold: Math.min(rule.max, Math.max(rule.min, Number(event.target.value))) })} /></div>
          </div>)}</div>
        </Card>

        <Card>
          <div className="settings-card-heading"><SectionHeading eyebrow="Model registry" title="Reference models" description="Confidence threshold chỉ dùng cho dữ liệu mock." /><Badge tone="neutral">{state.models.length} models</Badge></div>
          <div className="config-list">{state.models.map((model) => <div className="model-config-row" key={model.id}><div className="config-row-heading"><div><strong>{model.name}</strong><small>{model.version} · {model.task}</small></div><label className="toggle-control"><input type="checkbox" checked={model.enabled} onChange={(event) => actions.updateModel(model.id, { enabled: event.target.checked })} /><span>{model.enabled ? "Enabled" : "Disabled"}</span></label></div><div className="threshold-control"><label><span>Confidence threshold</span><input type="range" min="0.1" max="0.99" step="0.05" value={model.confidenceThreshold} onChange={(event) => actions.updateModel(model.id, { confidenceThreshold: Number(event.target.value) })} /></label><strong className="threshold-value">{Math.round(model.confidenceThreshold * 100)}%</strong></div></div>)}</div>
          <Button variant="ghost" size="sm" disabled>Save to backend · FE-25+</Button>
        </Card>
      </div> : null}
    </div>
  );
}

import {
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  Clock3,
  Command,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { PrimaryViewId } from "../components/layout";
import { roleLabels } from "../config/informationArchitecture";
import {
  tutorialByRole,
  tutorialText,
  type TutorialLanguage,
} from "../config/tutorialContent";
import type { Role } from "../domain/types";

const shortcuts = [
  { keys: "V", en: "Select a box", vi: "Chọn bounding box" },
  { keys: "M", en: "Move a box", vi: "Di chuyển bounding box" },
  { keys: "B", en: "Create a box", vi: "Tạo bounding box" },
  { keys: "Z", en: "Zoom tool", vi: "Công cụ zoom" },
  { keys: "H", en: "Pan the canvas", vi: "Di chuyển canvas" },
  { keys: "Ctrl/⌘ + S", en: "Save revision", vi: "Lưu revision" },
  { keys: "Ctrl/⌘ + Z", en: "Undo", vi: "Hoàn tác" },
];

export function TutorialView({
  role,
  language,
  completedStepIds,
  completedAt,
  onToggleStep,
  onComplete,
  onReset,
  onNavigate,
}: {
  role: Role;
  language: TutorialLanguage;
  completedStepIds: string[];
  completedAt?: string;
  onToggleStep: (stepId: string) => void;
  onComplete: () => void;
  onReset: () => void;
  onNavigate: (view: PrimaryViewId) => void;
}) {
  const tutorial = tutorialByRole[role];
  const completed = new Set(completedStepIds);
  const completedCount = tutorial.steps.filter((step) =>
    completed.has(step.id),
  ).length;
  const completionPercent = Math.round(
    (completedCount / tutorial.steps.length) * 100,
  );
  const totalMinutes = tutorial.steps.reduce(
    (total, step) => total + step.durationMinutes,
    0,
  );
  const allDone = completedCount === tutorial.steps.length;
  const t = (en: string, vi: string) => (language === "en" ? en : vi);

  return (
    <div className="tutorial-page">
      <section className="tutorial-hero">
        <div className="tutorial-hero-copy">
          <span className="tutorial-kicker">
            <Sparkles size={14} />
            {t("Role-based onboarding", "Hướng dẫn theo vai trò")}
          </span>
          <h1>{tutorialText(tutorial.title, language)}</h1>
          <p>{tutorialText(tutorial.summary, language)}</p>
          <div className="tutorial-hero-meta">
            <span>
              <ShieldCheck size={16} /> {roleLabels[role]}
            </span>
            <span>
              <Clock3 size={16} /> {totalMinutes} {t("minutes", "phút")}
            </span>
            <span>
              <BookOpen size={16} /> {tutorial.steps.length} {t("steps", "bước")}
            </span>
          </div>
        </div>
        <div className="tutorial-progress-card">
          <div className="tutorial-progress-ring" style={{ "--progress": `${completionPercent}%` } as React.CSSProperties}>
            <strong>{completionPercent}%</strong>
            <span>{t("complete", "hoàn thành")}</span>
          </div>
          <div>
            <strong>
              {completedCount}/{tutorial.steps.length} {t("steps complete", "bước hoàn thành")}
            </strong>
            <p>{tutorialText(tutorial.outcome, language)}</p>
          </div>
        </div>
      </section>

      <div className="tutorial-layout">
        <section className="tutorial-main" aria-labelledby="tutorial-checklist-title">
          <div className="tutorial-section-heading">
            <div>
              <span>{t("Getting started", "Bắt đầu")}</span>
              <h2 id="tutorial-checklist-title">
                {t("Your guided checklist", "Checklist hướng dẫn của bạn")}
              </h2>
            </div>
            <button
              type="button"
              className="tutorial-reset-button"
              onClick={onReset}
            >
              <RefreshCcw size={14} />
              {t("Reset progress", "Làm lại từ đầu")}
            </button>
          </div>

          <div className="tutorial-step-list">
            {tutorial.steps.map((step, index) => {
              const isComplete = completed.has(step.id);
              return (
                <article
                  className={`tutorial-step-card ${isComplete ? "is-complete" : ""}`}
                  key={step.id}
                >
                  <button
                    type="button"
                    className="tutorial-step-check"
                    aria-label={
                      isComplete
                        ? t("Mark step incomplete", "Đánh dấu chưa hoàn thành")
                        : t("Mark step complete", "Đánh dấu hoàn thành")
                    }
                    aria-pressed={isComplete}
                    onClick={() => onToggleStep(step.id)}
                  >
                    {isComplete ? <Check size={16} /> : index + 1}
                  </button>
                  <div className="tutorial-step-content">
                    <div className="tutorial-step-title-row">
                      <h3>{tutorialText(step.title, language)}</h3>
                      <span>
                        <Clock3 size={13} /> {step.durationMinutes} {t("min", "phút")}
                      </span>
                    </div>
                    <p>{tutorialText(step.description, language)}</p>
                    <div className="tutorial-step-actions">
                      <button
                        type="button"
                        className="tutorial-action-link"
                        onClick={() => onNavigate(step.destination)}
                      >
                        {tutorialText(step.actionLabel, language)}
                        <ArrowRight size={14} />
                      </button>
                      <button
                        type="button"
                        className="tutorial-mark-link"
                        onClick={() => onToggleStep(step.id)}
                      >
                        {isComplete
                          ? t("Completed", "Đã hoàn thành")
                          : t("Mark as done", "Đánh dấu hoàn thành")}
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>

          <div className={`tutorial-completion ${allDone ? "is-ready" : ""}`}>
            <CheckCircle2 size={24} />
            <div>
              <strong>
                {allDone
                  ? t("Tutorial checklist complete", "Đã hoàn thành checklist")
                  : t("Complete every step to finish", "Hoàn thành tất cả các bước")}
              </strong>
              <p>
                {completedAt
                  ? t("Your progress is saved for this account and role.", "Tiến độ đã được lưu cho tài khoản và role này.")
                  : t("You can leave and continue later; progress is saved in this browser.", "Bạn có thể rời đi và tiếp tục sau; tiến độ được lưu trên trình duyệt này.")}
              </p>
            </div>
            <button
              type="button"
              className="button button-primary button-md"
              disabled={!allDone || Boolean(completedAt)}
              onClick={onComplete}
            >
              {completedAt
                ? t("Tutorial completed", "Đã hoàn thành hướng dẫn")
                : t("Finish tutorial", "Kết thúc hướng dẫn")}
            </button>
          </div>
        </section>

        <aside className="tutorial-aside">
          <section className="tutorial-tip-card">
            <span className="tutorial-tip-icon"><Command size={18} /></span>
            <div>
              <span className="tutorial-kicker">2D Editor</span>
              <h2>{t("Keyboard shortcuts", "Phím tắt")}</h2>
            </div>
            <div className="tutorial-shortcut-list">
              {shortcuts.map((shortcut) => (
                <div key={shortcut.keys}>
                  <kbd>{shortcut.keys}</kbd>
                  <span>{language === "en" ? shortcut.en : shortcut.vi}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="tutorial-tip-card tutorial-concepts-card">
            <span className="tutorial-kicker">
              {t("Core concepts", "Khái niệm chính")}
            </span>
            <dl>
              <div>
                <dt>QA Case</dt>
                <dd>{t("A potential label defect that needs a human decision.", "Một lỗi nhãn tiềm ẩn cần con người quyết định.")}</dd>
              </div>
              <div>
                <dt>Evidence</dt>
                <dd>{t("Signals, predictions and explanations supporting a finding.", "Tín hiệu, prediction và giải thích hỗ trợ finding.")}</dd>
              </div>
              <div>
                <dt>Revision</dt>
                <dd>{t("A saved annotation version that preserves edit history.", "Một phiên bản annotation được lưu và giữ lịch sử chỉnh sửa.")}</dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}

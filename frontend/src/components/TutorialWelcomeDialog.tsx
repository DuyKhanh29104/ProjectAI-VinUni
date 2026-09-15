import { ArrowRight, BookOpen, CheckCircle2, Clock3, X } from "lucide-react";
import { roleLabels } from "../config/informationArchitecture";
import {
  tutorialByRole,
  tutorialText,
  type TutorialLanguage,
} from "../config/tutorialContent";
import type { Role } from "../domain/types";

export function TutorialWelcomeDialog({
  role,
  language,
  onStart,
  onSkip,
}: {
  role: Role;
  language: TutorialLanguage;
  onStart: () => void;
  onSkip: () => void;
}) {
  const tutorial = tutorialByRole[role];
  const totalMinutes = tutorial.steps.reduce(
    (total, step) => total + step.durationMinutes,
    0,
  );
  const t = (en: string, vi: string) => (language === "en" ? en : vi);

  return (
    <div className="tutorial-dialog-backdrop" role="presentation">
      <section
        className="tutorial-welcome-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tutorial-welcome-title"
      >
        <button
          type="button"
          className="tutorial-dialog-close"
          aria-label={t("Skip tutorial", "Bỏ qua hướng dẫn")}
          onClick={onSkip}
        >
          <X size={18} />
        </button>

        <div className="tutorial-welcome-icon" aria-hidden="true">
          <BookOpen size={28} />
        </div>
        <span className="tutorial-kicker">
          {t("Welcome to Label Guardian", "Chào mừng đến Label Guardian")}
        </span>
        <h1 id="tutorial-welcome-title">
          {t("Your first review starts here", "Bắt đầu công việc đầu tiên")}
        </h1>
        <p className="tutorial-welcome-summary">
          {tutorialText(tutorial.summary, language)}
        </p>

        <div className="tutorial-welcome-meta">
          <span>
            <CheckCircle2 size={16} />
            {roleLabels[role]}
          </span>
          <span>
            <Clock3 size={16} />
            {t(`About ${totalMinutes} minutes`, `Khoảng ${totalMinutes} phút`)}
          </span>
          <span>
            <BookOpen size={16} />
            {tutorial.steps.length} {t("guided steps", "bước hướng dẫn")}
          </span>
        </div>

        <div className="tutorial-welcome-outcome">
          <strong>{t("What you will learn", "Bạn sẽ học được gì")}</strong>
          <p>{tutorialText(tutorial.outcome, language)}</p>
        </div>

        <div className="tutorial-dialog-actions">
          <button
            type="button"
            className="button button-ghost button-md"
            onClick={onSkip}
          >
            {t("Explore on my own", "Tự khám phá")}
          </button>
          <button
            type="button"
            className="button button-primary button-md"
            onClick={onStart}
          >
            {t("Start tutorial", "Bắt đầu hướng dẫn")}
            <ArrowRight size={16} />
          </button>
        </div>
      </section>
    </div>
  );
}

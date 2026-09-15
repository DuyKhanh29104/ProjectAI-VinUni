import {
  ArrowRight,
  Bot,
  Check,
  ChevronDown,
  Cloud,
  Code2,
  Database,
  FileCheck2,
  GitBranch,
  GitCommitHorizontal,
  GitCompareArrows,
  History,
  LayoutGrid,
  Layers3,
  MousePointer2,
  Network,
  PencilRuler,
  Radar,
  ScanSearch,
  ShieldCheck,
  type LucideIcon,
  UserCheck,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Logo } from "../components/Logo";

interface LandingSection {
  id: string;
  label: string;
  shortLabel: string;
  icon: LucideIcon;
}

function LandingNavigation({
  lang,
  onChangeLang,
}: {
  lang: "en" | "vi";
  onChangeLang: (lang: "en" | "vi") => void;
}) {
  const landingSections: LandingSection[] = [
    {
      id: "overview",
      label: lang === "en" ? "Overview" : "Tổng quan",
      shortLabel: lang === "en" ? "Start" : "Bắt đầu",
      icon: LayoutGrid,
    },
    {
      id: "signals",
      label: lang === "en" ? "Risk signals" : "Tín hiệu rủi ro",
      shortLabel: lang === "en" ? "Signals" : "Tín hiệu",
      icon: Radar,
    },
    {
      id: "pipeline",
      label: lang === "en" ? "QA pipeline" : "Quy trình QA",
      shortLabel: lang === "en" ? "Pipeline" : "Quy trình",
      icon: GitBranch,
    },
    {
      id: "review",
      label: lang === "en" ? "Review workflow" : "Luồng đánh giá",
      shortLabel: lang === "en" ? "Review" : "Đánh giá",
      icon: UserCheck,
    },
    {
      id: "architecture",
      label: lang === "en" ? "Architecture" : "Kiến trúc",
      shortLabel: lang === "en" ? "System" : "Hệ thống",
      icon: Network,
    },
  ];

  const [activeSection, setActiveSection] = useState(landingSections[0].id);
  const activeIndex = Math.max(
    0,
    landingSections.findIndex((section) => section.id === activeSection),
  );
  const active = landingSections[activeIndex];
  const next = landingSections[(activeIndex + 1) % landingSections.length];
  const condensed = activeIndex > 0;

  const t = (en: string, vi: string) => (lang === "en" ? en : vi);

  useEffect(() => {
    const targets = landingSections
      .map((section) => document.getElementById(section.id))
      .filter((target): target is HTMLElement => Boolean(target));

    if (targets.length === 0 || typeof IntersectionObserver === "undefined") {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visibleEntry = entries
          .filter((entry) => entry.isIntersecting)
          .sort(
            (first, second) =>
              second.intersectionRatio - first.intersectionRatio,
          )[0];

        if (visibleEntry) {
          setActiveSection(visibleEntry.target.id);
        }
      },
      {
        rootMargin: "-18% 0px -66% 0px",
        threshold: [0, 0.15, 0.35, 0.6],
      },
    );

    targets.forEach((target) => observer.observe(target));
    const requestedSection = window.location.hash.slice(1);
    const hashTarget = targets.find((target) => target.id === requestedSection);
    let restoreScrollTimer = 0;
    const hashTimer = window.setTimeout(() => {
      if (hashTarget) {
        const root = document.documentElement;
        const previousScrollBehavior = root.style.scrollBehavior;
        root.style.scrollBehavior = "auto";
        const targetTop =
          hashTarget.getBoundingClientRect().top + window.scrollY - 68;
        const maximumTop = Math.max(0, root.scrollHeight - window.innerHeight);
        window.scrollTo(0, Math.min(Math.max(0, targetTop), maximumTop));
        setActiveSection(hashTarget.id);
        restoreScrollTimer = window.setTimeout(() => {
          root.style.scrollBehavior = previousScrollBehavior;
        }, 0);
      }
    }, 120);

    return () => {
      window.clearTimeout(hashTimer);
      window.clearTimeout(restoreScrollTimer);
      observer.disconnect();
    };
  }, [lang]);

  return (
    <>
      <header
        className={`landing-header${condensed ? " is-condensed" : ""}`}
        data-section-index={activeIndex}
      >
        <a className="landing-skip-link" href="#overview">
          Skip to content
        </a>
        <nav className="landing-nav" aria-label="Landing navigation">
          <a className="landing-brand" href="#overview">
            <Logo size={22} />
            <span>Label Guardian</span>
          </a>

          <div className="landing-nav-center">
            <span className="landing-nav-current">{active.label}</span>
            <div className="landing-nav-links">
              {landingSections.slice(1).map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  aria-current={
                    activeSection === section.id ? "location" : undefined
                  }
                >
                  {section.shortLabel}
                </a>
              ))}
            </div>
          </div>

          <div className="landing-nav-actions">
            <div className="landing-lang-switcher" aria-label="Chọn ngôn ngữ">
              <button
                type="button"
                className={`landing-lang-btn ${lang === "en" ? "active" : ""}`}
                onClick={() => onChangeLang("en")}
              >
                EN
              </button>
              <span>/</span>
              <button
                type="button"
                className={`landing-lang-btn ${lang === "vi" ? "active" : ""}`}
                onClick={() => onChangeLang("vi")}
              >
                VI
              </button>
            </div>
            <a
              className="landing-nav-next"
              href={`#${next.id}`}
              aria-label={`Go to ${next.label}`}
              title={`Next: ${next.label}`}
            >
              <ChevronDown size={17} aria-hidden="true" />
            </a>
            <a className="landing-nav-action" href="/overview">
              {t("Open workspace", "Mở không gian")}
              <ArrowRight size={16} aria-hidden="true" />
            </a>
          </div>
        </nav>
        <span className="landing-nav-progress" aria-hidden="true" />
      </header>

      <aside
        className={`landing-section-dock${condensed ? " is-visible" : ""}`}
        aria-label="Jump to landing section"
        aria-hidden={!condensed}
      >
        <span className="landing-dock-current">{active.label}</span>
        <nav>
          {landingSections.map((section) => {
            const Icon = section.icon;
            const current = activeSection === section.id;
            return (
              <a
                key={section.id}
                href={`#${section.id}`}
                aria-label={`Go to ${section.label}`}
                aria-current={current ? "location" : undefined}
                title={section.label}
                tabIndex={condensed ? 0 : -1}
              >
                <Icon size={16} aria-hidden="true" />
                <span>{section.shortLabel}</span>
              </a>
            );
          })}
        </nav>
      </aside>
    </>
  );
}

export function LandingPage({
  lang,
  onChangeLang,
}: {
  lang: "en" | "vi";
  onChangeLang: (lang: "en" | "vi") => void;
}) {
  const t = (en: string, vi: string) => (lang === "en" ? en : vi);

  const issueTypes =
    lang === "en"
      ? ["Wrong class", "Loose bbox", "Missing label", "Duplicate label"]
      : ["Sai lớp đối tượng", "Lệch hộp bao", "Thiếu nhãn", "Lặp nhãn"];

  const workflowSteps = [
    {
      icon: ScanSearch,
      label: t("Triage", "Phân loại"),
      meta: t("Risk ranked", "Sắp xếp rủi ro"),
    },
    {
      icon: GitCompareArrows,
      label: t("Compare", "So sánh"),
      meta: t("Label vs model", "Nhãn vs mô hình"),
    },
    {
      icon: PencilRuler,
      label: t("Correct", "Sửa đổi"),
      meta: t("Edit geometry", "Sửa tọa độ"),
    },
    {
      icon: GitCommitHorizontal,
      label: t("Commit", "Xác nhận"),
      meta: t("New revision", "Phiên bản mới"),
    },
  ];

  return (
    <main className="landing-page">
      <LandingNavigation lang={lang} onChangeLang={onChangeLang} />

      <section className="landing-hero" id="overview">
        <div className="landing-hero-copy">
          <p className="landing-kicker">
            {t("Perception Data QA", "Đảm bảo chất lượng nhãn AI")}
          </p>
          <h1>
            {t(
              "Catch label errors before training.",
              "Phát hiện lỗi nhãn trước khi training.",
            )}
          </h1>
          <p>
            {t(
              "Evidence-led review for autonomous-driving datasets.",
              "Đánh giá dựa trên bằng chứng cho dữ liệu xe tự lái.",
            )}
          </p>
          <div className="landing-hero-actions">
            <a className="landing-primary-action" href="/overview">
              {t("Open workspace", "Mở không gian làm việc")}
              <ArrowRight size={18} aria-hidden="true" />
            </a>
            <a className="landing-secondary-action" href="#pipeline">
              {t("See pipeline", "Xem quy trình")}
            </a>
          </div>
        </div>
        <figure className="landing-hero-visual">
          <img
            src="/label-guardian-hero.png"
            alt="Perception dataset review workstation with bounding boxes and risk evidence"
          />
        </figure>
      </section>

      <section className="landing-proof" aria-label="Product principles">
        <article className="landing-proof-item">
          <div className="proof-human" aria-hidden="true">
            <span>
              <Bot size={17} />
            </span>
            <i />
            <span className="is-active">
              <UserCheck size={17} />
            </span>
            <i />
            <span>
              <Check size={17} />
            </span>
          </div>
          <div>
            <strong>{t("Human decides", "Con người phê duyệt")}</strong>
            <small>
              {t(
                "Every flagged case ends with a reviewer.",
                "Mọi trường hợp bị gắn cờ đều do đánh giá viên quyết định.",
              )}
            </small>
          </div>
        </article>
        <article className="landing-proof-item">
          <div className="proof-rules" aria-hidden="true">
            <Code2 size={18} />
            <span>IoU &lt; 0.50</span>
            <ArrowRight size={14} />
            <b>HIGH</b>
          </div>
          <div>
            <strong>{t("Rules set severity", "Quy tắc định mức độ")}</strong>
            <small>
              {t(
                "Models explain evidence. Code controls outcomes.",
                "Mô hình gợi ý bằng chứng. Mã nguồn kiểm soát kết quả.",
              )}
            </small>
          </div>
        </article>
        <article className="landing-proof-item">
          <div className="proof-cloud" aria-hidden="true">
            <Cloud size={18} />
            <span className="proof-packet" />
            <Database size={18} />
          </div>
          <div>
            <strong>{t("Cloud-native data", "Dữ liệu cloud gốc")}</strong>
            <small>
              {t(
                "Frames and metadata stay in their source systems.",
                "Hình ảnh và siêu dữ liệu lưu trữ tại nguồn của bạn.",
              )}
            </small>
          </div>
        </article>
      </section>

      <section className="landing-problem" id="signals">
        <div className="landing-section-copy">
          <h2>
            {t(
              "See the failure, not another list.",
              "Nhìn thấy trực quan lỗi, không chỉ là danh sách.",
            )}
          </h2>
          <p>
            {t(
              "Label Guardian turns scattered annotation defects into spatial evidence reviewers can inspect.",
              "Label Guardian chuyển đổi các khuyết tật nhãn rải rác thành bằng chứng không gian dễ dàng kiểm tra.",
            )}
          </p>
          <div
            className="landing-issue-legend"
            aria-label="Detected issue types"
          >
            {issueTypes.map((issue, index) => (
              <span key={issue}>
                <i>{index + 1}</i>
                {issue}
              </span>
            ))}
          </div>
        </div>
        <figure className="landing-inspection-frame">
          <img
            src="/label-guardian-hero.png"
            alt="Road frames with annotation issues highlighted for inspection"
          />
          <span className="issue-box issue-box-one">
            <i>1</i>
          </span>
          <span className="issue-box issue-box-two">
            <i>2</i>
          </span>
          <span className="issue-box issue-box-three">
            <i>3</i>
          </span>
          <span className="issue-box issue-box-four">
            <i>4</i>
          </span>
          <figcaption>
            <span>scene_000142</span>
            <strong>{t("4 signals found", "Tìm thấy 4 lỗi")}</strong>
          </figcaption>
        </figure>
      </section>

      <section className="landing-pipeline" id="pipeline">
        <div className="landing-section-copy landing-section-copy-compact">
          <h2>
            {t(
              "A QA pipeline you can follow.",
              "Quy trình QA trực quan tin cậy.",
            )}
          </h2>
          <p>
            {t(
              "Each case moves from raw annotation to review-ready evidence through deterministic stages.",
              "Mỗi trường hợp di chuyển từ nhãn thô đến bằng chứng đánh giá qua các giai đoạn xác định.",
            )}
          </p>
        </div>
        <div
          className="landing-pipeline-canvas"
          aria-label="Annotation QA pipeline"
        >
          <article className="pipeline-source">
            <div className="pipeline-frame-stack" aria-hidden="true">
              <img src="/label-guardian-hero.png" alt="" />
              <span />
              <span />
            </div>
            <div>
              <small>{t("Input", "Đầu vào")}</small>
              <strong>{t("Annotation", "Nhãn thô")}</strong>
            </div>
          </article>
          <div className="pipeline-link" aria-hidden="true">
            <span />
          </div>
          <article className="pipeline-engine">
            <span className="pipeline-engine-icon">
              <Bot size={22} />
            </span>
            <div className="pipeline-engine-rings" aria-hidden="true">
              <i />
              <i />
              <i />
            </div>
            <div>
              <small>{t("Evidence engine", "Bộ máy bằng chứng")}</small>
              <strong>{t("Match + score", "Khớp nhãn + tính điểm")}</strong>
            </div>
          </article>
          <div className="pipeline-link" aria-hidden="true">
            <span />
          </div>
          <article className="pipeline-output">
            <div className="pipeline-case-list" aria-hidden="true">
              <span>
                <i /> Wrong class <b>H</b>
              </span>
              <span>
                <i /> Loose bbox <b>M</b>
              </span>
              <span>
                <i /> Missing label <b>H</b>
              </span>
            </div>
            <div>
              <small>{t("Output", "Đầu ra")}</small>
              <strong>{t("Ranked QA cases", "Hàng đợi QA phân loại")}</strong>
            </div>
          </article>
        </div>
      </section>

      <section className="landing-review" id="review">
        <div className="landing-review-heading">
          <h2>
            {t(
              "One fluid path from signal to revision.",
              "Một lộ trình mượt mà từ tín hiệu đến sửa đổi.",
            )}
          </h2>
          <a className="landing-text-link" href="/qa-queue">
            {t("Open QA Queue", "Mở danh sách hàng đợi QA")}
            <ArrowRight size={16} aria-hidden="true" />
          </a>
        </div>
        <div className="landing-workflow">
          <ol className="workflow-steps">
            {workflowSteps.map((step, index) => {
              const Icon = step.icon;
              return (
                <li
                  key={step.label}
                  className={index === 1 ? "is-current" : ""}
                >
                  <span>
                    <Icon size={19} aria-hidden="true" />
                  </span>
                  <div>
                    <strong>{step.label}</strong>
                    <small>{step.meta}</small>
                  </div>
                </li>
              );
            })}
          </ol>
          <div className="workflow-stage">
            <figure>
              <img
                src="/label-guardian-hero.png"
                alt="Frame under human review with model and annotation overlays"
              />
              <span className="workflow-bbox workflow-bbox-label" />
              <span className="workflow-bbox workflow-bbox-model" />
            </figure>
            <div className="workflow-decision">
              <div>
                <GitCompareArrows size={18} aria-hidden="true" />
                <span>
                  <small>{t("Evidence", "Bằng chứng")}</small>
                  <strong>{t("Class mismatch", "Sai lớp đối tượng")}</strong>
                </span>
              </div>
              <div className="workflow-actions" aria-label="Review decisions">
                <span>
                  <Check size={15} />
                  {t("Accept", "Đồng ý")}
                </span>
                <span className="is-selected">
                  <PencilRuler size={15} />
                  {t("Edit", "Sửa đổi")}
                </span>
                <span>
                  <History size={15} />
                  {t("Restore", "Phục hồi")}
                </span>
              </div>
              <div className="workflow-revision">
                <GitCommitHorizontal size={17} />
                <span>revision_03</span>
                <b>{t("saved", "đã lưu")}</b>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-architecture" id="architecture">
        <div className="landing-section-copy landing-section-copy-compact">
          <h2>
            {t(
              "Data moves. Ownership stays clear.",
              "Dữ liệu di chuyển. Quyền sở hữu giữ nguyên.",
            )}
          </h2>
          <p>
            {t(
              "A live path from private storage to reviewer decision, with every correction returning as a traceable revision.",
              "Một luồng trực tiếp từ lưu trữ nội bộ đến quyết định đánh giá, lưu lịch sử sửa đổi rõ ràng.",
            )}
          </p>
        </div>
        <div
          className="architecture-flow"
          aria-label="System architecture data flow"
        >
          <div className="architecture-source architecture-gcs">
            <Cloud size={23} aria-hidden="true" />
            <span>
              <small>{t("Objects", "Lưu trữ")}</small>
              <strong>GCS frames</strong>
            </span>
          </div>
          <div className="architecture-source architecture-db">
            <Database size={23} aria-hidden="true" />
            <span>
              <small>{t("State", "Cơ sở dữ liệu")}</small>
              <strong>Supabase</strong>
            </span>
          </div>
          <div
            className="architecture-beam architecture-beam-a"
            aria-hidden="true"
          >
            <i />
          </div>
          <div
            className="architecture-beam architecture-beam-b"
            aria-hidden="true"
          >
            <i />
          </div>
          <div className="architecture-core">
            <span className="architecture-core-icon">
              <ShieldCheck size={26} />
            </span>
            <small>{t("Private API boundary", "Phân vùng API bảo mật")}</small>
            <strong>FastAPI + QA agent</strong>
            <div>
              <Code2 size={14} /> deterministic rules
            </div>
          </div>
          <div
            className="architecture-beam architecture-beam-c"
            aria-hidden="true"
          >
            <i />
          </div>
          <div className="architecture-reviewer">
            <Layers3 size={23} aria-hidden="true" />
            <span>
              <small>{t("Workspace", "Không gian làm việc")}</small>
              <strong>React reviewer</strong>
            </span>
          </div>
          <div className="architecture-return" aria-hidden="true">
            <span />
          </div>
          <div className="architecture-audit">
            <FileCheck2 size={19} aria-hidden="true" />
            <span>
              <strong>
                {t("Revision + audit event", "Lịch sử sửa đổi và kiểm toán")}
              </strong>
              <small>actor, note, status, timestamp</small>
            </span>
          </div>
        </div>
      </section>

      <section className="landing-guardrails" aria-label="Product guardrails">
        <span>
          <ShieldCheck size={18} />
          {t("Human approval", "Con người phê duyệt")}
        </span>
        <span>
          <Code2 size={18} />
          {t("Deterministic severity", "Mức độ xác định")}
        </span>
        <span>
          <History size={18} />
          {t("Immutable revisions", "Phiên bản bất biến")}
        </span>
        <span>
          <Database size={18} />
          {t("Traceable provenance", "Nguồn gốc rõ ràng")}
        </span>
      </section>

      <section className="landing-final">
        <div>
          <MousePointer2 size={24} aria-hidden="true" />
          <h2>
            {t(
              "Review the frames that matter first.",
              "Đánh giá các frame quan trọng trước.",
            )}
          </h2>
        </div>
        <a className="landing-primary-action" href="/overview">
          {t("Enter workspace", "Vào không gian làm việc")}
          <ArrowRight size={18} aria-hidden="true" />
        </a>
      </section>
    </main>
  );
}

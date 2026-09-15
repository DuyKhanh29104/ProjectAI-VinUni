import type { PrimaryViewId } from "../components/layout";
import type { Role } from "../domain/types";

export type TutorialLanguage = "en" | "vi";

interface LocalizedText {
  en: string;
  vi: string;
}

export interface TutorialStep {
  id: string;
  title: LocalizedText;
  description: LocalizedText;
  actionLabel: LocalizedText;
  destination: PrimaryViewId;
  durationMinutes: number;
}

export interface RoleTutorial {
  title: LocalizedText;
  summary: LocalizedText;
  outcome: LocalizedText;
  steps: TutorialStep[];
}

export const TUTORIAL_VERSION = 1;

export const tutorialByRole: Record<Role, RoleTutorial> = {
  annotator: {
    title: {
      en: "Correct an annotation with confidence",
      vi: "Chỉnh sửa annotation một cách tự tin",
    },
    summary: {
      en: "Learn how to move from an Agent finding to a traceable annotation revision.",
      vi: "Tìm hiểu cách đi từ finding của Agent đến một annotation revision có thể truy vết.",
    },
    outcome: {
      en: "You will be able to inspect an assigned case, edit its boxes and save a revision.",
      vi: "Bạn sẽ có thể kiểm tra case được giao, chỉnh bounding box và lưu revision.",
    },
    steps: [
      {
        id: "annotator-open-cases",
        title: { en: "Open your QA cases", vi: "Mở danh sách QA Case" },
        description: {
          en: "Find cases assigned to you and use status or risk filters to focus the queue.",
          vi: "Tìm case được giao và dùng bộ lọc trạng thái hoặc risk để tập trung công việc.",
        },
        actionLabel: { en: "Open QA Cases", vi: "Mở QA Cases" },
        destination: "qa-cases",
        durationMinutes: 1,
      },
      {
        id: "annotator-read-evidence",
        title: { en: "Read Agent evidence", vi: "Đọc evidence của Agent" },
        description: {
          en: "Review the issue type, confidence and visual comparison before changing a label.",
          vi: "Xem loại lỗi, confidence và so sánh trực quan trước khi thay đổi nhãn.",
        },
        actionLabel: { en: "Inspect cases", vi: "Kiểm tra case" },
        destination: "qa-cases",
        durationMinutes: 2,
      },
      {
        id: "annotator-edit-labels",
        title: { en: "Use the 2D Editor", vi: "Sử dụng 2D Editor" },
        description: {
          en: "Select, move, resize, create or delete boxes. Ctrl/Cmd+Z undoes the latest edit.",
          vi: "Chọn, di chuyển, đổi kích thước, tạo hoặc xóa box. Ctrl/Cmd+Z để hoàn tác.",
        },
        actionLabel: { en: "Open 2D Editor", vi: "Mở 2D Editor" },
        destination: "annotator-workspace",
        durationMinutes: 3,
      },
      {
        id: "annotator-save-revision",
        title: { en: "Save a revision", vi: "Lưu annotation revision" },
        description: {
          en: "Add a concise change note, validate every box and save without overwriting history.",
          vi: "Thêm ghi chú ngắn, kiểm tra các box và lưu mà không ghi đè lịch sử.",
        },
        actionLabel: { en: "Practice in Editor", vi: "Thực hành trong Editor" },
        destination: "annotator-workspace",
        durationMinutes: 2,
      },
    ],
  },
  reviewer: {
    title: {
      en: "Review high-risk findings efficiently",
      vi: "Review finding rủi ro cao hiệu quả",
    },
    summary: {
      en: "Learn the review loop from dataset selection to a documented QA decision.",
      vi: "Tìm hiểu vòng review từ chọn dữ liệu đến quyết định QA có lưu vết.",
    },
    outcome: {
      en: "You will be able to prioritize cases, validate evidence and record a decision.",
      vi: "Bạn sẽ có thể ưu tiên case, xác minh evidence và ghi nhận quyết định.",
    },
    steps: [
      {
        id: "reviewer-open-queue",
        title: { en: "Start in QA Queue", vi: "Bắt đầu tại QA Queue" },
        description: {
          en: "Choose a dataset frame and run or inspect Agent QA results.",
          vi: "Chọn frame trong dataset và chạy hoặc kiểm tra kết quả Agent QA.",
        },
        actionLabel: { en: "Open QA Queue", vi: "Mở QA Queue" },
        destination: "qa-queue",
        durationMinutes: 1,
      },
      {
        id: "reviewer-prioritize",
        title: { en: "Prioritize by risk", vi: "Ưu tiên theo risk" },
        description: {
          en: "Filter unresolved cases and start with high-risk findings that may block release.",
          vi: "Lọc case chưa xử lý và bắt đầu với finding rủi ro cao có thể chặn release.",
        },
        actionLabel: { en: "Browse QA Cases", vi: "Xem QA Cases" },
        destination: "qa-cases",
        durationMinutes: 2,
      },
      {
        id: "reviewer-validate",
        title: { en: "Validate the evidence", vi: "Xác minh evidence" },
        description: {
          en: "Compare the source annotation, prediction and Agent explanation before deciding.",
          vi: "So sánh annotation gốc, prediction và giải thích của Agent trước khi quyết định.",
        },
        actionLabel: { en: "Inspect evidence", vi: "Kiểm tra evidence" },
        destination: "qa-cases",
        durationMinutes: 3,
      },
      {
        id: "reviewer-report",
        title: { en: "Track the QA outcome", vi: "Theo dõi kết quả QA" },
        description: {
          en: "Use reports to monitor confirmed issues, corrections and review effectiveness.",
          vi: "Dùng báo cáo để theo dõi lỗi xác nhận, correction và hiệu quả review.",
        },
        actionLabel: { en: "Open Reports", vi: "Mở Báo cáo" },
        destination: "reports",
        durationMinutes: 1,
      },
    ],
  },
  admin: {
    title: {
      en: "Operate the Label Guardian workspace",
      vi: "Vận hành workspace Label Guardian",
    },
    summary: {
      en: "Learn how datasets, pipeline health, roles and QA reporting fit together.",
      vi: "Tìm hiểu cách dataset, pipeline, phân quyền và báo cáo QA kết nối với nhau.",
    },
    outcome: {
      en: "You will be able to verify a release, monitor ingestion and manage workspace access.",
      vi: "Bạn sẽ có thể kiểm tra release, theo dõi ingestion và quản lý quyền truy cập.",
    },
    steps: [
      {
        id: "admin-datasets",
        title: { en: "Verify datasets and runs", vi: "Kiểm tra Dataset và Run" },
        description: {
          en: "Confirm the active dataset release, frame scope and latest QA run status.",
          vi: "Xác nhận dataset release, phạm vi frame và trạng thái QA run gần nhất.",
        },
        actionLabel: { en: "Open Datasets / Runs", vi: "Mở Datasets / Runs" },
        destination: "dataset-run",
        durationMinutes: 2,
      },
      {
        id: "admin-pipeline",
        title: { en: "Monitor ingestion", vi: "Theo dõi ingestion" },
        description: {
          en: "Inspect pipeline stages and logs when cloud metadata or assets are unavailable.",
          vi: "Kiểm tra stage và log của pipeline khi metadata hoặc asset cloud không sẵn sàng.",
        },
        actionLabel: { en: "Open Pipeline", vi: "Mở Pipeline" },
        destination: "pipeline",
        durationMinutes: 2,
      },
      {
        id: "admin-access",
        title: { en: "Manage access and roles", vi: "Quản lý tài khoản và role" },
        description: {
          en: "Review authenticated users and grant only the role required for their workflow.",
          vi: "Kiểm tra người dùng xác thực và chỉ cấp role cần thiết cho công việc.",
        },
        actionLabel: { en: "Open Settings", vi: "Mở Cài đặt" },
        destination: "settings",
        durationMinutes: 2,
      },
      {
        id: "admin-reports",
        title: { en: "Review QA performance", vi: "Đánh giá hiệu quả QA" },
        description: {
          en: "Use reports to understand error trends and whether the review process is improving quality.",
          vi: "Dùng báo cáo để hiểu xu hướng lỗi và mức cải thiện chất lượng của quy trình review.",
        },
        actionLabel: { en: "Open Reports", vi: "Mở Báo cáo" },
        destination: "reports",
        durationMinutes: 1,
      },
    ],
  },
};

export function tutorialText(
  text: LocalizedText,
  language: TutorialLanguage,
): string {
  return text[language];
}

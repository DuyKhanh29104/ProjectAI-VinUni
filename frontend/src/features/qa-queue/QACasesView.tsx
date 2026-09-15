import { isApiDataSourceEnabled } from "../../api/labelGuardianApi";
import { ApiQAQueueView } from "./ApiQAQueueView";
import { MockCaseRegistryView } from "./MockCaseRegistryView";
import "../../styles/case-registry-v2.css";

export function QACasesView({
  onOpenFinding,
  onOpenEditor,
}: {
  onOpenFinding?: (findingId: string) => void;
  onOpenEditor?: (split?: string, imageId?: string) => void;
}) {
  return isApiDataSourceEnabled() ? (
    <ApiQAQueueView
      onOpenEditor={(split, imageId) => onOpenEditor?.(split, imageId)}
    />
  ) : (
    <MockCaseRegistryView
      onOpenFinding={onOpenFinding}
      onOpenEditor={onOpenEditor}
    />
  );
}

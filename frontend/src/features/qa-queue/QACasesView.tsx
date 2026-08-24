import { isApiDataSourceEnabled } from "../../api/labelGuardianApi";
import { ApiQAQueueView } from "./ApiQAQueueView";
import { MockQAQueueView } from "./MockQAQueueView";

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
    <MockQAQueueView
      onOpenFinding={onOpenFinding}
      onOpenEditor={onOpenEditor}
    />
  );
}

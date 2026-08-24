import { isApiDataSourceEnabled } from "../../api/labelGuardianApi";
import { MockQAQueueView } from "./MockQAQueueView";
import { RealDataQAView } from "../../views/RealDataQAView";

export function QAQueueView({
  onOpenFinding,
  onOpenEditor,
}: {
  onOpenFinding?: (findingId: string) => void;
  onOpenEditor?: (split?: string, imageId?: string) => void;
}) {
  return isApiDataSourceEnabled()
    ? <div className="page-container"><RealDataQAView /></div>
    : <MockQAQueueView onOpenFinding={onOpenFinding} onOpenEditor={onOpenEditor} />;
}

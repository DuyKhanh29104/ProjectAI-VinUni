import type { CSSProperties } from "react";

import { Card } from "../../components/ui";
import { chartColors, donutBackground } from "./queuePresentation";

interface DistributionItem {
  count: number;
  label: string;
  type?: string;
}

export function QueueAnalytics({
  errorDistribution,
  classDistribution,
  totalCount,
  reviewedCount,
  reviewProgress,
}: {
  errorDistribution: DistributionItem[];
  classDistribution: DistributionItem[];
  totalCount: number;
  reviewedCount: number;
  reviewProgress: number;
}) {
  const maxClassCount = Math.max(...classDistribution.map((item) => item.count), 1);

  return (
    <>
      <Card className="queue-analytics-card">
        <strong>Phân bố lỗi theo loại</strong>
        <div className="queue-donut-wrap">
          <div className="queue-donut" style={{ background: donutBackground(errorDistribution) }}>
            <span><b>{totalCount}</b><small>Tổng</small></span>
          </div>
        </div>
        <div className="queue-chart-legend">
          {errorDistribution.map((item, index) => (
            <div key={item.type ?? item.label}>
              <i style={{ background: chartColors[index % chartColors.length] }} />
              <span>{item.label}</span>
              <strong>{Math.round((item.count / Math.max(totalCount, 1)) * 100)}%</strong>
            </div>
          ))}
        </div>
      </Card>

      <Card className="queue-analytics-card">
        <strong>Theo class</strong>
        <div className="queue-class-bars">
          {classDistribution.map((item) => (
            <div key={item.label}>
              <span>{item.label}</span>
              <div><i style={{ width: `${(item.count / maxClassCount) * 100}%` }} /></div>
              <strong>{item.count}</strong>
            </div>
          ))}
        </div>
      </Card>

      <Card className="queue-analytics-card queue-progress-card">
        <strong>Tiến độ review</strong>
        <div
          className="queue-progress-ring"
          style={{ background: `conic-gradient(#22a06b 0 ${reviewProgress}%, #f3c46f ${reviewProgress}% 100%)` } as CSSProperties}
        >
          <span><b>{reviewProgress}%</b><small>Đã hoàn thành</small></span>
        </div>
        <div className="queue-progress-legend">
          <span><i className="is-reviewed" />Đã review <strong>{reviewedCount}</strong></span>
          <span><i className="is-waiting" />Chờ review <strong>{totalCount - reviewedCount}</strong></span>
        </div>
      </Card>
    </>
  );
}

import { Badge, Card } from "./ui";

export function ApiDemoNotice({
  loading,
  hasData,
  hasError,
  description,
}: {
  loading: boolean;
  hasData: boolean;
  hasError: boolean;
  description: string;
}) {
  if (loading || hasData) return null;

  return (
    <Card className="privacy-safe-card" role="status">
      <div className="privacy-safe-icon">i</div>
      <div>
        <strong>Chế độ trình diễn</strong>
        <p>{description}</p>
      </div>
      <Badge tone={hasError ? "high" : "info"}>
        {hasError ? "API chưa sẵn sàng" : "Chưa có dữ liệu"}
      </Badge>
    </Card>
  );
}

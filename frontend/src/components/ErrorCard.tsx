import { AlertTriangle } from "lucide-react";
import { Card } from "./ui/Card";

export function ErrorCard({ message }: { message: string }) {
  return (
    <Card title="Error" icon={<AlertTriangle className="h-3.5 w-3.5" />} tone="error">
      <p className="text-[13px] leading-relaxed text-fail">{message}</p>
    </Card>
  );
}

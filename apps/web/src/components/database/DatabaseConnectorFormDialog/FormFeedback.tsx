import type { DatabaseConnectorTestResult } from "@/types/databaseConnectors";

interface FormFeedbackProps {
  error: string | null;
  testResult: DatabaseConnectorTestResult | null;
}

export function FormFeedback({ error, testResult }: FormFeedbackProps) {
  return (
    <>
      {error ? (
        <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-sm text-foreground">
          {error}
        </div>
      ) : null}

      {testResult ? (
        <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-sm text-foreground">
          <div className="font-medium">
            {testResult.success ? "连接测试通过" : "连接测试失败"}
          </div>
          <div className="mt-1 text-muted-foreground">
            {testResult.message}
            {typeof testResult.latency_ms === "number"
              ? ` · ${testResult.latency_ms} ms`
              : ""}
          </div>
        </div>
      ) : null}
    </>
  );
}

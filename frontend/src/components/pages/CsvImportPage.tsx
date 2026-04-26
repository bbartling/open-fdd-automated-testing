import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { UploadCloud } from "lucide-react";

import { ApiError } from "@/lib/api";
import { getDriverProfileStatus, triggerRunFdd, uploadCsvFile } from "@/lib/crud-api";

type CsvUiResult = {
  ok?: boolean;
  validated?: boolean;
  preview?: {
    rows_total?: number;
    rows_with_valid_timestamp?: number;
    timestamp_column?: string | null;
    metric_columns?: string[];
    warnings?: string[];
  };
  ingest?: {
    rows_inserted?: number;
    points_upserted?: number;
  };
  fdd_trigger?: {
    status?: string;
    path?: string;
  } | null;
  note?: string;
  errors?: string[];
  warnings?: string[];
  timestamp_column?: string | null;
  [key: string]: unknown;
};

export function CsvImportPage() {
  const { data: profile } = useQuery({
    queryKey: ["driver-profile"],
    queryFn: getDriverProfileStatus,
  });

  const [siteId, setSiteId] = useState("csv-upload");
  const [createPoints, setCreatePoints] = useState(true);
  const [runFddAfterIngest, setRunFddAfterIngest] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CsvUiResult | null>(null);
  const [errorText, setErrorText] = useState("");

  const csvEnabled = profile?.drivers?.csv ?? false;
  const statusText = useMemo(() => {
    if (!profile) return "Checking driver profile...";
    return csvEnabled
      ? "CSV scraper is enabled in bootstrap profile."
      : "CSV scraper is disabled in bootstrap profile. Upload API still works when API is running.";
  }, [profile, csvEnabled]);

  const onDropFile = (f: File | null) => {
    setFile(f);
    setResult(null);
    setErrorText("");
  };

  const onSubmit = async () => {
    if (!file) return;
    setBusy(true);
    setResult(null);
    setErrorText("");
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("site_id", siteId);
      body.append("create_points", String(createPoints));
      const trimmedSource = file.name.replace(/\.csv$/i, "").trim();
      body.append("source_name", trimmedSource || file.name || "uploaded");
      const resp = await uploadCsvFile(body);
      let fddTrigger: { status: string; path: string } | null = null;
      if (runFddAfterIngest) {
        fddTrigger = await triggerRunFdd();
      }
      setResult({
        ...resp,
        fdd_trigger: fddTrigger,
        note:
          runFddAfterIngest && fddTrigger
            ? "FDD trigger created. If fdd_backfill_enabled=true, loop will run configured backfill windows before routine lookback."
            : undefined,
      });
    } catch (e) {
      if (e instanceof ApiError && e.payload && typeof e.payload === "object") {
        const payload = e.payload as { error?: { message?: string; details?: unknown } };
        setErrorText(payload.error?.message ?? e.message);
        setResult((payload.error?.details as CsvUiResult) ?? (e.payload as CsvUiResult));
      } else {
        setErrorText(e instanceof Error ? e.message : "Upload failed");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">CSV Import</h1>
      <p className="text-sm text-muted-foreground">
        Upload CSV with drag-and-drop. Backend validates timestamp and metric columns and returns structured errors when data is malformed.
      </p>

      <div className="rounded-xl border border-border/60 bg-card p-4">
        <p className="text-sm font-medium text-foreground">Driver profile status</p>
        <p className="mt-1 text-sm text-muted-foreground">{statusText}</p>
      </div>

      <div className="rounded-xl border border-border/60 bg-card p-4 space-y-4">
        <div>
          <label htmlFor="csv-site-id" className="mb-1 block text-xs font-medium text-muted-foreground">Site ID</label>
          <input
            id="csv-site-id"
            value={siteId}
            onChange={(e) => setSiteId(e.target.value)}
            className="h-9 w-full rounded-lg border border-border/60 bg-background px-3 text-sm"
            placeholder="csv-upload"
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={createPoints}
            onChange={(e) => setCreatePoints(e.target.checked)}
          />
          Auto-create missing points
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={runFddAfterIngest}
            onChange={(e) => setRunFddAfterIngest(e.target.checked)}
          />
          Run FDD now after successful ingest
        </label>

        <div
          className="rounded-xl border-2 border-dashed border-border p-8 text-center"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            onDropFile(e.dataTransfer.files?.[0] ?? null);
          }}
        >
          <UploadCloud className="mx-auto h-8 w-8 text-muted-foreground" />
          <p className="mt-2 text-sm text-muted-foreground">Drag and drop a CSV file here</p>
          <p className="mt-1 text-xs text-muted-foreground">or</p>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => onDropFile(e.target.files?.[0] ?? null)}
            className="mt-2 text-sm"
          />
          {file ? <p className="mt-2 text-sm font-medium">{file.name}</p> : null}
        </div>

        <button
          type="button"
          disabled={!file || busy || !siteId.trim()}
          onClick={onSubmit}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          {busy ? "Uploading..." : "Validate + Import CSV"}
        </button>
      </div>

      {errorText ? (
        <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {errorText}
        </div>
      ) : null}

      {result ? (
        <div className="space-y-3 rounded-xl border border-border/60 bg-muted/40 p-4 text-sm">
          <p className="font-medium text-foreground">CSV result</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <span className="text-muted-foreground">Validated:</span>{" "}
              <span className="font-medium">{String(result.validated ?? false)}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Rows total:</span>{" "}
              <span className="font-medium">{result.preview?.rows_total ?? "—"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Rows with valid timestamp:</span>{" "}
              <span className="font-medium">{result.preview?.rows_with_valid_timestamp ?? "—"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Timestamp column:</span>{" "}
              <span className="font-medium">{result.preview?.timestamp_column ?? result.timestamp_column ?? "—"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Metric columns:</span>{" "}
              <span className="font-medium">{result.preview?.metric_columns?.length ?? 0}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Rows inserted:</span>{" "}
              <span className="font-medium">{result.ingest?.rows_inserted ?? 0}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Points upserted:</span>{" "}
              <span className="font-medium">{result.ingest?.points_upserted ?? 0}</span>
            </div>
            <div>
              <span className="text-muted-foreground">FDD trigger:</span>{" "}
              <span className="font-medium">{result.fdd_trigger?.status ?? "not triggered"}</span>
            </div>
          </div>

          {(result.preview?.warnings?.length || result.warnings?.length) && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
              <p className="mb-1 font-medium text-amber-700 dark:text-amber-300">Warnings</p>
              <ul className="list-disc space-y-1 pl-4">
                {(result.preview?.warnings ?? result.warnings ?? []).map((w, i) => (
                  <li key={`${w}-${i}`}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {result.errors?.length ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
              <p className="mb-1 font-medium">Validation errors</p>
              <ul className="list-disc space-y-1 pl-4">
                {result.errors.map((err, i) => (
                  <li key={`${err}-${i}`}>{err}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {result.note ? (
            <p className="rounded-lg border border-border/60 bg-card px-3 py-2 text-xs text-muted-foreground">{result.note}</p>
          ) : null}

          <details>
            <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">Raw JSON</summary>
            <pre className="mt-2 max-h-[240px] overflow-auto rounded-lg border border-border/60 bg-card p-3 text-xs">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      ) : null}
    </div>
  );
}

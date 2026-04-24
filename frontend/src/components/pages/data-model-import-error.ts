export type ValidationErrorItem = {
  loc?: unknown;
  msg?: unknown;
  type?: unknown;
};

export function formatValidationPath(loc: unknown): string {
  if (!Array.isArray(loc)) return "body";
  const parts: string[] = [];
  for (const segment of loc) {
    if (segment === "body") continue;
    if (typeof segment === "number") {
      if (parts.length > 0) {
        parts[parts.length - 1] = `${parts[parts.length - 1]}[${segment}]`;
      } else {
        parts.push(`[${segment}]`);
      }
      continue;
    }
    if (typeof segment === "string") {
      parts.push(segment);
    }
  }
  return parts.length > 0 ? parts.join(".") : "body";
}

export function firstImportValidationFailure(payload: unknown): { path: string; message: string } | null {
  if (payload == null || typeof payload !== "object") return null;
  const root = payload as Record<string, unknown>;
  const error = root.error;
  if (error == null || typeof error !== "object") return null;
  const details = (error as Record<string, unknown>).details;
  if (details == null || typeof details !== "object") return null;
  const errors = (details as Record<string, unknown>).errors;
  if (!Array.isArray(errors) || errors.length === 0) return null;
  const first = errors[0] as ValidationErrorItem;
  return {
    path: formatValidationPath(first?.loc),
    message:
      typeof first?.msg === "string" && first.msg.trim()
        ? first.msg.trim()
        : typeof first?.type === "string" && first.type.trim()
          ? first.type.trim()
          : "Validation error",
  };
}

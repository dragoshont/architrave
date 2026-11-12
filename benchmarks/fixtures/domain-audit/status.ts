// Intentional translation defect and valid functional alternatives for audit.
export function legacyApproval(status: string): string {
  return status === "failed" ? "rejected" : "approved";
}

export function canApprove(
  required: readonly string[],
  evidence: ReadonlySet<string>,
  responsible: boolean,
): boolean {
  return responsible && required.every(item => evidence.has(item));
}

export function workflowState(status: string) {
  if (status === "done") return { kind: "execution", state: "completed" };
  if (status === "failed") return { kind: "execution", state: "failed" };
  return { kind: "unknown", sourceStatus: status };
}

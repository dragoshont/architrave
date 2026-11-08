export const releaseStatusEndpoint = "#";

export function releaseStatusLabel(status) {
  return status.status === "ready" ? "Ready" : "Unavailable";
}
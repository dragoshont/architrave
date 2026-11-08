# Release Status Contract

Endpoint: `/api/v1/release-status`

```json
{
  "releaseId": "fixture-2026.08.13",
  "status": "blocked_external",
  "reason": "provider_auth_required",
  "provider": "fixture-mail",
  "updatedAt": "2026-08-13T00:00:00Z"
}
```

The backend reads this state from `runtime/release-state.json` after every
process start. Web, Electron, and iOS show the same status and reason. Provider
authentication is not faked: it pauses as `AUTH_REQUIRED` for principal
`fixture-user` at provider `fixture-mail`, then resumes from synthetic evidence
`evidence:fixture-auth-resolved`.

The sandbox deployment release id and digest must match `deploy/release.json`.
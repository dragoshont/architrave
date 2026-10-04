#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/run"

cat >"$tmp/bin/fake-agent" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
name="$(basename "$0")"
prompt="${*: -1}"
nonce_file="$(printf '%s\n' "$prompt" | sed -n 's/.*Read \([^ ]*\) and include EVIDENCE_NONCE.*/\1/p' | tail -1)"
nonce=""
[ -n "$nonce_file" ] && [ -f "$nonce_file" ] && nonce="$(cat "$nonce_file")"
verdict=PASS
[ "${FAKE_AGENT_FAIL:-}" = "$name" ] && verdict=FAIL
content="EVIDENCE_NONCE: $nonce
VERDICT: $verdict"
if printf '%s\0' "$@" | grep -zq -- '--output-format'; then
  if [ "$name" = claude ]; then
    printf '{"result":%s}\n' "$(python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<<"$content")"
  else
    printf '{"type":"assistant.message","data":{"content":%s}}\n' "$(python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<<"$content")"
  fi
else
  printf '%s\nTOURNAMENT: COMPLETE\n' "EVIDENCE_NONCE: $nonce"
fi
SH
chmod +x "$tmp/bin/fake-agent"
ln -s fake-agent "$tmp/bin/copilot"
ln -s fake-agent "$tmp/bin/claude"
export PATH="$tmp/bin:$PATH"

suggested="$(harness/semantic-review.sh --provider both --run "$tmp/run")"
if printf '%s' "$suggested" | grep -Eq -- '--model|--effort|--reasoning-effort'; then
  echo "FAIL semantic launcher specifies a model control" >&2
  exit 1
fi
echo "ok    semantic launcher inherits host model"

harness/semantic-review.sh --provider both --run "$tmp/run" --execute >/dev/null
echo "ok    semantic launcher verifies both independent providers"

export FAKE_AGENT_FAIL=claude
if harness/semantic-review.sh --provider both --run "$tmp/run" --execute >/dev/null 2>&1; then
  echo "FAIL semantic launcher accepted a failing reviewer" >&2
  exit 1
fi
unset FAKE_AGENT_FAIL
echo "ok    semantic launcher fails closed"

tournament="$(harness/tournament-review.sh --run "$tmp/run")"
if printf '%s' "$tournament" | grep -Eq -- '--model|--effort|--reasoning-effort'; then
  echo "FAIL tournament launcher specifies a model control" >&2
  exit 1
fi
echo "ok    tournament launcher inherits host model"

harness/tournament-review.sh --run "$tmp/run" --execute >/dev/null
echo "ok    tournament launcher verifies completion"

if command -v pwsh >/dev/null 2>&1; then
  ps_suggested="$(pwsh -NoProfile -File harness/semantic-review.ps1 -Provider both -RunDir "$tmp/run")"
  if printf '%s' "$ps_suggested" | grep -Eq -- '--model|--effort|--reasoning-effort'; then
    echo "FAIL PowerShell semantic launcher specifies a model control" >&2
    exit 1
  fi
  pwsh -NoProfile -File harness/semantic-review.ps1 -Provider both -RunDir "$tmp/run" -Execute >/dev/null
  echo "ok    PowerShell semantic launcher inherits host model"
fi

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/repo/scripts"
cp scripts/check-manifests.sh "$tmp/repo/scripts/"
mkdir -p "$tmp/repo/.architrave" "$tmp/repo/node_modules" "$tmp/repo/assets"
printf '%s\n' 'mcp-'"ignoredtoken1234" > "$tmp/repo/.architrave/ignored.txt"
printf '%s\n' 'mcp-'"ignoredtoken1234" > "$tmp/repo/node_modules/ignored.txt"
printf '%s\n' 'mcp-'"ignoredtoken1234" > "$tmp/repo/assets/ignored.png"

clean_output="$(cd "$tmp/repo" && ARCHITRAVE_FORCE_GREP=1 ./scripts/check-manifests.sh --scan-only)"
grep -q 'no legacy config references' <<<"$clean_output"
grep -q 'no MCP-looking bearer tokens or auth headers' <<<"$clean_output"
echo "ok    grep fallback clean scan"

printf '%s\n' 'mcp-'"abcdefghijklmnop" > "$tmp/repo/synthetic-token.txt"
set +e
(cd "$tmp/repo" && ARCHITRAVE_FORCE_GREP=1 ./scripts/check-manifests.sh --scan-only) >"$tmp/positive-output" 2>&1
ret=$?
set -e
[ "$ret" -eq 1 ] || { echo "FAIL  synthetic token scan expected exit 1, got $ret" >&2; exit 1; }
grep -q 'possible MCP bearer token/auth material committed' "$tmp/positive-output"
echo "ok    grep fallback synthetic token rejected"

rm "$tmp/repo/synthetic-token.txt"
printf '%s%s\n' 'architrave' '-ui' > "$tmp/repo/legacy-name.txt"
set +e
(cd "$tmp/repo" && ARCHITRAVE_FORCE_GREP=1 ./scripts/check-manifests.sh --scan-only) >"$tmp/legacy-output" 2>&1
ret=$?
set -e
[ "$ret" -eq 1 ] || { echo "FAIL  legacy-name scan expected exit 1, got $ret" >&2; exit 1; }
grep -q 'legacy config name references remain' "$tmp/legacy-output"
echo "ok    grep fallback legacy name rejected"

rm "$tmp/repo/legacy-name.txt"
mkdir "$tmp/fake-bin"
cat > "$tmp/fake-bin/grep" <<'SH'
#!/bin/sh
echo 'synthetic scanner failure' >&2
exit 2
SH
chmod +x "$tmp/fake-bin/grep"
set +e
(cd "$tmp/repo" && PATH="$tmp/fake-bin:/usr/bin:/bin" ARCHITRAVE_FORCE_GREP=1 ./scripts/check-manifests.sh --scan-only) >"$tmp/error-output" 2>&1
ret=$?
set -e
[ "$ret" -eq 1 ] || { echo "FAIL  scanner error expected gate exit 1, got $ret" >&2; exit 1; }
grep -q 'legacy config scan failed' "$tmp/error-output"
grep -q 'MCP bearer/auth scan failed' "$tmp/error-output"
grep -q 'synthetic scanner failure' "$tmp/error-output"
echo "ok    scanner operational error fails closed"

if command -v rg >/dev/null 2>&1; then
	printf '%s\n' 'mcp-'"abcdefghijklmnop" > "$tmp/repo/synthetic-token.txt"
	set +e
	(cd "$tmp/repo" && ./scripts/check-manifests.sh --scan-only) >"$tmp/rg-output" 2>&1
	ret=$?
	set -e
	[ "$ret" -eq 1 ] || { echo "FAIL  ripgrep token scan expected exit 1, got $ret" >&2; exit 1; }
	grep -q 'possible MCP bearer token/auth material committed' "$tmp/rg-output"
	echo "ok    ripgrep synthetic token rejected"
fi
echo "MANIFEST-SCANNER: PASS"
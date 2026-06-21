#!/usr/bin/env bash
# Architrave — backend + infra deterministic gate (complements gates/checks.sh,
# which covers the UI lane). Reads the `backend` and `iac` blocks of
# architrave.config.json and runs: the backend build/test, the IaC PLAN (never apply),
# the policy lint, and a secret scan of the IaC path.
#
#   gates/backend-checks.sh
#
# Exit 0 = PASS, non-zero = FAIL. Infra is PLAN-ONLY: this gate refuses to run an
# apply-shaped command. Dependency: jq.
set -uo pipefail
command -v jq >/dev/null 2>&1 || { echo "backend-checks: 'jq' is required (brew install jq)" >&2; exit 2; }

find_root() {
  local d="$PWD"
  while [ "$d" != "/" ]; do
    [ -f "$d/architrave.config.json" ] && { printf '%s\n' "$d"; return 0; }
    d="$(dirname "$d")"
  done
  return 1
}
root="$(find_root)" || { echo "backend-checks: architrave.config.json not found" >&2; exit 2; }
cd "$root"
root="$(pwd -P)"

bcfg() { jq -r --arg k "$1" '.backend[$k] // ""' architrave.config.json; }
icfg() { jq -r --arg k "$1" '.iac[$k] // ""' architrave.config.json; }
has_block() { [ "$(jq -r --arg b "$1" '.[$b] // empty' architrave.config.json)" != "" ]; }

fail=0
echo "== Architrave backend-checks (root: $root) =="

if ! has_block backend && ! has_block iac; then
  echo "skip  no backend/iac block in architrave.config.json"
  exit 0
fi

run_step() {
  local name="$1" cmd="$2"
  if [ -z "$cmd" ]; then echo "skip  $name (not configured)"; return 0; fi
  echo "== $name: $cmd =="
  if eval "$cmd"; then echo "ok    $name"; else echo "FAIL  $name"; fail=1; fi
}

project_paths_from_solution() {
  local solution="$1"
  case "$solution" in
    *.slnx)
      sed -nE 's/.*<Project[^>]*[[:space:]]Path="([^"]+)".*/\1/p' "$solution"
      ;;
    *.sln)
      sed -nE 's/^[[:space:]]*Project\([^)]*\)[[:space:]]*=[^,]*,[[:space:]]*"([^"]+)".*/\1/p' "$solution" | grep -E '\.(csproj|fsproj|vbproj|vcxproj)$' || true
      ;;
  esac
}

validate_backend_solution_paths() {
  local solution="$1" solution_dir path candidate candidate_dir full bad=0
  [ -n "$solution" ] || return 0
  case "$solution" in *.sln|*.slnx) ;; *) return 0 ;; esac
  echo "== backend solution path check: $solution =="
  if [ ! -f "$solution" ]; then
    echo "FAIL  backend solution not found: $solution"
    fail=1
    return 0
  fi
  solution_dir="$(cd "$(dirname "$solution")" && pwd -P)"
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    case "$path" in
      /*) candidate="$path" ;;
      *) candidate="$solution_dir/$path" ;;
    esac
    candidate_dir="$(dirname "$candidate")"
    if [ -d "$candidate_dir" ]; then
      full="$(cd "$candidate_dir" && pwd -P)/$(basename "$candidate")"
    else
      full="$candidate"
    fi
    case "$full" in
      "$root"/*) ;;
      *) echo "FAIL  solution project escapes repo: $path -> $full"; bad=1; continue ;;
    esac
    if [ ! -f "$full" ]; then
      echo "FAIL  solution project missing: $path -> $full"
      bad=1
    fi
  done < <(project_paths_from_solution "$solution")
  if [ "$bad" -eq 0 ]; then echo "ok    backend solution project paths stay inside repo"; else fail=1; fi
}

# --- Backend lane ---
if has_block backend; then
  validate_backend_solution_paths "$(bcfg solution)"
  run_step "backend build" "$(bcfg build)"
  run_step "backend test"  "$(bcfg test)"
fi

# --- Infra lane (PLAN-ONLY) ---
if has_block iac; then
  plan="$(icfg plan)"
  # Safety: refuse apply-shaped commands. Infra is plan-only by charter.
  if printf '%s' "$plan" | grep -Eiq 'kubectl[[:space:]]+(apply|create|delete|replace|patch)|terraform[[:space:]]+(apply|destroy)|az[[:space:]]+deployment[[:space:]]+[a-z]+[[:space:]]+create|pulumi[[:space:]]+(up|destroy)|helm[[:space:]]+(install|upgrade|uninstall)|apply[[:space:]]+-f'; then
    echo "FAIL  iac.plan looks like an APPLY ('$plan') — infra is plan-only; use diff / what-if / plan"
    fail=1
  else
    run_step "iac plan"   "$plan"
    run_step "iac policy" "$(icfg policy)"
  fi
fi

# --- Secret scan (IaC path; *.example.* / *.sample excluded) ---
iac_path="$(icfg path)"
if [ -n "$iac_path" ] && command -v git >/dev/null 2>&1; then
  echo "== secret scan: $iac_path =="
  hits="$(git grep -nIE '(-----BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|(client_secret|api_key|apikey|password)[[:space:]]*[:=][[:space:]]*[^[:space:]]{12,})' -- "$iac_path" 2>/dev/null | grep -ivE '\.example\.|\.sample|example\.ya?ml' || true)"
  if [ -n "$hits" ]; then
    echo "FAIL  possible committed secret(s):"; printf '%s\n' "$hits" | sed 's/^/      /' | head -10; fail=1
  else
    echo "ok    no obvious secrets under $iac_path"
  fi
fi

if [ "$fail" -eq 0 ]; then echo "BACKEND-CHECKS: PASS"; else echo "BACKEND-CHECKS: FAIL"; fi
exit "$fail"

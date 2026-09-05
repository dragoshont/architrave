#!/usr/bin/env bash

# Shared fail-closed path handling for install.sh and update.sh.
# Call managed_paths_init with a canonical existing target directory first.

managed_paths_init() {
  MANAGED_ROOT="$1"
  MANAGED_LABEL="${2:-architrave}"
  [ -n "$MANAGED_ROOT" ] && [ -d "$MANAGED_ROOT" ] && [ ! -L "$MANAGED_ROOT" ] || {
    echo "$MANAGED_LABEL: target root must resolve to a real directory" >&2
    return 1
  }
}

managed_fail() {
  echo "$MANAGED_LABEL: unsafe managed path '$1': $2" >&2
  return 1
}

managed_validate_relative() {
  local rel="$1" segment
  [ -n "$rel" ] || managed_fail "$rel" "empty path" || return 1
  case "$rel" in
    /*|*\\*) managed_fail "$rel" "path must be relative and use '/' separators"; return 1 ;;
  esac
  IFS='/' read -r -a managed_segments <<<"$rel"
  for segment in "${managed_segments[@]}"; do
    case "$segment" in
      ''|.|..) managed_fail "$rel" "path contains an empty, '.' or '..' segment"; return 1 ;;
    esac
  done
}

managed_parent_relative() {
  local rel="$1"
  if [[ "$rel" == */* ]]; then printf '%s\n' "${rel%/*}"; else printf '\n'; fi
}

managed_absolute() {
  managed_validate_relative "$1" || return 1
  printf '%s/%s\n' "$MANAGED_ROOT" "$1"
}

managed_preflight_dir() {
  local rel="$1" current="$MANAGED_ROOT" segment
  managed_validate_relative "$rel" || return 1
  IFS='/' read -r -a managed_segments <<<"$rel"
  for segment in "${managed_segments[@]}"; do
    current="$current/$segment"
    [ ! -L "$current" ] || managed_fail "$rel" "component '$segment' is a symbolic link" || return 1
    if [ -e "$current" ]; then
      [ -d "$current" ] || managed_fail "$rel" "component '$segment' is not a directory" || return 1
    else
      return 0
    fi
  done
}

managed_require_dir() {
  local rel="$1" path
  managed_preflight_dir "$rel" || return 1
  path="$(managed_absolute "$rel")" || return 1
  [ -d "$path" ] && [ ! -L "$path" ] || managed_fail "$rel" "directory is missing or unsafe" || return 1
}

managed_ensure_dir() {
  local rel="$1" current="$MANAGED_ROOT" built="" segment
  managed_validate_relative "$rel" || return 1
  IFS='/' read -r -a managed_segments <<<"$rel"
  for segment in "${managed_segments[@]}"; do
    built="${built:+$built/}$segment"
    current="$current/$segment"
    [ ! -L "$current" ] || managed_fail "$rel" "component '$segment' is a symbolic link" || return 1
    if [ -e "$current" ]; then
      [ -d "$current" ] || managed_fail "$rel" "component '$segment' is not a directory" || return 1
    else
      if [[ "$built" == */* ]]; then managed_require_dir "${built%/*}" || return 1; fi
      mkdir "$current" || return 1
    fi
    managed_require_dir "$built" || return 1
  done
}

managed_preflight_file() {
  local rel="$1" parent path
  managed_validate_relative "$rel" || return 1
  parent="$(managed_parent_relative "$rel")"
  if [ -n "$parent" ]; then managed_preflight_dir "$parent" || return 1; fi
  path="$(managed_absolute "$rel")" || return 1
  [ ! -L "$path" ] || managed_fail "$rel" "destination is a symbolic link" || return 1
  if [ -e "$path" ]; then
    [ -f "$path" ] || managed_fail "$rel" "destination is not a regular file" || return 1
  fi
}

managed_require_file() {
  local rel="$1" path
  managed_preflight_file "$rel" || return 1
  path="$(managed_absolute "$rel")" || return 1
  [ -f "$path" ] && [ ! -L "$path" ] || managed_fail "$rel" "regular file is missing or unsafe" || return 1
}

managed_preflight_tree() {
  local rel="$1" path unsafe
  managed_preflight_dir "$rel" || return 1
  path="$(managed_absolute "$rel")" || return 1
  [ -e "$path" ] || return 0
  managed_require_dir "$rel" || return 1
  unsafe="$(find "$path" -type l -print -quit 2>/dev/null)"
  [ -z "$unsafe" ] || managed_fail "$rel" "tree contains symbolic link '${unsafe#$MANAGED_ROOT/}'" || return 1
  unsafe="$(find "$path" ! -type d ! -type f ! -type l -print -quit 2>/dev/null)"
  [ -z "$unsafe" ] || managed_fail "$rel" "tree contains unsupported entry '${unsafe#$MANAGED_ROOT/}'" || return 1
}

managed_assert_source_file() {
  local source="$1"
  [ -f "$source" ] && [ ! -L "$source" ] || {
    echo "$MANAGED_LABEL: packaged source is not a regular non-link file: $source" >&2
    return 1
  }
}

managed_assert_source_tree() {
  local source="$1" unsafe
  [ -d "$source" ] && [ ! -L "$source" ] || {
    echo "$MANAGED_LABEL: packaged source is not a real directory: $source" >&2
    return 1
  }
  unsafe="$(find "$source" -type l -print -quit 2>/dev/null)"
  [ -z "$unsafe" ] || {
    echo "$MANAGED_LABEL: packaged source tree contains a symbolic link: $unsafe" >&2
    return 1
  }
  unsafe="$(find "$source" ! -type d ! -type f ! -type l -print -quit 2>/dev/null)"
  [ -z "$unsafe" ] || {
    echo "$MANAGED_LABEL: packaged source tree contains an unsupported entry: $unsafe" >&2
    return 1
  }
}

managed_stage_copy() {
  local source="$1" parent_abs="$2" destination="$3" temp
  temp="$(mktemp "$parent_abs/.architrave.tmp.XXXXXX")" || return 1
  if ! cp -p "$source" "$temp"; then rm -f "$temp"; return 1; fi
  printf '%s\n' "$temp"
}

managed_safe_replace() {
  local source="$1" rel="$2" parent parent_abs destination temp
  managed_assert_source_file "$source" || return 1
  managed_preflight_file "$rel" || return 1
  parent="$(managed_parent_relative "$rel")"
  if [ -n "$parent" ]; then managed_require_dir "$parent" || return 1; parent_abs="$(managed_absolute "$parent")"; else parent_abs="$MANAGED_ROOT"; fi
  destination="$(managed_absolute "$rel")" || return 1
  temp="$(managed_stage_copy "$source" "$parent_abs" "$destination")" || return 1
  if [ -n "$parent" ]; then managed_require_dir "$parent" || { rm -f "$temp"; return 1; }; fi
  managed_preflight_file "$rel" || { rm -f "$temp"; return 1; }
  mv -f "$temp" "$destination" || { rm -f "$temp"; return 1; }
  managed_require_file "$rel" || return 1
}

managed_safe_create() {
  local source="$1" rel="$2" parent parent_abs destination temp
  managed_assert_source_file "$source" || return 1
  managed_preflight_file "$rel" || return 1
  destination="$(managed_absolute "$rel")" || return 1
  if [ -e "$destination" ] || [ -L "$destination" ]; then managed_fail "$rel" "destination already exists"; return 1; fi
  parent="$(managed_parent_relative "$rel")"
  if [ -n "$parent" ]; then managed_require_dir "$parent" || return 1; parent_abs="$(managed_absolute "$parent")"; else parent_abs="$MANAGED_ROOT"; fi
  temp="$(managed_stage_copy "$source" "$parent_abs" "$destination")" || return 1
  if [ -n "$parent" ]; then managed_require_dir "$parent" || { rm -f "$temp"; return 1; }; fi
  managed_preflight_file "$rel" || { rm -f "$temp"; return 1; }
  if [ -e "$destination" ] || [ -L "$destination" ]; then rm -f "$temp"; managed_fail "$rel" "destination appeared before create"; return 1; fi
  mv -n "$temp" "$destination" || { rm -f "$temp"; return 1; }
  [ ! -e "$temp" ] || { rm -f "$temp"; managed_fail "$rel" "destination appeared before create"; return 1; }
  managed_require_file "$rel" || return 1
}

managed_safe_remove() {
  local rel="$1" parent destination
  managed_preflight_file "$rel" || return 1
  destination="$(managed_absolute "$rel")" || return 1
  [ -e "$destination" ] || return 0
  parent="$(managed_parent_relative "$rel")"
  if [ -n "$parent" ]; then managed_require_dir "$parent" || return 1; fi
  managed_require_file "$rel" || return 1
  rm -f "$destination" || return 1
  [ ! -e "$destination" ] && [ ! -L "$destination" ] || managed_fail "$rel" "file remains after removal" || return 1
}

managed_copy_tree() {
  local source="$1" rel="$2" entry suffix destination_rel
  managed_assert_source_tree "$source" || return 1
  managed_preflight_tree "$rel" || return 1
  managed_ensure_dir "$rel" || return 1
  managed_preflight_tree "$rel" || return 1
  while IFS= read -r entry; do
    [ "$entry" = "$source" ] && continue
    suffix="${entry#$source/}"
    managed_ensure_dir "$rel/$suffix" || return 1
  done < <(find "$source" -type d -name __pycache__ -prune -o -type d -print | LC_ALL=C sort)
  while IFS= read -r entry; do
    suffix="${entry#$source/}"
    destination_rel="$rel/$suffix"
    managed_safe_replace "$entry" "$destination_rel" || return 1
  done < <(find "$source" -type d -name __pycache__ -prune -o -type f ! -name '*.pyc' -print | LC_ALL=C sort)
  managed_preflight_tree "$rel" || return 1
}
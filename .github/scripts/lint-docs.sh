#!/usr/bin/env bash
# Lint script for blazing-docs MDX/MD files
# Run locally: bash .github/scripts/lint-docs.sh
set -euo pipefail

ERROR_FILE=$(mktemp)
WARN_FILE=$(mktemp)
echo 0 > "$ERROR_FILE"
echo 0 > "$WARN_FILE"
trap 'rm -f "$ERROR_FILE" "$WARN_FILE"' EXIT

error() {
  echo "ERROR: $1"
  echo $(( $(cat "$ERROR_FILE") + 1 )) > "$ERROR_FILE"
}
warn() {
  echo "WARN:  $1"
  echo $(( $(cat "$WARN_FILE") + 1 )) > "$WARN_FILE"
}

# --- 1. Placeholder Akash addresses (akash1...xxx) ---
echo "=== Checking for placeholder Akash addresses ==="
while IFS= read -r line; do
  error "$line"
done < <(grep -rn 'akash1\.\.\.' --include="*.mdx" --include="*.md" . 2>/dev/null || true)

# --- 2. Markdown table structure ---
echo "=== Checking markdown table structure ==="

while IFS= read -r file; do
  in_table=false
  in_code=false
  header_cols=0
  separator_seen=false
  table_start_line=0
  line_num=0

  while IFS= read -r line; do
    line_num=$((line_num + 1))

    # Track code blocks
    if [[ "$line" =~ ^\`\`\` ]]; then
      if $in_code; then
        in_code=false
      else
        in_code=true
        if $in_table; then
          error "$file:$table_start_line: table interrupted by code block at line $line_num"
          in_table=false
        fi
      fi
      continue
    fi
    $in_code && continue

    # Detect table row
    if [[ "$line" =~ ^[[:space:]]*\| ]]; then
      if ! $in_table; then
        in_table=true
        separator_seen=false
        table_start_line=$line_num

        stripped="${line#"${line%%[![:space:]]*}"}"
        stripped="${stripped#|}"
        stripped="${stripped%|}"
        header_cols=$(echo "$stripped" | awk -F'|' '{print NF}')
      else
        stripped="${line#"${line%%[![:space:]]*}"}"
        stripped="${stripped#|}"
        stripped="${stripped%|}"
        row_cols=$(echo "$stripped" | awk -F'|' '{print NF}')

        # Check separator row (second row should be |---|---|)
        if ! $separator_seen; then
          separator_seen=true
          clean="${line//[[:space:]|:\-]/}"
          if [[ -n "$clean" ]]; then
            error "$file:$line_num: table missing separator row (expected |---|---|, got content row)"
          fi
        fi

        if [[ $row_cols -ne $header_cols ]]; then
          error "$file:$line_num: table column mismatch — header has $header_cols cols, this row has $row_cols"
        fi
      fi
    else
      if $in_table; then
        if ! $separator_seen && [[ $line_num -gt $((table_start_line + 1)) ]]; then
          error "$file:$table_start_line: table has no separator row"
        fi
        in_table=false
      fi
    fi
  done < "$file"

  if $in_table && ! $separator_seen; then
    error "$file:$table_start_line: table has no separator row"
  fi
done < <(find . -name "*.mdx" -o -name "*.md")

# --- 3. Broken internal links ---
echo "=== Checking for broken internal links ==="
while IFS= read -r match; do
  file="${match%%:*}"
  rest="${match#*:}"
  line_num="${rest%%:*}"
  content="${rest#*:}"

  linked=$(echo "$content" | grep -oP '\]\(\K[^)]+' | head -1)
  if [[ -n "$linked" && "$linked" != http* && "$linked" != "#"* && "$linked" != mailto:* ]]; then
    dir=$(dirname "$file")
    linked_clean="${linked%%#*}"
    if [[ -n "$linked_clean" && ! -f "$dir/$linked_clean" ]]; then
      warn "$file:$line_num: broken link to '$linked_clean'"
    fi
  fi
done < <(grep -rn '\]\(' --include="*.mdx" --include="*.md" . 2>/dev/null || true)

# --- Summary ---
ERRORS=$(cat "$ERROR_FILE")
WARNINGS=$(cat "$WARN_FILE")
echo ""
echo "=== Lint Summary ==="
echo "Errors:   $ERRORS"
echo "Warnings: $WARNINGS"

if [[ $ERRORS -gt 0 ]]; then
  echo "FAILED"
  exit 1
fi

echo "PASSED"

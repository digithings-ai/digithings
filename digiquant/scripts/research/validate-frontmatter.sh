#!/bin/bash
# validate-frontmatter.sh — Check all skill Markdown files have valid YAML frontmatter.
# A valid header must:  (1) start with "---" on line 1
#                       (2) contain a "name:" key within the first 10 lines
#                       (3) contain a "description:" key within the first 10 lines
set -e

ERRORS=0

# Collect skill files (top-level and subdirectories)
while IFS= read -r -d '' file; do
  # Line 1 must be the opening fence
  line1=$(head -1 "$file")
  if [[ "$line1" != "---" ]]; then
    echo "MISSING ---     : $file"
    ERRORS=$((ERRORS + 1))
    continue
  fi

  # name: and description: must appear within the first 10 lines
  header=$(head -10 "$file")
  if ! echo "$header" | grep -q "^name:"; then
    echo "MISSING name:   : $file"
    ERRORS=$((ERRORS + 1))
  fi
  if ! echo "$header" | grep -q "^description:"; then
    echo "MISSING description: : $file"
    ERRORS=$((ERRORS + 1))
  fi
done < <(find skills -name "*.md" -print0 2>/dev/null)

if [[ $ERRORS -eq 0 ]]; then
  echo "✅ All skill frontmatter valid"
else
  echo ""
  echo "❌ $ERRORS frontmatter issue(s) found — fix the files listed above"
  exit 1
fi

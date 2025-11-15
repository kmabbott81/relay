#!/bin/bash

# Comprehensive import migration fix - handles all remaining "from src." imports

echo "Starting comprehensive import migration fix..."
echo ""

# Count total files before
BEFORE_COUNT=$(grep -r "from src\." --include="*.py" . 2>/dev/null | wc -l)
echo "Found $BEFORE_COUNT total occurrences of 'from src.' imports"
echo ""

# Create a list of all files that need fixing
echo "Identifying files that need fixes..."
FILES_TO_FIX=($(grep -r "from src\." --include="*.py" . 2>/dev/null | cut -d: -f1 | sort -u))
UNIQUE_FILES=${#FILES_TO_FIX[@]}
echo "Found $UNIQUE_FILES unique files to fix"
echo ""

# Process each file
COUNT=0
for FILE in "${FILES_TO_FIX[@]}"; do
  COUNT=$((COUNT + 1))
  PERCENT=$((COUNT * 100 / UNIQUE_FILES))

  # Show progress every 10 files
  if (( COUNT % 10 == 0 )); then
    echo "[$PERCENT%] Processing file $COUNT/$UNIQUE_FILES: $FILE"
  fi

  # Replace "from src." with "from relay_ai."
  sed -i 's/from src\./from relay_ai./g' "$FILE"
done

echo ""
echo "✓ All files processed"
echo ""

# Verify the fix
AFTER_COUNT=$(grep -r "from src\." --include="*.py" . 2>/dev/null | wc -l 2>/dev/null || echo "0")
echo "Import count after fix: $AFTER_COUNT occurrences"

if [ "$AFTER_COUNT" -eq "0" ]; then
  echo "✓ SUCCESS: All 'from src.' imports have been replaced!"
else
  echo "⚠ WARNING: Still found $AFTER_COUNT occurrences. These may need manual review."
fi

echo ""
echo "Migration complete!"

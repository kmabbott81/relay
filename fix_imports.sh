#!/bin/bash
# Bulk fix all old src.* imports to relay_ai.*

count=0
for file in $(find relay_ai src scripts -name "*.py" -type f 2>/dev/null | xargs grep -l "^from src\." 2>/dev/null); do
    # Use sed to replace src. with relay_ai. for import statements
    sed -i 's/^from src\./from relay_ai./g' "$file"
    sed -i 's/^import src\./import relay_ai./g' "$file"
    count=$((count + 1))
    echo "✓ Fixed: $file"
done

echo ""
echo "Fixed $count files total"

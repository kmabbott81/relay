#!/bin/bash

echo "Fixing incorrect import paths..."

# Fix relay_ai.knowledge -> relay_ai.platform.api.knowledge
find . -name "*.py" -type f -exec sed -i 's/from relay_ai\.knowledge\./from relay_ai.platform.api.knowledge./g' {} +
find . -name "*.py" -type f -exec sed -i 's/import relay_ai\.knowledge\./import relay_ai.platform.api.knowledge./g' {} +

# Fix relay_ai.memory -> relay_ai.platform.security.memory
find . -name "*.py" -type f -exec sed -i 's/from relay_ai\.memory\./from relay_ai.platform.security.memory./g' {} +
find . -name "*.py" -type f -exec sed -i 's/import relay_ai\.memory\./import relay_ai.platform.security.memory./g' {} +

# Fix relay_ai.stream -> relay_ai.platform.api.stream
find . -name "*.py" -type f -exec sed -i 's/from relay_ai\.stream\./from relay_ai.platform.api.stream./g' {} +
find . -name "*.py" -type f -exec sed -i 's/import relay_ai\.stream\./import relay_ai.platform.api.stream./g' {} +

echo "✓ Import paths fixed"

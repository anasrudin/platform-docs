#!/bin/bash
set -e

API_URL="http://localhost:8080"

echo "=== 1. Checking API Health ==="
curl -s -X GET $API_URL/health | jq

echo -e "\n=== 2. Creating Firecracker Session ==="
SESSION_RESP=$(curl -s -X POST $API_URL/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime": "microvm"}')

echo $SESSION_RESP | jq
SESSION_ID=$(echo $SESSION_RESP | jq -r '.session_id')

if [ "$SESSION_ID" == "null" ] || [ -z "$SESSION_ID" ]; then
  echo "Failed to create session!"
  exit 1
fi

echo -e "\n=== 3. Executing Tool in Firecracker Session ==="
EXEC_RESP=$(curl -s -X POST $API_URL/execute \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "'$SESSION_ID'",
    "tool": "python_run",
    "input": {
      "code": "print(\"Hello from Firecracker on Nomad!\")"
    }
  }')

echo $EXEC_RESP | jq

echo -e "\n=== 4. Executing WASM Tool (Auto Session) ==="
WASM_RESP=$(curl -s -X POST $API_URL/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "hello",
    "input": {
      "name": "Testing WASM Engine"
    }
  }')

echo $WASM_RESP | jq

echo -e "\n=== 5. Executing GUI Tool (Auto Session) ==="
GUI_RESP=$(curl -s -X POST $API_URL/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "browser_open",
    "input": {
      "url": "https://example.com"
    }
  }')

echo $GUI_RESP | jq

echo -e "\n=== E2E Test Completed ==="

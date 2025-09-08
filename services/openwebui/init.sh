#!/bin/sh
set -e

echo "[init.sh] Starting Open WebUI server..."
/app/backend/start.sh &
# Wait for Open WebUI API to become available
echo "[init.sh] Waiting for Open WebUI to start..." &&
while ! curl -s -o /dev/null "http://localhost:8080/health"; do
  sleep 2;
done &&
echo "[init.sh] Open WebUI started"
echo "[init.sh] Sign up default admin user ..."

SIGNUP_RESPONSE=$(curl -s -X POST "http://localhost:8080/api/v1/auths/signup" \
  -H "Content-Type: application/json" \
  --data-raw "{\"name\":\"${WEBUI_ADMIN_USER}\", \"email\":\"${WEBUI_ADMIN_EMAIL}\", \"password\":\"${WEBUI_ADMIN_PASS}\"}")
API_KEY=$(echo "${SIGNUP_RESPONSE}" | jq -r '.token')
echo "[init.sh] Received API_KEY: ${API_KEY}"

for tool in /init_app/tools/*.json; do
  echo "[init.sh] Importing tool: $tool"
  curl -s -X POST "http://localhost:8080/api/v1/tools/create" \
       -H 'accept: application/json' \
       -H "Authorization: Bearer ${API_KEY}" \
       -H "Content-Type: application/json" \
       --data-binary @"$tool" \
       || echo "Failed to import $tool"
done

echo -e "\n[init.sh] Tool import completed!"
wait
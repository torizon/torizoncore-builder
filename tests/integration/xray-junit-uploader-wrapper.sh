#!/bin/bash

if [ -z "$TORIZON_OS_TEST_PLAN_KEY" ]; then
  echo "Error: TORIZON_OS_TEST_PLAN_KEY is not set."
  exit 1
fi

for report_path in tests/integration/workdir/reports/report-*-nightly.xml; do
  if [ ! -e "$report_path" ]; then
    echo "Warning: Report path '$report_path' does not exist, skipping."
    continue
  fi

  filename=$(basename "$report_path")
  test_name=$(echo "$filename" | sed -E 's/^report-(.*)\.xml$/\1/' | tr '[:lower:]' '[:upper:]' | tr '-' '_')

  var_name="${test_name}_TEST_EXEC_KEY"

  if [ -n "${!var_name}" ]; then
    echo "==> Uploading report: $report_path"
    echo "    Using test plan key: $TORIZON_OS_TEST_PLAN_KEY"
    echo "    Using test execution key: ${!var_name} (variable: $var_name)"

    xray-junit-uploader \
      --report "$report_path" \
      --test-plan-key "$TORIZON_OS_TEST_PLAN_KEY" \
      --test-exec-key "${!var_name}"
  else
    echo "Warning: Variable ${var_name} is not set, skipping $report_path"
  fi
done

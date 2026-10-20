#!/bin/bash

if [ -z "$TORIZON_OS_TEST_PLAN_KEY" ]; then
  echo "Error: TORIZON_OS_TEST_PLAN_KEY is not set."
  exit 1
fi

missing_keys=()
failed_reports=()

for report_path in tests/integration/workdir/reports/report-*-nightly.xml; do
  if [ ! -e "$report_path" ]; then
    echo "Warning: Report path '$report_path' does not exist, skipping."
    continue
  fi

  filename=$(basename "$report_path")
  test_name=$(echo "$filename" | sed -E 's/^report-(.*)\.xml$/\1/' | tr '[:lower:]' '[:upper:]' | tr '-' '_')

  var_name="${test_name}_TEST_EXEC_KEY"

  if [ -z "${!var_name}" ]; then
    echo "Error: Variable ${var_name} is not set, skipping '$report_path'."
    missing_keys+=("$var_name")
    continue
  fi

  echo "==> Uploading report: $report_path"
  echo "    Using test plan key: $TORIZON_OS_TEST_PLAN_KEY"
  echo "    Using test execution key: ${!var_name} (variable: $var_name)"

  if ! xray-junit-uploader \
      --report "$report_path" \
      --test-plan-key "$TORIZON_OS_TEST_PLAN_KEY" \
      --test-exec-key "${!var_name}"; then
    echo "Error: Upload of '$report_path' failed."
    failed_reports+=("$report_path")
  fi
done

# Fail only after trying every report, so one bad report does not keep the others out of Xray.
if [ ${#missing_keys[@]} -gt 0 ]; then
  echo "Error: Test execution keys not set: ${missing_keys[*]}"
fi
if [ ${#failed_reports[@]} -gt 0 ]; then
  echo "Error: Uploads failed: ${failed_reports[*]}"
fi
if [ ${#missing_keys[@]} -gt 0 ] || [ ${#failed_reports[@]} -gt 0 ]; then
  exit 1
fi

#!/bin/bash

SCRIPT_DIR="$(dirname ${BASH_SOURCE[0]})"

cp -a --remove-destination "$SCRIPT_DIR/post-commit" "$SCRIPT_DIR/../.git/hooks/post-commit"

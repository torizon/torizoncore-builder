load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'

@test "push: check help output" {
    run torizoncore-builder push --help
    assert_success
    assert_output --partial 'usage: torizoncore-builder push'
}

@test "push: docker-compose canonicalization" {
    local CANON_DIR="$SAMPLES_DIR/push/canonicalize"

	# Test-case: everything good
    run torizoncore-builder push "$CANON_DIR/docker-compose-good.yml" --canonicalize-only --force
    assert_success
    assert_output --partial "has been generated"
	# Check produced file:
    run cat "$CANON_DIR/docker-compose-good.lock.yml"
    assert_success
    assert_output --partial "torizon/torizoncore-builder@sha256:"
    assert_output --partial "torizon/debian@sha256:"
    assert_output --partial "torizon/weston@sha256:"

	# Test-case: error present
    run torizoncore-builder push "$CANON_DIR/docker-compose-no-services.yml" --canonicalize-only --force
    assert_failure
    assert_output --partial "No 'services' section in compose file"

	# Test-case: error present
    run torizoncore-builder push "$CANON_DIR/docker-compose-no-image.yml" --canonicalize-only --force
    assert_failure
    assert_output --partial "No image specified for service"

	# Test-case: error present
    run torizoncore-builder push "$CANON_DIR/docker-compose-with-registry.yml" --canonicalize-only --force
    assert_failure
    assert_output --partial "Registry name specification is not supported"
}

load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'
load 'lib/common.bash'

@test "deploy: run without parameters" {
    run torizoncore-builder deploy
    assert_failure 255
    assert_output --partial "One of the following arguments is required: --output-directory, --remote-host"
}

@test "deploy: check help output" {
    run torizoncore-builder deploy --help
    assert_success
    assert_output --partial "usage: torizoncore-builder deploy"
}

@test "deploy: deploy changes to Tezi image without images unpack" {
    torizoncore-builder-clean-storage

    run torizoncore-builder deploy --output-directory some_dir some_branch
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}

@test "deploy: deploy changes to Tezi image" {
    local ROOTFS=temp_rootfs
    rm -rf my_new_image
    rm -rf $ROOTFS

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    torizoncore-builder union --changes-directory $SAMPLES_DIR/changes branch1

    run torizoncore-builder deploy --output-directory my_new_image branch1
    assert_success
    assert_output --partial "Packing rootfs done."

    mkdir $ROOTFS && cd $ROOTFS
    tar -I zstd -xvf ../my_new_image/*.ota.tar.zst
    run cat ostree/deploy/torizon/deploy/*/etc/myconfig.txt
    assert_success
    assert_output --partial "enabled=1"

    check-file-ownership-as-workdir ../my_new_image
    check-file-ownership-as-workdir ../my_new_image/*.ota.tar.zst

    cd .. && rm -rf $ROOTFS my_new_image
}

@test "deploy: deploy changes to device without images unpack" {
    requires-device
    torizoncore-builder-clean-storage

    run torizoncore-builder deploy --remote-host $DEVICE_ADDR \
                                   --remote-username $DEVICE_USER \
                                   --remote-password $DEVICE_PASS \
                                   --remote-port $DEVICE_PORT \
                                   --reboot some_branch
    assert_failure
    assert_output --partial "Error: could not find an Easy Installer image in the storage."
    assert_output --partial "Please use the 'images' command to unpack an Easy Installer image before running this command."
}

@test "deploy: deploy changes to device" {
    requires-device

    torizoncore-builder-clean-storage
    torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
    torizoncore-builder union --changes-directory $SAMPLES_DIR/changes2 branch1

    run torizoncore-builder deploy --remote-host $DEVICE_ADDR \
                                   --remote-username $DEVICE_USER \
                                   --remote-password $DEVICE_PASS \
                                   --remote-port $DEVICE_PORT \
                                   --reboot branch1
    assert_success
    assert_output --partial "Deploying successfully finished"

    run device-wait 20
    assert_success

    run device-shell-root /usr/sbin/secret_of_life
    assert_failure 42
}

@test "deploy: check with --image-autoinstall" {
  local LICENSE_FILE="license-fc.html"
  local LICENSE_DIR="$SAMPLES_DIR/installer/$LICENSE_FILE"

  torizoncore-builder-clean-storage
  run torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
  assert_success

  run torizoncore-builder union branch1
  assert_success

  # Check if licence is present in the image.
  local licence=$(torizoncore-builder-shell "grep -E \
                -e '\s*\"license\"\s*:\s*\".*\"\s*,' /storage/tezi/image.json")

  if [ -n "$licence" ]; then
    rm -rf some_dir

    # Image has licence
    run torizoncore-builder deploy --output-directory some_dir branch1 \
                                   --image-autoinstall \
                                   --image-accept-licence
    assert_success

    # Remove license from image
    run torizoncore-builder-shell \
        "sed -i '/\s*\"license\"\s*:\s\".*\"\s*,/d' /storage/tezi/image.json"
    assert_success

    run torizoncore-builder-shell "grep -E \
        -e '\s*\"license\"\s*:\s*\".*\"\s*,' /storage/tezi/image.json"
    assert_failure

  fi

  rm -rf some_dir

  run torizoncore-builder deploy --output-directory some_dir branch1 \
                                 --image-autoinstall
  assert_success

  rm -rf some_dir

  run torizoncore-builder deploy --output-directory some_dir branch1 \
                                 --image-autoinstall \
                                 --image-accept-licence
  assert_success

  rm -rf some_dir

  run torizoncore-builder deploy --output-directory some_dir branch1 \
                                 --image-autoinstall \
                                 --image-licence "$LICENSE_DIR"
  assert_failure
  assert_output --partial \
      "Error: To enable the auto-installation feature you must accept the licence \"$LICENSE_FILE\""

  rm -rf some_dir

  run torizoncore-builder deploy --output-directory some_dir branch1
  assert_success
  run grep autoinstall some_dir/image.json
  assert_output --partial "false"

  rm -rf some_dir

  run torizoncore-builder deploy --output-directory some_dir branch1 \
                                 --image-autoinstall --image-accept-licence
  assert_success
  run grep autoinstall some_dir/image.json
  assert_output --partial "true"

  rm -rf some_dir
  run torizoncore-builder deploy --output-directory some_dir branch1 --no-image-autoinstall
  assert_success
  run grep autoinstall some_dir/image.json
  assert_output --partial "false"

  rm -rf some_dir
}

@test "deploy: check with --image-autoreboot" {
  local REG_EX_GENERATED='^\s*reboot\s+-f\s*#\s*torizoncore-builder\s+generated'
  torizoncore-builder-clean-storage
  torizoncore-builder images --remove-storage unpack $DEFAULT_TEZI_IMAGE
  torizoncore-builder union branch1

  rm -rf some_dir

  run torizoncore-builder deploy --output-directory some_dir branch1
  assert_success
  run grep reboot some_dir/wrapup.sh
  refute_output

  rm -rf some_dir

  run torizoncore-builder deploy --output-directory some_dir branch1 --image-autoreboot
  assert_success
  run grep -E $REG_EX_GENERATED some_dir/wrapup.sh
  assert_success

  rm -rf some_dir
  run torizoncore-builder deploy --output-directory some_dir branch1 --no-image-autoreboot
  run grep -E $REG_EX_GENERATED some_dir/wrapup.sh
  refute_output

  rm -rf some_dir
}

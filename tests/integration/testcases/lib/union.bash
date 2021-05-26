#!/bin/bash

#
# Functions shared by the "union" test cases.
#


# Add files to dir so them can be checked for default credentials later
add-files-to-check-default-credentials() {
    local CHANGES_DIR="$1"

    local FILE_ATTRS="file4|F|0600|1000:2000 \
                      file5|F|0750|2000:1000 \
                      dir2|D|0700|1000:1000"

    for FILE_ATTR in $FILE_ATTRS
    do
        FILE_NAME=$(echo $FILE_ATTR | cut -d '|' -f 1)
        FILE_TYPE=$(echo $FILE_ATTR | cut -d '|' -f 2)
        FILE_MODE=$(echo $FILE_ATTR | cut -d '|' -f 3)
        FILE_OWNER=$(echo $FILE_ATTR | cut -d '|' -f 4)

        if [ $FILE_TYPE == "F" ]
        then
            run torizoncore-builder-shell "touch $CHANGES_DIR/usr/etc/$FILE_NAME"
        else
            run torizoncore-builder-shell "mkdir -p $CHANGES_DIR/usr/etc/$FILE_NAME"
        fi
        run torizoncore-builder-shell "chmod $FILE_MODE $CHANGES_DIR/usr/etc/$FILE_NAME"
        run torizoncore-builder-shell "chown $FILE_OWNER $CHANGES_DIR/usr/etc/$FILE_NAME"
    done
}

# Make some changes in the "isolated" or "changed-dir" so we can check if
# they will end up with different credentials than those set in the tcattr
make-changes-to-validate-tcattr-acls() {
    local CHANGES_DIR="$1"

    local FILE_ATTRS="file1|0666|0:0 \
                      dir1|0777|0:1000 \
                      dir1/file2|0000|2000:0 \
                      dir1/file3|0600|2000:1000"

    for FILE_ATTR in $FILE_ATTRS
    do
        FILE_NAME=$(echo $FILE_ATTR | cut -d '|' -f 1)
        FILE_MODE=$(echo $FILE_ATTR | cut -d '|' -f 2)
        FILE_OWNER=$(echo $FILE_ATTR | cut -d '|' -f 3)
        FILE_GROUP=$(echo $FILE_ATTR | cut -d '|' -f 4)

        run torizoncore-builder-shell "chmod $FILE_MODE $CHANGES_DIR/usr/etc/$FILE_NAME"
        run torizoncore-builder-shell "chown $FILE_OWNER:$FILE_GROUP $CHANGES_DIR/usr/etc/$FILE_NAME"
    done
}

# Check credentials for all files
check-credentials() {
    local ROOTFS="$1"

    local FILE_ATTRS="file1|-rw-------|1000|2000 \
                      dir1|drwx------|1000|0 \
                      dir1/file2|-rw-rw----|1000|0 \
                      dir1/file3|-rw-rw-rw-|1000|2000 \
                      file4|-rw-rw----|0|0 \
                      file5|-rwxrwx---|0|0 \
                      dir2|drwxr-xr-x|0|0"

    for FILE_ATTR in $FILE_ATTRS
    do
        FILE_NAME=$(echo $FILE_ATTR | cut -d '|' -f 1)
        FILE_MODE=$(echo $FILE_ATTR | cut -d '|' -f 2)
        FILE_USER=$(echo $FILE_ATTR | cut -d '|' -f 3)
        FILE_GROUP=$(echo $FILE_ATTR | cut -d '|' -f 4)

        run torizoncore-builder-shell "ls -ldn $ROOTFS/usr/etc/$FILE_NAME"
        assert_success
        assert_output --partial "$FILE_NAME"
        assert_output --regexp "$FILE_MODE .* $FILE_USER $FILE_GROUP"
    done
}

# Check if there isn't any ".tcattr" file in the OSTree commit
check-tcattr-files-removal() {
    local ROOTFS="$1"

    run torizoncore-builder-shell "find $ROOTFS -name '.tcattr'"
    assert_success
    refute_output --partial '.tcattr'
}

# Check credentials for all files include with the --extra-changes-directory
check-credentials-for-links() {
    local ROOTFS="$1"

    local FILE_ATTRS="usr/bin/file1|-rw-rw-r--|1000|2000 \
                      usr/bin/file2|-rw-rw----|0|0 \
                      usr/bin/dir1|drwxrwxr-x|1000|2000 \
                      usr/bin/dir1/file11|-rw-rw-r--|1000|1000 \
                      usr/bin/broken_link|lrwxrwxrwx|0|0 \
                      usr/bin/good_link|lrwxrwxrwx|0|0 "


    for FILE_ATTR in $FILE_ATTRS
    do
        FILE_NAME=$(echo  $FILE_ATTR | cut -d '|' -f 1)
        FILE_MODE=$(echo  $FILE_ATTR | cut -d '|' -f 2)
        FILE_USER=$(echo  $FILE_ATTR | cut -d '|' -f 3)
        FILE_GROUP=$(echo $FILE_ATTR | cut -d '|' -f 4)

        run torizoncore-builder-shell "ls -ldn $ROOTFS/$FILE_NAME"
        assert_success
        assert_output --partial "$FILE_NAME"
        assert_output --regexp "$FILE_MODE .* $FILE_USER $FILE_GROUP"
    done

    run torizoncore-builder-shell "ls -ldn $ROOTFS"'/usr/bin/file\ with\ space\ 1'
    assert_success
    assert_output --partial 'file with space 1'
    assert_output --regexp -rw------- .* 1000 1000

    run torizoncore-builder-shell "ls -ldn $ROOTFS"'/usr/bin/file\ with\ space\ 2'
    assert_success
    assert_output --partial 'file with space 2'
    assert_output --regexp -rw-rw---- .* 0 0
}

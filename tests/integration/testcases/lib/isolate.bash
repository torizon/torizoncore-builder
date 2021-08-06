#!/bin/bash

#
# Functions shared by the "isolate" test cases.
#


# Check if a ".tcattr" file was created after an "isolate" command has been issued
check-tcattr-file() {
    local IS_STORAGE="$1"
    local ISOLATE_DIR="$2"

    if [ "$IS_STORAGE" == "storage" ]
    then
        run torizoncore-builder-shell "ls $ISOLATE_DIR/usr/etc/.tcattr"
    else
        run ls $ISOLATE_DIR/usr/etc/.tcattr
    fi
    assert_success
    assert_output --partial "etc/.tcattr"
}

# Check if files were created after an "isolate" command has been issued
# and if they have the right ACLs applied based on the ".tcattr" file
check-isolated-files() {
    local IS_STORAGE="$1"
    local ISOLATE_DIR="$2"

    local FILE_ATTRS="file1|1000|2000|rw-|---|--- \
                      dir1|1000|0|rwx|---|--- \
                      dir1/file2|1000|0|rw-|rw-|--- \
                      dir1/file3|1000|2000|rw-|rw-|rw-"

    for FILE_ATTR in $FILE_ATTRS
    do
        FILE_NAME=$(echo $FILE_ATTR | cut -d '|' -f 1)
        FILE_USER=$(echo $FILE_ATTR | cut -d '|' -f 2)
        FILE_GROUP=$(echo $FILE_ATTR | cut -d '|' -f 3)
        FILE_PERM_USER=$(echo $FILE_ATTR | cut -d '|' -f 4)
        FILE_PERM_GROUP=$(echo $FILE_ATTR | cut -d '|' -f 5)
        FILE_PERM_OTHER=$(echo $FILE_ATTR | cut -d '|' -f 6)

        if [ "$IS_STORAGE" == "storage" ]
        then
            run torizoncore-builder-shell "grep -A6 -B1 '^# file: '$FILE_NAME'$' $ISOLATE_DIR/usr/etc/.tcattr"
        else
            run grep -A6 -B1 '^# file: '$FILE_NAME'$' $ISOLATE_DIR/usr/etc/.tcattr
        fi
        assert_success
        assert_output - <<__END__

# file: $FILE_NAME
# owner: $FILE_USER
# group: $FILE_GROUP
user::$FILE_PERM_USER
group::$FILE_PERM_GROUP
other::$FILE_PERM_OTHER

__END__
    done
}

# Create a symbolic link in the device so them can be isolated and checked
# later both, on the storage or using the --changes-directory parameter.
create-links-in-device() {
    device-shell-root "touch /etc/file.txt"
    device-shell-root "rm -f /etc/link-to-file.txt"
    device-shell-root "ln -s /etc/file.txt /etc/link-to-file.txt"
}

#!/bin/bash

#
# Functions shared by all test cases.
#

# Create files in the device so them can be isolated later
create-files-in-device() {
    local FILE_ATTRS="file1|F|0600|1000:2000 \
                      dir1|D|0700|1000:0 \
                      dir1/file2|F|0660|1000.0 \
                      dir1/file3|F|0666|1000.2000 "

    for FILE_ATTR in $FILE_ATTRS
    do
        FILE_NAME=$(echo $FILE_ATTR | cut -d '|' -f 1)
        FILE_TYPE=$(echo $FILE_ATTR | cut -d '|' -f 2)
        FILE_PERM=$(echo $FILE_ATTR | cut -d '|' -f 3)
        FILE_USER=$(echo $FILE_ATTR | cut -d '|' -f 4)

        if [ $FILE_TYPE == "F" ]
        then
            device-shell-root "touch /etc/$FILE_NAME"
        else
            device-shell-root "mkdir -p /etc/$FILE_NAME"
        fi
        device-shell-root "chmod $FILE_PERM /etc/$FILE_NAME"
        device-shell-root "chown $FILE_USER /etc/$FILE_NAME"
    done
}

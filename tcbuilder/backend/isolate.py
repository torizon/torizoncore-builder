import datetime
import os
import subprocess
import shlex
import re

import fabric

from tcbuilder.errors import OperationFailureError, TorizonCoreBuilderError
from tcbuilder.backend.ostree import OSTREE_WHITEOUT_PREFIX, OSTREE_OPAQUE_WHITEOUT_NAME
from tcbuilder.backend.common import resolve_remote_host, REMOTE_CMD_TIMEOUT

IGNORE_FILES = [
    'group-',
    'shadow-',
    'gshadow-',
    'hostname',
    'machine-id',
    'ipk-postinsts',
    'fw_env.conf',
    'docker/key.json',
    '.updated',
    '.pwd.lock',
    'ssh/ssh_host_rsa_key',
    'ssh/ssh_host_rsa_key.pub',
    'ssh/ssh_host_ecdsa_key',
    'ssh/ssh_host_ecdsa_key.pub',
    'ssh/ssh_host_ed25519_key',
    'ssh/ssh_host_ed25519_key.pub',
    'systemd/system/sysinit.target.wants/run-postinsts.service',
    'ostree/remotes.d/toradex-nightly.conf',
]
TAR_NAME = 'isolated_changes.tar'

NO_CHANGES = 0
CHANGES_CAPTURED = 1


def ignore_changes_deletion(change):
    # NOTE: this offset must match the output of `ostree admin config`:
    fname = change[5:]
    if not fname or fname in IGNORE_FILES:
        return False  # ignore file

    return True


def remove_tmp_dir(conn, tmp_dir_name):
    conn.run('rm -rf ' + tmp_dir_name, hide=True, timeout=REMOTE_CMD_TIMEOUT)


def check_path(path):
    return '/' if path.rsplit('/', 1)[0] == path else '/{}/'.format(
        path.rsplit('/', 1)[0])


def whiteouts(ssh_conn, sftp_channel, tmp_dir_name, deleted_f_d):
    # check if deleted file/dir was in subdirectory of /etc --> '/' for file/dir at /etc
    path = check_path(deleted_f_d)
    if path != '/':  # file/dir was in subdirectory of /etc
        # check if any file exists other than file/dir deleted in same subdirectory of /etc
        d_list = sftp_channel.listdir('/etc' + path)
        if not d_list:  # entire content(s) deleted
            deleted_file_dir_to_tar = 'etc' + path + OSTREE_OPAQUE_WHITEOUT_NAME
        else:
            deleted_file_dir_to_tar = 'etc' + path + OSTREE_WHITEOUT_PREFIX \
                                        + deleted_f_d.rsplit('/', 1)[1]
    else:
        deleted_file_dir_to_tar = 'etc' + path + OSTREE_WHITEOUT_PREFIX \
                                    + deleted_f_d

    # create deleted files/dir in torizonbuilder tmp directory with whiteout format
    create_deleted_info_cmd = 'mkdir -p {0}/{1} && touch {0}/{2}'.format(
        tmp_dir_name, deleted_file_dir_to_tar.rsplit('/', 1)[0],
        shlex.quote(deleted_file_dir_to_tar))
    result = ssh_conn.run(create_deleted_info_cmd, hide=True, timeout=REMOTE_CMD_TIMEOUT)
    if result.failed:
        raise OperationFailureError(
            f'Could not create dir in {tmp_dir_name}',
            result.stdout)


def get_tcattr_file_content(files_dir_to_tar, ssh_conn, tmp_dir_name):
    """
    Get the content (permission/ownership) for the "/etc/.tcattr"
    metadata file of all files that will be isolated and will be
    used later by the "union" command.
    """

    facl_command = "getfacl -n {0}".format(files_dir_to_tar)
    result = ssh_conn.sudo(facl_command, pty=True, hide=True, timeout=REMOTE_CMD_TIMEOUT)

    if result.failed:
        remove_tmp_dir(ssh_conn, tmp_dir_name)
        ssh_conn.close()
        facl_command_error = 'Unable to save permissions/ownership at target'
        raise OperationFailureError(facl_command_error, result.stdout.strip())

    tcattr = result.stdout.strip("\r").split("\r\n")
    # remove upto password keyword
    indx = tcattr.index("[sudo] password: ")
    tcattr = tcattr[(indx + 1):]

    # remove any getfacl warnings from the list
    tcattr = [e for e in tcattr if 'getfacl:' not in e]

    return tcattr


def create_tcattr_file(diff_dir, tcattr_list):
    """
        Create the {diff_dir}/usr/etc/.tcattr file using the content of
        tcattr buffer so it can be used later by the "union" command to
        set file and/or directory permissions and/or ownership.
    """

    # Replace any space characters in the file name with its 3-digit octal ASCII code (\040)
    # so that setfacl can properly include them when searching the file.
    _tcattr_list = ["# file: " + line[8:].replace(" ", "\\040") if line.startswith("# file: ")
                    else line for line in tcattr_list]

    tcattr_str = "\n".join(_tcattr_list)
    # Remove etc/ at the beginning of the file path
    tcattr_str = re.sub(r'^# file: etc/', '# file: ', tcattr_str, flags=re.MULTILINE)

    with open(f"{diff_dir}/usr/etc/.tcattr", "w") as fd_tcattr:
        fd_tcattr.write(tcattr_str)


def list_to_string_with_quote(args_list):
    """
        Insert quotes where needed so shell can read names with special characters.
        Also, transforms the list into a string
    """
    return r' '.join([shlex.quote(file) for file in args_list])


# pylint: disable=too-many-locals
def isolate_user_changes(diff_dir, r_name_ip, r_username, r_password, r_port, r_mdns):

    resolved_remote_host = resolve_remote_host(r_name_ip, r_mdns)
    conn = fabric.Connection(host=resolved_remote_host,
                             user=r_username,
                             port=r_port,
                             connect_kwargs={'password': r_password},
                             config=fabric.Config(overrides={'sudo': {'password': r_password}}))
    conn.open()
    # get config diff
    result = conn.sudo('ostree admin config-diff', pty=True, hide=True, timeout=REMOTE_CMD_TIMEOUT)

    # Check exit status
    if result.failed:
        conn.close()
        raise OperationFailureError('Unable to get user changes',
                                    result.stdout.strip())

    output = result.stdout.split("\r\n")
    # remove upto password keyword
    indx = output.index("[sudo] password: ")
    output = output[(indx + 1):]

    # filter out files
    changed_itr = filter(ignore_changes_deletion, output)
    changes = list(changed_itr)
    if not changes:
        return NO_CHANGES

    # Buffer to store the content for the ".tcattr" file
    tcattr = None

    sftp = conn.sftp()
    if sftp is not None:
        # perform all operations in /tmp
        tmp_dir_name = '/tmp/torizon-builder-' + str(datetime.datetime.now().date()) + '_' + str(
            datetime.datetime.now().time()).replace(':', '-')
        sftp.mkdir(tmp_dir_name)

        files_dir_to_tar = ''
        files_list = []
        f_delete_exists = False
        # append /etc because ostree config provides file/dir names relative to /etc
        for item in changes:
            f_name = item[5:]   # Sync with ignore_changes_deletion
            if item[0] != 'D':
                files_list.append('/etc/' + f_name)
            else:
                f_delete_exists = True
                whiteouts(conn, sftp, tmp_dir_name, f_name)

        files_dir_to_tar = list_to_string_with_quote(files_list)
        if f_delete_exists:
            tar_command = "tar --exclude={0} --xattrs --acls -cf {1}/{0} -C {1} . {2}". \
                format(TAR_NAME, tmp_dir_name, files_dir_to_tar)
        else:
            # don't include current directory i.e. '.':
            # whiteout files does not exist in /tmp/torizon-builder/
            tar_command = "tar --xattrs --acls -cf {1}/{0} {2}".format(
                TAR_NAME, tmp_dir_name, files_dir_to_tar)
        # make tar
        result = conn.sudo(tar_command, pty=True, hide=True, timeout=REMOTE_CMD_TIMEOUT)
        if result.failed:
            remove_tmp_dir(conn, tmp_dir_name)
            sftp.close()
            conn.close()
            raise OperationFailureError('Unable to bundle up changes at target',
                                        result.stdout.strip())

        # get the tar
        sftp.get(tmp_dir_name + '/' + TAR_NAME, diff_dir + '/' + TAR_NAME, None)
        remove_tmp_dir(conn, tmp_dir_name)
        sftp.close()

        tcattr = get_tcattr_file_content(files_dir_to_tar, conn, tmp_dir_name)
    else:
        conn.close()
        raise TorizonCoreBuilderError('Unable to create SSH connection for transferring of files')

    conn.close()

    # Extract tar to diff_dir/usr/ so that at time of union
    # they can be committed to /usr/etc of unpacked image as it is
    os.mkdir(os.path.join(diff_dir, "usr"))
    extract_tar_cmd = [
        "tar", "--acls", "--xattrs", "--overwrite", "--preserve-permissions", "-xf",
        os.path.join(diff_dir, TAR_NAME), "-C", os.path.join(diff_dir, "usr", "")
    ]
    subprocess.check_output(extract_tar_cmd, stderr=subprocess.STDOUT)

    create_tcattr_file(diff_dir, tcattr)

    os.remove(os.path.join(diff_dir, TAR_NAME))

    return CHANGES_CAPTURED
# pylint: enable=too-many-locals

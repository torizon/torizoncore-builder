import struct, os, unittest.mock
import guestfs
from tcbuilder.backend.deploy import grow_last_partition

SECTOR = 4096
img = "grow_lba_mock.img"
added_kb = 4 * 1024
orig_size = os.path.getsize(img)
expected_new_size = orig_size + added_kb * 1024
expected_new_size = (expected_new_size + SECTOR - 1) // SECTOR * SECTOR
# Deliberately not what the default-table reservation would give
# (5 sectors at this SECTOR size).
mock_end_sector = expected_new_size // SECTOR - 1 - 9
mock_header = b"EFI PART" + b"\0" * 40 + struct.pack("<Q", mock_end_sector)

with unittest.mock.patch("guestfs.GuestFS.pread_device", return_value=mock_header):
    grow_last_partition(img, added_kb, SECTOR, "/dev/sda1", delete_on_error=True)

g = guestfs.GuestFS(python_return_dict=True)
g.add_drive_opts(img, format="raw", blocksize=SECTOR)
g.launch()
grown = max(g.part_list("/dev/sda"), key=lambda p: p["part_start"])
actual_end = grown["part_end"] // SECTOR
g.shutdown()
g.close()

assert actual_end == mock_end_sector, f"expected {mock_end_sector}, got {actual_end}"
print("OK: grew to mocked LastUsableLBA sector", actual_end)

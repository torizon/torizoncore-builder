import os
import subprocess
import shutil
import tempfile
import logging
from tcbuilder.errors import OperationFailureError, PathNotExistError, TorizonCoreBuilderError

def build_and_apply(devicetree, overlays, devicetree_out, includepaths):
    """ Compile and apply several overlays to an input devicetree

        Args:
            devicetree (str) - input devicetree
            overlays (str) - list of devicetree overlays to apply
            devicetree_out (str) - the output devicetree(with overlays) applied
            includepaths (list) - list of additional include paths

        Raises:
            FileNotFoundError: invalid file name or build errors
    """
    if not os.path.isfile(devicetree):
        raise TorizonCoreBuilderError("Missing input devicetree")

    tempdir = tempfile.mkdtemp()
    if overlays is not None:
        dtbos = []
        for overlay in overlays:
            dtbo = tempdir + "/" + os.path.basename(overlay) + ".dtbo"
            build(overlay, dtbo, includepaths)
            dtbos.append(dtbo)

        apply_overlays(devicetree, dtbos, devicetree_out)
    else:
        build(devicetree, devicetree_out, includepaths)

    shutil.rmtree(tempdir)

def build(source_file, outputpath=None, includepaths=None):
    """ Compile a dtbs file into dtb or dtbo output

        Args:
            source_file (str) - path of source device tree/overlay file
            outputpath (str) - output file name/folder, if None then extension
                is appended to source file name, if it's a folder file with dtb/dtbo
                extension is created
            includepaths (list) - list of additional include paths

        Raises:
            FileNotFoundError: invalid file name or build errors
            OperationFailureError: failed to build the source_file
    """

    if not os.path.isfile(source_file):
        raise FileNotFoundError("Invalid source_file")

    ext = ".dtb"

    with open(source_file, "r") as f:
        for line in f:
            if "fragment@0" in line:
                ext = ".dtbo"
                break
    if outputpath is None:
        outputpath = "./" + os.path.basename(source_file) + ext

    if os.path.isdir(outputpath):
        outputpath = os.path.join(
            outputpath, os.path.basename(source_file) + ext)


    cppcmdline = ["cpp", "-nostdinc", "-undef", "-x", "assembler-with-cpp"]
    dtccmdline = ["dtc", "-@", "-I", "dts", "-O", "dtb"]

    if includepaths is not None:
        if type(includepaths) is list:
            for path in includepaths:
                dtccmdline.append("-i")
                dtccmdline.append(path)
                cppcmdline.append("-I")
                cppcmdline.append(path)
        else:
            raise OperationFailureError("Please provide include paths as list")

    tmppath = source_file+".tmp"

    dtccmdline += ["-o", outputpath, tmppath]
    cppcmdline += ["-o", tmppath, source_file]

    cppprocess = subprocess.run(
        cppcmdline, stderr=subprocess.PIPE, check=False)

    if cppprocess.returncode != 0:
        raise OperationFailureError("Failed to preprocess device tree.\n" +
                        cppprocess.stderr.decode("utf-8"))

    dtcprocess = subprocess.run(
        dtccmdline, stderr=subprocess.PIPE, check=False)

    if dtcprocess.returncode != 0:
        raise OperationFailureError("Failed to build device tree.\n" +
                    dtcprocess.stderr.decode("utf-8"))

    os.remove(tmppath)

def apply_overlays(devicetree, overlays, devicetree_out):
    """ Verifies that a compiled overlay is valid for the base device tree

        Args:
            devicetree (str) - path to the binary input device tree
            overlays (str,list) - list of overlays to apply
            devicetree_out (str) - input device tree with overlays applied

        Raises:
            OperationFailureError - fdtoverlay returned an error
    """

    if not os.path.exists(devicetree):
        raise PathNotExistError("Invalid input devicetree")

    fdtoverlay_args = ["fdtoverlay", "-i", devicetree, "-o", devicetree_out]
    if type(overlays) == list:
        fdtoverlay_args.extend(overlays)
    else:
        fdtoverlay_args.append(overlays)

    fdtoverlay = subprocess.run(fdtoverlay_args,
                                stderr=subprocess.PIPE,
                                check=False)
    # For some reason fdtoverlay returns 0 even if it fails
    if fdtoverlay.stderr != b'':
        raise OperationFailureError(f"fdtoverlay failed with: {fdtoverlay.stderr.decode()}")

    logging.info("Successfully applied device tree overlay")

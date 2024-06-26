
Introduction
============

TorizonCore Builder (TCB) is a CLI tool that enables customizations on a Torizon OS image in an easy way, without the need to rebuild the OS from scratch. Many aspects of the the image can be customized, which include:

- Changing the splash screen;
- Modifying configuration files in `/etc`;
- Adding Device Trees and adding/removing Device Tree Overlays;
- Combining Docker images into the OS;
- Building and including out-of-tree kernel modules from source;
- Including new kernel parameters, etc.

The end result is a custom Torizon OS image prepared for production programming.

TCB also has integration with Torizon Cloud, our OTA platform which is part of the [Torizon Ecosystem](https://www.torizon.io/): You can use TCB to directly upload custom OS images to the Cloud servers.

To learn more about the tool please refer to the [TorizonCore Builder Commands Manual page](https://developer.toradex.com/torizoncore-builder-commands-manual) available at the Toradex Developer website.

The TCB source code is licensed under the GPLv3. You can find the license [here](LICENSE.md).


Supported Platforms
===================
TorizonCore Builder is officially supported for x64 Linux systems and on x64 Windows 10/11 through WSL2. On both options, the supported shell is Bash.


Prerequisites
=============

Before beginning the setup process, please make sure your system has the following programs installed:

- Docker Engine or Docker Desktop
- Curl


Getting Started
===============

## Setup

Create a dedicated directory for TCB and in it download the setup script:

```
mkdir -p $TCBDIR && cd $TCBDIR
wget https://raw.githubusercontent.com/toradex/tcb-env-setup/master/tcb-env-setup.sh
```

Source the script and accept the online update check:

```
source tcb-env-setup.sh
```

The command `torizoncore-builder` should be available in your terminal session. Inside $TCBDIR create a `tcbuild.yaml` template with:

```
torizoncore-builder build --create-template
```

All customization features available on TCB can be described in a `tcbuild.yaml` file, which can then be read by TCB when running:

```
torizoncore-builder build
```

The template has comments that give a general overview on the `tcbuild.yaml` syntax and how each option should be filled. For more details about them check the manual page linked above.

## Simple customization example

This section is heavily based on this article from the Toradex Developer website:

https://developer.toradex.com/torizon/os-customization/use-cases/splash-screen-on-torizoncore/

This example shows how to create a Torizon OS image with a custom Plymouth splash screen, starting from a Toradex-provided Torizon OS image.

Download the latest quarterly release of Torizon OS (with no containers pre-provisioned) for your Toradex SoM at:

https://developer.toradex.com/software/toradex-embedded-software/toradex-download-links-torizon-linux-bsp-wince-and-partner-demos/

and save the tar file inside $TCBDIR e.g. in `$TCBDIR/images/`.

Choose a PNG image to use as the new splash screen and copy it to $TCBDIR, then modify the contents of `tcbuild.yaml` to be similar to this:

```
input:
  easy-installer:
    local: images/$INPUT_IMAGE
customization:
  splash-screen: $SPLASH_SCREEN_PNG
output:
  easy-installer:
    local: $OUTPUT_IMAGE
```

Replace:

- $INPUT_IMAGE with the tar file of the input Torizon OS image;
- $SPLASH_SCREEN_PNG with the filename of the PNG image to be the new splash screen;
- $OUTPUT_IMAGE with a user-defined directory name inside $TCBDIR. This is where the final image will be located.

As an example, a `tcbuild.yaml` file doing this customization to a Torizon OS image for the Apalis i.MX6 SoM should look like this:

```
input:
  easy-installer:
    local: images/torizon-core-docker-apalis-imx6-Tezi_6.6.1+build.14.tar
customization:
  splash-screen: splash.png
output:
  easy-installer:
    local: tcb_dir_apalis_imx6_custom_splash
```

Run the command below to apply everything specified in `tcbuild.yaml`:

```
torizoncore-builder build
```

On a successful run an OSTree commit ref associated with the custom image will be displayed on the terminal:

```
[..]
=>> Handling output section
Applying changes from STORAGE/splash.
Commit a84d7994dbcb170da456621e733d7f0fa786042fbb7f580bba1e181e39cc442b has been generated for changes and is ready to be deployed.
Deploying commit ref: tcbuilder-20240627135407
Pulling OSTree with ref tcbuilder-20240627135407 from local archive repository...
  Commit checksum: a84d7994dbcb170da456621e733d7f0fa786042fbb7f580bba1e181e39cc442b
  TorizonCore Version: 6.6.1+build.14-tcbuilder.20240627135407
  Default kernel arguments: quiet logo.nologo vt.global_cursor_default=0 plymouth.ignore-serial-consoles splash fbcon=map:3
[...]
```

The commit ref from the example above is `tcbuilder-20240627135407`. Take note of your ref as it may be necessary for the next step.

## Installing the generated Torizon OS image

To install the customized image, use one of the methods below. For more details on each one, see:

https://developer.toradex.com/torizon/os-customization/use-cases/splash-screen-on-torizoncore/#deploy-the-custom-toradex-easy-installer-image

### Recommended for development

***Important: This method is an OSTree-only update, meaning that any bundled container images in the customized OS image will not be installed.***

Load the customized image with:

```
torizoncore-builder images unpack $OUTPUT_IMAGE
```

Where $OUTPUT_IMAGE is the output directory of the `build` command. then run:

```
torizoncore-builder deploy --reboot --remote-host "$SOM_IP" --remote-username "$TORIZON_USER" --remote-password "$TORIZON_PASS" "$COMMIT_REF"
```

to directly install it to a SoM connected on the local network. Replace:

- $SOM_IP with the local IP address of the SoM;
- $TORIZON_USER with a Torizon OS user (default is `torizon`);
- $TORIZON_PASS with the corresponding user password;
- $COMMIT_REF with the OSTree commit ref of the output image.


### Recommended for production

Copy the output directory to a USB storage device and install it using [Toradex Easy Installer](https://developer.toradex.com/easy-installer/toradex-easy-installer/loading-toradex-easy-installer/).


### Recommended for devices in the field

Perform an OTA update if the devices are registered on Torizon Cloud.


Reporting Issues
================

If you find any problems when using TorizonCore Builder, feel free to open a new issue here on GitHub or create a new Technical Support topic on the Toradex Developer Community: https://community.toradex.com/.


Contributing
============

You may also choose to actively correct issues/bugs or possibly add new features by contributing code to TCB. For more details, see [CONTRIBUTING.md](CONTRIBUTING.md).


Development Process
===================

TorizonCore Builder is maintained by the Toradex R&D team. Currently this GitHub repo is a mirror of an internal GitLab repository only accessible to members of the team, where most of the development happens.

We're currently working on opening development to GitHub, where discussions, pull requests and issues can be made public more easily. This section will be updated once the opening process finishes.


Introduction
============

TorizonCore Builder is a tool that enables customizations on a TorizonCore image in an easy way. Almost all aspects of the the image can be customized, including the splash screen, configuration files, device trees and overlays, out-of-tree kernel modules, kernel parameters, etc. The end result is a custom TorizonCore image prepared for production programming. To learn more about the tool and how to get started, please refer to [TorizonCore Builder Commands Manual page](https://developer.toradex.com/torizoncore-builder-commands-manual).

TorizonCore Builder source code is licensed under GPLv3, you can find the license file [here](gpl-30.md)

In the next sections we describe some independent procedures that a developer working on **TorizonCore Builder** may like to follow.


Install Git Hooks (after cloning the repo)
==========================================

The directory `hooks` has some simple scripts that may be installed as local Git hooks for your cloned repository. To install them, simply run in the top directory of the repo:

```
$ ./hooks/set_hooks.sh
```

At the time of this writing, we have just a `post-commit` script that helps the developer remembering to run the linter on the code (by showing a message on every commit).


Building and running the Docker image of the tool
=================================================

TorizonCore Builder runs in a container. To build that container image, run in the top directory of the repo:

```
$ docker build -f torizoncore-builder.Dockerfile -t torizoncore-builder:local .
```

Now to run the actual tool, you can set an alias such as this:

```
$ alias torizoncore-builder='docker run --rm -it -v /deploy -v $(pwd):/workdir -v storage:/storage -v /var/run/docker.sock:/var/run/docker.sock --net=host torizoncore-builder:local'
```

If you run into problems, take a look at the normal setup script provided by Toradex to end users. See the instructions to fetch that script here:

- https://developer.toradex.com/knowledge-base/torizoncore-builder-tool#Setup_Script

You could run the tool's setup script and modify the alias `torizoncore-builder` to reference your locally build image (tagged torizoncore-builder:local)


Building the development Docker image<a name="build-dev-image"></a>
=====================================

The development image provides some tools for testing TorizonCore Builder
itself. To build the dev image, run in the top directory of the repo:

```
$ docker build -f torizoncore-builder.Dockerfile --target tcbuilder-dev -t torizoncore-builder-dev:local .
```

An then set an alias like this:

```
$ alias torizoncore-tools='docker run --rm -it -v /deploy -v $(pwd):/workdir -v storage:/storage --net=host -v /var/run/docker.sock:/var/run/docker.sock torizoncore-builder-dev:local'
```

Testing changes to Python code without rebuilding
=================================================
To just test changes to the Python code, you can mount the source
directory directly into the container using a docker volume mount. This
can be done using the regular tcb-env-setup.sh as follows:

```
$ tcb-env-setup.sh -- --volume /path/to/torizoncore-builder:/builder:ro --entrypoint torizoncore-builder.py
```

This also changes the entrypoint, because the file has a .py extension
in the repository which is removed when building the docker image.

Running the linter (static analysis tool)
=========================================

To run the linter you need to build development image first (see section [Building the development Docker image](#build-dev-image)). After that, you can run `pylint` like this:

```
$ torizoncore-tools bash -c 'cd /workdir && pylint -ry --output-format=colorized $(find tcbuilder/ -type f -name "*.py") *.py'
```

The above command will show all warnings (as configured in the `.pylintrc` file). Not all of them will cause pipeline failures when your local changes are pushed to GitLab but the developer is encouraged to fix all of them. In CI we run just the same command except that we disable the warnings related to docstrings.

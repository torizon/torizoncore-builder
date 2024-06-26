# How to Contribute

This document details guidelines and common practices which should be followed when contributing code to this repository, whether the person is part of the TCB team or an external contributor.

Here you can also find a general overview on how the code is organized.

## Code Contributor Workflow

- Make a fork of this repository;
- Create a new development branch in it;
- Make your changes in the new branch and commit them;
- Open a pull request to the default branch (currently `bullseye`).

When a PR is opened, updated or reopened, our test pipeline is automatically executed on it if there are no merge conflicts.

For most PRs all tests in the pipeline should pass before the TorizonCore Builder team starts the review process. Exceptions can be made by the TCB team, but it's on a case-by-case scenario.

## Commit Guidelines

All commits must be signed-off i.e. have a 'Signed-off-by' line at the end of their messages, similar to this example:

```
Update README.md

Signed-off-by: Your Name <your-e-mail@your-provider.com>
```

This line can be added automatically with the `-s` option of `git commit`. It certifies the authorship of your own commit or that you have the right to pass it under the same license of this repository, as stated in https://developercertificate.org/ .

Commit messages should generally follow the format below:

```
scope: Brief one line description with up to 72 characters

[optional] Detailed description, with multiple lines. Each one should
have up to 72 characters.

Signed-off-by: Your Name <your-e-mail@your-provider.com>
```

`scope` can be a specific file being changed (e.g. `requirements.txt`, `tcbuild.schema.yaml`) or a part of the code related to a command, such as `backend/platform` or `cli/deploy`.

The first line can also be a single sentence, usually starting with a verb in the imperative present tense, that describes a general change to the code if dealing with multiple files e.g.

```
Show spinner loading animation when processing raw images
```

Or if simple changes are done to a single file e.g:

```
Add README.md
```


# Getting started with the development process

TorizonCore Builder is a series of Python scripts that run inside a Docker container. In practice this means that the actual `torizoncore-builder` CLI command that becomes available after sourcing `tcb-env-setup.sh` is, in fact, an alias to a `docker run` command that executes `torizoncore-builder.py`.

In the following sections we describe some independent procedures that a developer working on **TorizonCore Builder** may wish to follow.

## Install Git Hooks (after cloning the repo)

The directory `hooks` has some simple scripts that may be installed as local Git hooks for your cloned repository. To install them, simply run in the top directory of the repo:

```
./hooks/set_hooks.sh
```

At the time of this writing, we have just a `post-commit` script that helps the developer remember to run the linter on the code (by showing a message on the terminal after every commit).

## Building and running the Docker image of the tool

TorizonCore Builder runs in a container. To build this container image, run in the top directory of the repo:

```
docker build -f torizoncore-builder.Dockerfile -t torizoncore-builder:local .
```

Now to execute the actual tool, you can set an alias such as this:

```
alias torizoncore-builder='docker run --rm -it -v /deploy -v $(pwd):/workdir -v storage:/storage -v /var/run/docker.sock:/var/run/docker.sock --net=host torizoncore-builder:local'
```

If you run into problems, take a look at the normal setup script provided by Toradex to end users. See the instructions to fetch that script here:

- https://developer.toradex.com/knowledge-base/torizoncore-builder-tool#Setup_Script

You could run the tool's setup script and modify the alias `torizoncore-builder` to reference your locally built image (tagged torizoncore-builder:local)

## Building the development Docker image<a name="build-dev-image"></a>

The development image provides some tools for testing TorizonCore Builder
itself. To build the dev image, run in the top directory of the repo:

```
docker build -f torizoncore-builder.Dockerfile --target tcbuilder-dev -t torizoncore-builder-dev:local .
```

An then set an alias like this:

```
alias torizoncore-tools='docker run --rm -it -v /deploy -v $(pwd):/workdir -v storage:/storage --net=host -v /var/run/docker.sock:/var/run/docker.sock torizoncore-builder-dev:local'
```

## Running the linter (static analysis tool)

To run the linter you need to build the development image first (see section [Building the development Docker image](#build-dev-image)). After that, you can run `pylint` like this:

```
torizoncore-tools bash -c 'cd /workdir && pylint -ry --output-format=colorized $(find tcbuilder/ -type f -name "*.py") *.py'
```

The above command will show all warnings (as configured in the `.pylintrc` file). Not all of them will cause pipeline failures when your local changes are pushed to GitHub but the developer is encouraged to fix all of them. In CI we run the same command except that we disable the warnings related to docstrings.


# General Code Organization

- `torizoncore-builder.Dockerfile`: Dockerfile that builds the TCB container image.

- `torizoncore-builder.py`: Python file that is the entry point for the TorizonCore Builder command. If a TCB sub-command is used it calls the corresponding CLI .py file.

- `tcbuilder/`: Directory that has most Python scripts that make up the tool. In it most files are grouped into two directories:

  - `tcbuilder/cli/`: Has code related to CLI tasks e.g. parsing arguments, checking if provided input is valid, etc. In it each TCB sub-command has a corresponding .py file. These files serve as an interface between the backend files and the user input/output.

  - `tcbuilder/backend/`: Does the heavy lifting of the tool i.e. it has the logic that actually performs the sub-commands requested by their `cli` counterparts.

- `tezi/`: Directory with auxiliary Python functions to manipulate OS images in the Toradex Easy Installer format (TEZI).

- `tests/`: Directory that has all test-related content, including automated tests. For more details, see [tests/integration/README](tests/integration/README).


# Overview

This directory contains compose files used for testing Lockbox generation with
TorizonCore Builder.

Currently, the tests assume that these files have been previously pushed and the
corresponding Lockboxes have been created on the platform.

The names of the Lockboxes follow the pattern:

`lockbox-with-<compose-name-without-extension>`

where the `<compose-name-without-extension>` is the name of a canonical package
on the platform. For example, the file `docker-compose-lkbx-32bit.yml` would be
pushed to the plaform in canonical form with the name
`docker-compose-lkbx-32bit.lock.yml` and that file should be included in the
Lockbox named `lockbox-with-docker-compose-lkbx-32bit`.

To push all compose files in the current folder one can run:

```
$ . <path-to-tcb-env-setup-script>
$ . push-lockbox-compose-files.sh <credentials-file-for-account>
```

After that, one can create the corresponding Lockboxes, which currently must be
done manually through the platform web UI.

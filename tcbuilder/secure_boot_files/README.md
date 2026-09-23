# Support files for the secboot commands

Signing helper scripts and templates used by `torizoncore-builder secboot`, plus one key.

## `ti-degenerate-key.pem`

TI's *degenerate* signing key for K3 SoCs. It is a published constant, the same file for everyone,
and it is not secret: the certificates it produces carry no security property. It exists because the
boot ROM of GP silicon expects a signed container while verifying nothing, so TI ships a key whose
signature is a formality.

`secboot sign-bootloader-k3` uses it for the artifacts a Torizon OS build also signs with it:
`tiboot3-am62x-gp-verdin.bin` and the `tifsstub-gp` subimage inside `tispl.bin`. Everything else is
signed with the customer key passed to `--k3-key`. Signing these two with anything else would
produce different bytes than the OS build does, for no gain.

- Origin: `core-secdev-k3` from TI,
  `git://git.ti.com/git/security-development-tools/core-secdev-k3.git`, packaged by `meta-ti` as
  `ti-k3-secdev-native` at SRCREV `ed6951fd3877c6cac7f1237311f7278ac21634f3`.  Licence BSD-3-Clause.
- This copy is byte-identical to the one that package installs at
  `usr/share/ti/ti-k3-secdev/keys/ti-degenerate-key.pem`, sha256
  `ba232085efab23c6a926879dbfdbc1e7054894eff50f19ae60cbd5c38264a976`.
- Upstream U-Boot does not carry it; a Torizon OS build reaches it through
  `TDX_K3_SECBOOT_KEY_DIR`. A build that replaced the key there produces containers this copy cannot
  reproduce, which is what `--k3-degenerate-key` is for.

Do not add customer or test signing keys to this directory. Test key material belongs under
`tests/integration/samples/signing_keys`.

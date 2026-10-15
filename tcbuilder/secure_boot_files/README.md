# Support files for the secboot commands

Signing helper scripts and templates used by `torizoncore-builder secboot`, plus one key.

## `ti-degenerate-key.pem`

TI's *degenerate* signing key for K3 SoCs. It is a published constant, the same file for everyone,
and it is not secret: the certificates it produces carry no security property. It exists because the
boot ROM of GP silicon expects a signed container while verifying nothing, so TI ships a key whose
signature is a formality.

`secboot sign-bootloader-k3` stages it into every signing root, because the K3 binman descriptors
declare a `ti-degenerate-key` image whose file must exist, whatever the SoC. What it signs depends
on the SoC:

- AM62 (`verdin-am62`): the artifacts a Torizon OS build also signs with it,
  `tiboot3-am62x-gp-verdin.bin` and the `tifsstub-gp` subimage inside `tispl.bin`. Signing these two
  with anything else would produce different bytes than the OS build does, for no gain.
- AM62P (`verdin-am62p`): nothing. TI ships no GP firmware for this SoC, so there is no GP container
  and no `tifsstub-gp`.

Everything else is signed with the customer key passed to `--k3-key`.

- Origin: `keys/ti-degenerate-key.pem` in `core-secdev-k3` from TI,
  `git://git.ti.com/git/security-development-tools/core-secdev-k3.git`, at commit
  `ed6951fd3877c6cac7f1237311f7278ac21634f3` (the SRCREV `meta-ti` uses for `ti-k3-secdev-native`).
  Licence BSD-3-Clause, as declared by `meta-ti`'s recipe (the repository has no licence file).
  Upstream U-Boot carries the same file as
  `arch/arm/mach-k3/keys/ti-degenerate-key.pem`.
- RSA 1024-bit, PKCS#1 PEM, sha256
  `99768f6042bc3f8198f9aa8291bed2716b4ebfc5a3513189570a1e8bbe39d98a`. Do not take the file from a
  Torizon OS build's `ti-k3-secdev-native` sysroot: `meta-toradex-security` replaces that package's
  `keys` directory with `TDX_K3_SECBOOT_KEY_DIR`, so the sysroot holds the build's own key set.
- A build whose key directory holds a different degenerate key produces GP artifacts this copy
  cannot reproduce, which is what `--k3-degenerate-key` is for.

Do not add customer or test signing keys to this directory. Test key material belongs under
`tests/integration/samples/signing_keys`.

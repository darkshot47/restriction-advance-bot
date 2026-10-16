# The update signing key

Android installs an APK over an existing app **only when both carry the same
signature**.  Signing every build with Android's debug key — which is what the
workflow used to do — meant a different signature on every build, because a CI
runner generates its debug keystore from scratch each time.  Every update then
ended in `App not installed`, which is the bug this folder exists to prevent.

## What lives here

| file | what it is |
| --- | --- |
| `vmore.jks` | the RSA 4096 key that signs every release APK |
| `storepass.txt` | line 1: the keystore and key password, line 2: the alias |

Both are committed on purpose.  A GitHub repository secret would be the tidier
home for a signing key, but secrets cannot be written by the build itself, and
a key that cannot be recreated means every future update breaks the moment it is
lost.  The alternative — regenerating the key — is exactly the failure this
folder fixes, so the key is kept where the build can always reach it.

## What that means, honestly

Anyone who can read this repository can produce an APK that Android would accept
as an update to an installed Vmore.  That is a phishing risk, not a remote one:
the app is installed from this repository's releases, and a fake would have to be
handed to the owner directly.  To make that verifiable anyway:

* `android/tools/expected_signing.txt` records the certificate fingerprint, and
  the build **fails** if an APK is signed with anything else;
* the app shows the fingerprint of the build that is actually installed
  (Settings → Check the Telegram connection), and every release carries the same
  value in its notes — so the installed app can be compared with the release it
  claims to be.

## Rotating

Replace `vmore.jks` and `storepass.txt`, write the new fingerprint into
`android/tools/expected_signing.txt`, and remember: after a rotation every
installed copy has to be uninstalled once, because Android will not accept an
update signed with the new key over an app signed with the old one.

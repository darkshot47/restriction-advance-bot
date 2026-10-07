# Vmore icons (SVG sources)

The app draws every icon from a vector so the APK carries no bitmaps and the look
stays crisp on any screen density.

Android renders these as **VectorDrawable** XML: each `.svg` here has an exact
twin in `app/src/main/res/drawable/ic_*.xml` (same paths, same colours).  Keep the
two in sync — the SVG is what a designer edits, the drawable is what the build
ships.

| SVG | Drawable | Where it shows |
| --- | --- | --- |
| `vmore.svg` | `ic_vmore.xml` | launcher icon, header |
| `download.svg` | `ic_download.xml` | download button, notification |
| `pause.svg` | `ic_pause.xml` | pause button |
| `play.svg` | `ic_play.xml` | resume / preview |
| `stop.svg` | `ic_stop.xml` | stop button |
| `edit.svg` | `ic_edit.xml` | editor |
| `trim.svg` | `ic_trim.xml` | front/back trim |
| `image.svg` | `ic_image.xml` | thumbnail tools |
| `upload.svg` | `ic_upload.xml` | upload |
| `save.svg` | `ic_save.xml` | save to device |
| `history.svg` | `ic_history.xml` | downloads + history |
| `settings.svg` | `ic_settings.xml` | settings |
| `help.svg` | `ic_help.xml` | how to use |
| `owner.svg` | `ic_owner.xml` | owner profile in the corner |
| `token.svg` | `ic_token.xml` | access token |
| `link.svg` | `ic_link.xml` | link field |

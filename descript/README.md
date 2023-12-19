![](../ffmpeg-build-script.png)

# Build FFmpeg for Descript

## Author / Contact:
  - [Charles Van Winkle](https://github.com/cvanwinkle)
  - [Steve Rubin](https://github.com/srubin) 

## Instructions
- Run `build-ffmpeg-descript.py`


## Build Overview
The build script automates the following basic operations.
- Creates a log file to archive the compiler/linker and packaging steps
- Runs the modified `buildFFmpeg` shell script, outputs to log file
- Recursively generates or copies `.dSYM` symbol files for each dependency into a `.zip` file
  - Also fixes `dlyd` loader paths for each dependency
- Checks that each executable (i.e. `ffmpeg` & `ffprobe`) are runnable
- Copies `includes` header folder
- Checks for any linked dependencies which are linked to locations on the build machine and not present in the archive bundle
- Archives the upstream tar bundles for each `ffmpeg` component
  - This is important in case upstream FTP or source servers go offline in the future
- Generates checksum for each created artifact (build, symbols, packages, log)
 
## Development
Known issues:
- CI can only build `x86_64` and doesn't yet cross-compile to `arm64`
- When running on CI, there's libraries linked from `/usr/local/opt/...` which are non-portable
  - Watch the script output at the end for warnings about this. These could turn into errors later.

## Patches
- The build-ffmpeg shell script is modified directly to allow for
  - building shared libraries
  - disable non-free codecs
  - add additional codecs that Descript uses

## Deployment / Releases
- Currently, the script is run manually on a developer's machine
  - once for each platform (`x86_64` and `arm64`)
- Build artifacts (`*.zip` files) are manually uploaded to a GitHub release and tagged
- `SHAMSUM256.txt` files need to be merged between the two platforms when adding to a release.

## Clients
- This build is consumed by Descript's Beamcoder fork
  - https://github.com/descriptinc/beamcoder

## Previous Documentation of targeted differences (prior to `arm64` port)
- ❌ don't need 
- ✅ already in ffmpeg-build-script build
- 🕒 need to add to ffmpeg-build-script

Target (`evermeet.cx` static build)
- `--cc=/usr/bin/clang`
- `--prefix=/opt/ffmpeg`
- `--extra-version=tessus`
- ❌ `--enable-avisynth` - non-linear editing
- ❌ `--enable-fontconfig`
- ✅ `--enable-gpl`
- ✅ `--enable-libaom`
- ❌ `--enable-libass`
- ❌ `--enable-libbluray` - bluray playback
- 🕒✅ `--enable-libdav1d`
- ❌ `--enable-libfreetype` - text rendering
- ❌ `--enable-libgsm` - GSM audio
- ❌ `--enable-libmodplug` - midi/instrument support (https://github.com/Konstanty/libmodplug)
- ✅ `--enable-libmp3lame`
- ❌ `--enable-libmysofa` - spatial audio
- ✅ `--enable-libopencore-amrnb`
- ✅ `--enable-libopencore-amrwb`
- 🕒✅ `--enable-libopenh264`
- 🕒✅ `--enable-libopenjpeg`
- ✅ `--enable-libopus`
- ❌ `--enable-librubberband` - time stretching
- 🕒✅ `--enable-libshine` - mp3 encoder
- 🕒✅ `--enable-libsnappy` - compression/decompression
- 🕒✅ `--enable-libsoxr` - resampling
- 🕒✅ `--enable-libspeex` - speex audio file format
- ✅ `--enable-libtheora`
- 🕒✅ `--enable-libtwolame` - mpeg2
- ✅ `--enable-libvidstab`
- ❌ `--enable-libvmaf` - perceptual video quality metric
- ❌ `--enable-libvo-amrwbenc` - VisualOn AMR-WB encoder library
- ✅ `--enable-libvorbis`
- ✅ `--enable-libvpx`
- ✅ `--enable-libwebp`
- ✅ `--enable-libx264`
- ✅ `--enable-libx265`
- ❌ `--enable-libxavs` - AV standard of China
- ✅ `--enable-libxvid`
- 🕒✅ `--enable-libzimg` - Scaling, colorspace conversion, and dithering library
- ❌ `--enable-libzmq` - ZeroMQ Support To Let Multiple Clients Connect To A Single Instance (streaming)
- ❌ `--enable-libzvbi` - capture and decode VBI (vertical blanking interval) data
- ✅ `--enable-version3`
- `--pkg-config-flags=--static`
- `--disable-ffplay`

# Building From Source

## Prerequisites

- Python 3.12 or higher, and [uv](https://docs.astral.sh/uv/)
- Other dependencies are in `pyproject.toml` and are installed automatically by the build scripts below
- A C compiler for Nuitka, which compiles the app

#### macOS

- Xcode Command Line Tools (`xcode-select --install`)
- macOS 14 or newer (the Qt 6.12 wheels need it)

#### Linux

- `build-essential` and `patchelf` (`sudo apt install build-essential patchelf` on Ubuntu-based distributions)

#### Windows

- A C++ compiler for Nuitka (it will offer to download MinGW if you don't have one)

## Running From Source

```sh
uv sync
uv run jv-studio       # or: uv run python -m jv_studio
uv run pytest          # the tests (they run on Qt's offscreen platform and never touch a MIDI port)
```

## Setup and Build

1. Clone the repository
2. Run the script for your platform (in `scripts/`). The first time on Windows, PowerShell will warn about running a script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` fixes it. On Linux or macOS you may need `chmod +x scripts/build_xxx.sh`
3. The build lands in `src/` (`JV-Studio.app` on macOS, `JV-Studio.dist` on Linux and Windows)

Each script syncs the environment, writes the version from the nearest git tag into `src/jv_studio/_build_version.py` (not tracked), generates `src/pysidedeploy.spec` (not tracked) and runs `pyside6-deploy`. The built app contains the parameter and wave-name tables, the stylesheet template, the icons and cabling diagrams, and `LICENSE`.

To check a finished build without opening it, run its executable with `--smoke-test`. It checks the bundled data files, that Qt's SVG support and python-rtmidi are present, and that the main window and all five editor pages build, then exits 0 (or 1 with a report of what's missing). It never touches your settings or a MIDI port. CI does this for every platform.

```
QT_QPA_PLATFORM=offscreen src/JV-Studio.app/Contents/MacOS/main --smoke-test=report.txt
```

## Icons

`assets/icon/icon_1024x1024.png` is the master: 1024x1024, already in macOS icon form (rounded square about 824px wide, centred, soft shadow, transparent corners). `scripts/make_icons.sh` (macOS only) makes the two derived icons from it, `icon_512x512.png` (Linux AppImage and the Windows exe/installer) and `jv-studio-macos.icns` (all ten sizes). `icon_source.png` is the plain full-bleed square the master was made from.

## CI

- `.github/workflows/test.yml`: the tests, on every push to `master` and every pull request.
- `.github/workflows/build.yml`: on a `v*.*.*` tag (or by hand): the tests, then the macOS (Apple Silicon and Intel), Linux (AppImage) and Windows (installer) builds, each smoke-tested, then a **draft** GitHub release with all four.
- `.github/workflows/update-homebrew-tap.yml`: when a release is **published**, bumps `Casks/jv-studio.rb` in the tap (`martincurkovic/homebrew-tap`). It needs a repository secret `TAP_REPO_TOKEN`: a fine-grained token with Contents read and write on that one repository.

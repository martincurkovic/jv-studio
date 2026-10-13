from importlib import metadata

try:
    from jv_studio._build_version import APP_VERSION  # written by scripts/build_* from the git tag; not tracked
except ImportError:
    try:
        APP_VERSION = metadata.version("jv-studio")
    except metadata.PackageNotFoundError:  # running from a source tree that was never installed
        APP_VERSION = "0.0.0-dev"

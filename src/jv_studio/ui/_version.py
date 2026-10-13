from importlib import metadata

try:
    APP_VERSION = metadata.version("jv-studio")
except metadata.PackageNotFoundError:  # running from a source tree that was never installed
    APP_VERSION = "0.0.0-dev"

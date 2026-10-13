"""Text for the MIDI loopback test: what the results window shows and what a user can share. Pure functions (no Qt, no MIDI).

`results` is the list of `(byte_count, passed, detail)` tuples the loopback test produces."""

import platform
from urllib.parse import quote

#: where "Share on GitHub" opens a new issue; None until the project has a public repository (the button is then left out)
ISSUES_URL = None


def describe_os():
    system = platform.system()
    if system == "Darwin":
        version = platform.mac_ver()[0]
        return f"macOS {version}" if version else "macOS"
    if system == "Linux":
        try:
            return platform.freedesktop_os_release().get("PRETTY_NAME") or "Linux"
        except OSError:
            return "Linux"
    return platform.platform() or system or "Unknown"


def _port_text(input_name, output_name):
    if input_name == output_name:
        return [f"MIDI interface: {input_name}"]
    return [f"MIDI input: {input_name}", f"MIDI output: {output_name}"]


def header_lines(input_name, output_name, os_name, app_version):
    return [*_port_text(input_name, output_name), f"Operating system: {os_name}", f"JV Studio version: {app_version}"]


def result_lines(results):
    return [f"{size:>5} bytes: {'PASS' if passed else 'FAIL'}" + ("" if passed else f" - {detail}") for size, passed, detail in results]


def verdict(results):
    failed = [size for size, passed, _ in results if not passed]
    if not failed:
        return "All sizes tested passed cleanly."
    return (
        f"This interface starts failing around {failed[0]} bytes. "
        "A JV-1010 patch tone is 129 bytes and a whole bank dump is far larger, so if failures start below about 256 bytes "
        "this interface may struggle with real transfers too."
    )


def report_text(results, input_name, output_name, os_name, app_version):
    """Everything worth sending, as plain text (header, per-size results, verdict)."""
    return "\n".join([*header_lines(input_name, output_name, os_name, app_version), "", *result_lines(results), "", verdict(results)])


def issue_url(results, input_name, output_name, os_name, app_version):
    """A GitHub 'new issue' link with the title and body filled in (the user still presses Submit), or None without a repository."""
    if not ISSUES_URL:
        return None
    interface = input_name if input_name == output_name else f"{input_name} / {output_name}"
    body = "Loopback test results from JV Studio:\n\n```\n" + report_text(results, input_name, output_name, os_name, app_version) + "\n```\n"
    return f"{ISSUES_URL}?title={quote('MIDI interface test: ' + interface)}&body={quote(body)}"

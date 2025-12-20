"""Main entry point for GNOME Nano Image Edit application.

This module defines the main GTK application class and entry point for the
image editing application.
"""

import sys
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gio  # noqa: E402

from .window import MainWindow  # noqa: E402


def on_activate(app):
    """Handles application activation.

    Args:
        app: The GTK application instance.
    """
    # Create the window inside the activate callback
    # Ensure MainWindow accepts the application argument
    win = MainWindow(application=app)

    # Request the system's preferred color scheme
    settings = Gtk.Settings.get_default()
    settings.set_property("gtk-application-prefer-dark-theme", True)

    win.present()


def main() -> int:
    """Runs the application.

    Returns:
        Exit status code.
    """
    # Ensure application_id matches the Flatpak ID
    app = Gtk.Application(
        application_id="com.github.konverner.gnome-nano-image-edit",
        flags=Gio.ApplicationFlags.FLAGS_NONE,
    )
    app.connect("activate", on_activate)
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

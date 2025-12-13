"""Main entry point for GNOME Nano Image Edit application.

This module defines the main GTK application class and entry point for the
image editing application.
"""

import sys
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk  # noqa: E402

from .window import MainWindow  # noqa: E402


class GnomeNanoImageEdit(Gtk.Application):
    """The main GTK application class for GNOME Nano Image Edit.

    This class manages the application lifecycle and creates the main window.
    """

    def __init__(self) -> None:
        """Initializes the GTK application."""
        super().__init__(application_id="com.github.konverner.gnome-nano-image-edit")
        self.connect("activate", self.on_activate)

    def on_activate(self, app: Gtk.Application) -> None:
        """Handles application activation.

        Args:
            app: The GTK application instance.
        """
        win = MainWindow(application=app)
        win.present()


def main() -> int:
    """Runs the application.

    Returns:
        Exit status code.
    """
    app = GnomeNanoImageEdit()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

"""Image processor module for GNOME Nano Image Edit.

This module handles all image data manipulation using Cairo surfaces,
including loading, saving, editing operations, and undo/redo functionality.
"""

import io
import math

import cairo
import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402


class ImageProcessor:
    """Handles all image data and manipulation using Cairo surfaces.

    This class manages the image state, editing operations like crop, cut, paste,
    brush strokes, text overlay, and provides undo/redo functionality.
    """

    def __init__(self) -> None:
        """Initializes the image processor with default state."""
        self._original_surface = None
        self._current_surface = None
        self._floating_selection_data = None
        self._selection_box = None
        self._floating_selection_position = None
        self._brush_size = 10
        self._text_size = 20
        self._brush_color = (255, 0, 0, 255)
        self._font_path = None
        self.image_path = None

        self._undo_stack = []
        self._redo_stack = []
        self._max_undo_steps = 20

        self._is_cropping = False
        self._crop_pan_offset = (0, 0)

    def create_blank_image(
        self, width: int = 800, height: int = 600, color: tuple = (255, 255, 255, 255)
    ) -> None:
        """Creates a blank image with the specified dimensions and color.
        
        Args:
            width: Image width in pixels. Defaults to 800.
            height: Image height in pixels. Defaults to 600.
            color: RGBA color tuple (0-255). Defaults to white (255, 255, 255, 255).
        """
        self.clear_floating_selection()

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)

        # Cairo uses normalized color values (0-1)
        r, g, b, a = [c / 255.0 for c in color]
        ctx.set_source_rgba(r, g, b, a)
        ctx.paint()

        self._original_surface = surface
        self._current_surface = self._copy_surface(surface)

        self.image_path = None
        self._undo_stack = []
        self._redo_stack = []

    def _copy_surface(self, surface: cairo.Surface) -> cairo.Surface:
        """Creates a deep copy of a Cairo surface.

        Args:
            surface: The Cairo surface to copy.

        Returns:
            A new Cairo surface with the same content, or None if surface is None.
        """
        if not surface:
            return None

        new_surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, surface.get_width(), surface.get_height()
        )
        ctx = cairo.Context(new_surface)
        ctx.set_source_surface(surface)
        ctx.paint()
        return new_surface

    def load_image(self, filepath: str) -> None:
        """Loads an image from a file using GdkPixbuf to support multiple formats.

        Args:
            filepath: Path to the image file to load.

        Raises:
            Exception: If the file cannot be loaded or processed.
        """
        self.clear_floating_selection()

        # Use GdkPixbuf to load the image, which supports many formats (JPEG, GIF, etc.)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(filepath)

        # To get this into a Cairo surface, we can save it as a PNG to a memory buffer
        # and then load it into Cairo from that buffer.
        success, buffer = pixbuf.save_to_bufferv("png", [], [])
        if not success:
            raise Exception("Failed to convert image to PNG buffer.")

        # Create a file-like object from the buffer
        png_buffer = io.BytesIO(buffer)

        # Load into a Cairo surface
        surface = cairo.ImageSurface.create_from_png(png_buffer)

        # Ensure the surface is in ARGB32 format for consistency
        if surface.get_format() != cairo.FORMAT_ARGB32:
            new_surface = cairo.ImageSurface(
                cairo.FORMAT_ARGB32, surface.get_width(), surface.get_height()
            )
            ctx = cairo.Context(new_surface)
            ctx.set_source_surface(surface)
            ctx.paint()
            surface = new_surface

        self._original_surface = surface
        self._current_surface = self._copy_surface(surface)

        self.image_path = filepath
        self._undo_stack = []
        self._redo_stack = []

    @property
    def current_image(self) -> cairo.Surface:
        """Returns the current Cairo surface with any floating selection composited.

        Returns:
            The current Cairo surface, with floating selection if present.
        """
        if self._floating_selection_data:
            # Create a temporary composite to show the floating selection being moved
            temp_surface = self._copy_surface(self._current_surface)
            ctx = cairo.Context(temp_surface)
            ctx.set_source_surface(
                self._floating_selection_data,
                self._floating_selection_position[0],
                self._floating_selection_position[1],
            )
            ctx.paint()
            return temp_surface
        return self._current_surface

    def save_state(self) -> None:
        """Saves the current state to the undo stack.

        Limits the undo stack to max_undo_steps entries and clears the redo stack.
        """
        if self._current_surface:
            self._undo_stack.append(self._copy_surface(self._current_surface))
            if len(self._undo_stack) > self._max_undo_steps:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def undo(self) -> bool:
        """Restores the previous state from the undo stack.

        Returns:
            True if undo was successful, False if undo stack is empty.
        """
        if self._undo_stack:
            self._redo_stack.append(self._copy_surface(self._current_surface))
            self._current_surface = self._undo_stack.pop()
            self.clear_floating_selection()
            return True
        return False

    def redo(self) -> bool:
        """Restores the next state from the redo stack.

        Returns:
            True if redo was successful, False if redo stack is empty.
        """
        if self._redo_stack:
            self._undo_stack.append(self._copy_surface(self._current_surface))
            self._current_surface = self._redo_stack.pop()
            self.clear_floating_selection()
            return True
        return False

    def start_crop(self):
        self.paste_selection()  # Finalize any floating selection
        self._is_cropping = True
        self._crop_pan_offset = (0, 0)  # Reset pan

    def cancel_crop(self):
        self._is_cropping = False
        self._selection_box = None
        self._crop_pan_offset = (0, 0)

    def apply_crop(self) -> None:
        """Crops the image to the selection_box."""
        if self._current_surface and self._selection_box and self._is_cropping:
            self.save_state()
            x, y, w, h = self._selection_box
            pan_x, pan_y = self._crop_pan_offset

            new_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w), int(h))
            ctx = cairo.Context(new_surface)

            # Set the source to the relevant part of the old surface
            ctx.set_source_surface(self._current_surface, -x + pan_x, -y + pan_y)
            ctx.paint()

            self._current_surface = new_surface
            self.cancel_crop()

    def cut_selection(self, selection_box):
        """Cuts the selected area and stores it as a Cairo surface."""
        if self._current_surface and selection_box:
            self.paste_selection()  # Paste any existing floating selection first
            self.save_state()

            x, y, w, h = [int(val) for val in selection_box]
            self._selection_box = selection_box
            self._floating_selection_position = (x, y)

            # Create a new surface for the floating selection
            self._floating_selection_data = cairo.ImageSurface(
                cairo.FORMAT_ARGB32, w, h
            )
            cut_ctx = cairo.Context(self._floating_selection_data)
            cut_ctx.set_source_surface(self._current_surface, -x, -y)
            cut_ctx.paint()

            # Fill the area on the main surface with transparent pixels
            main_ctx = cairo.Context(self._current_surface)
            main_ctx.rectangle(x, y, w, h)
            main_ctx.set_operator(cairo.OPERATOR_CLEAR)
            main_ctx.fill()

    def copy_selection(self, selection_box: tuple) -> cairo.Surface:
        """Copies the selected area as a new Cairo surface without removing it."""
        if self._current_surface and selection_box:
            self.paste_selection()  # Paste any existing floating selection first

            x, y, w, h = [int(val) for val in selection_box]

            # Create a new surface for the copied data
            copied_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            ctx = cairo.Context(copied_surface)
            ctx.set_source_surface(self._current_surface, -x, -y)
            ctx.paint()

            return copied_surface
        return None
        
    def set_floating_selection(
        self, surface: cairo.Surface, x: int = 0, y: int = 0
    ) -> None:
        """Sets the floating selection from an external Cairo surface (e.g. paste)."""
        self.paste_selection()  # Commit previous
        self.save_state()  # Save state before adding new floating selection
        self._floating_selection_data = surface
        self._floating_selection_position = (x, y)

    def paste_selection(self):
        """Pastes the floating selection (a Cairo surface) at its current position."""
        if self._current_surface and self._floating_selection_data:
            ctx = cairo.Context(self._current_surface)
            x, y = self._floating_selection_position

            # By default, set_source_surface uses OPERATOR_OVER, which respects alpha
            ctx.set_source_surface(self._floating_selection_data, x, y)
            ctx.paint()

            self.clear_floating_selection()

    def clear_floating_selection(self):
        """Discards the current floating selection."""
        self._floating_selection_data = None
        self._selection_box = None
        self._floating_selection_position = None

    def move_floating_selection(self, x: int, y: int) -> None:
        """Updates the position of the floating selection."""
        if self._floating_selection_data:
            self._floating_selection_position = (x, y)

    def set_brush_size(self, size: int) -> None:
        """Sets the brush diameter."""
        self.paste_selection()
        self._brush_size = size

    def set_brush_color(self, color: tuple) -> None:
        """Sets the brush color."""
        self.paste_selection()
        self._brush_color = color

    def set_text_size(self, size: int) -> None:
        """Sets the text font size."""
        self._text_size = size

    def start_drawing(self):
        """Prepares for a new drawing operation by saving state."""
        self.save_state()

    def draw_brush_stroke(self, points: list) -> None:
        """Draws a stroke along a list of (x, y) coordinates using Cairo."""
        if self._current_surface and len(points) >= 2:
            ctx = cairo.Context(self._current_surface)

            # Set brush properties
            r, g, b, a = [c / 255.0 for c in self._brush_color]
            ctx.set_source_rgba(r, g, b, a)
            ctx.set_line_width(self._brush_size)
            ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            ctx.set_line_join(cairo.LINE_JOIN_ROUND)

            # Draw the line
            ctx.move_to(points[0][0], points[0][1])
            for point in points[1:]:
                ctx.line_to(point[0], point[1])

            ctx.stroke()

    def draw_brush_dab(self, point: tuple) -> None:
        """Draws a single dab of the brush at the given point using Cairo.

        Args:
            point: Tuple of (x, y) coordinates for the brush dab center.
        """
        if self._current_surface:
            self.save_state()
            ctx = cairo.Context(self._current_surface)

            r, g, b, a = [c / 255.0 for c in self._brush_color]
            ctx.set_source_rgba(r, g, b, a)

            x, y = point
            radius = self._brush_size / 2.0

            ctx.arc(x, y, radius, 0, 2 * math.pi)
            ctx.fill()

    def set_font_path(self, font_path: str) -> None:
        """Sets the font path for text tool."""
        self._font_path = font_path

    def add_text(self, text: str, x: int, y: int, font_path: str = None) -> None:
        """Adds text to the image using Cairo."""
        if self._current_surface:
            self.paste_selection()
            self.save_state()
            ctx = cairo.Context(self._current_surface)

            # Set text color
            r, g, b, a = [c / 255.0 for c in self._brush_color]
            ctx.set_source_rgba(r, g, b, a)

            # Set font options
            # Note: While font family is selected, Cairo's native text API (toy text API)
            # has limited capabilities for font matching and may not always
            # render the exact requested font, silently falling back to a default.
            # For robust font handling and advanced text layout, Pango/PangoCairo
            # would be required, but this is a significant integration effort.
            target_font = font_path if font_path else self._font_path
            if target_font:
                # This is a simplification. Real font handling is more complex.
                ctx.select_font_face(
                    target_font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL
                )
            else:
                # Default font
                ctx.select_font_face(
                    "sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL
                )

            ctx.set_font_size(self._text_size)

            # Position and draw text
            ctx.move_to(x, y)
            ctx.show_text(text)

    def save_image(self, filepath: str) -> None:
        """Saves the current Cairo surface to a PNG file."""
        if self._current_surface:
            self.paste_selection()
            # Note: This only supports PNG. Saving to other formats would require
            # external libraries or more complex handling.
            self._current_surface.write_to_png(filepath)
            self.image_path = filepath

    def resize_canvas(
        self, new_width, new_height, anchor=("left", "top"), fill_color=(0, 0, 0, 0)
    ):
        """Resizes the canvas using Cairo, keeping the requested anchor fixed."""
        if not self._current_surface:
            return
        self.paste_selection()
        self.save_state()

        new_width = max(1, int(new_width))
        new_height = max(1, int(new_height))
        anchor_x, anchor_y = anchor

        # Create new surface and fill with color
        new_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, new_width, new_height)
        ctx = cairo.Context(new_surface)
        r, g, b, a = [c / 255.0 for c in fill_color]
        ctx.set_source_rgba(r, g, b, a)
        ctx.paint()

        # Calculate offset and draw old surface onto new one
        offset_x = self._compute_anchor_offset(
            anchor_x, self._current_surface.get_width(), new_width
        )
        offset_y = self._compute_anchor_offset(
            anchor_y, self._current_surface.get_height(), new_height
        )

        ctx.set_source_surface(self._current_surface, offset_x, offset_y)
        ctx.paint()

        self._current_surface = new_surface

    @staticmethod
    def _compute_anchor_offset(anchor, old_size, new_size):
        if anchor in ("left", "top"):
            return 0
        if anchor in ("right", "bottom"):
            return new_size - old_size
        return (new_size - old_size) // 2

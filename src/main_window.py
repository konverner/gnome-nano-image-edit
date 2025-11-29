"""Main window module for GNOME Nano Image Edit.

This module defines the main application window with all UI components,
toolbar, canvas, and event handlers.
"""

import io
import os

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, Gdk, GLib

from src.processor import ImageProcessor
from src.manager import ToolManager
from src.canvas import CanvasWidget

class MainWindow(Gtk.ApplicationWindow):
    """The main application window."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.processor = ImageProcessor()
        self.manager = ToolManager()

        self.set_default_size(800, 600)
        self.set_title("GNOME Nano Image Edit")

        # Header Bar
        header_bar = Gtk.HeaderBar()
        self.set_titlebar(header_bar)

        # Open Button
        open_button = Gtk.Button(label="Open")
        open_button.connect("clicked", self.on_open_clicked)
        header_bar.pack_start(open_button)
        
        # Save Button
        save_button = Gtk.Button(label="Save")
        save_button.connect("clicked", self.on_save_clicked)
        header_bar.pack_start(save_button)

        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_child(main_box)

        # Toolbar Container
        toolbar_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_box.append(toolbar_container)

        # Tool Selector
        tool_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tool_box.set_halign(Gtk.Align.START)
        toolbar_container.append(tool_box)

        # CSS Provider for styling
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            .padded-button {
                padding: 10px 20px;
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Tool Buttons
        self.select_button = Gtk.ToggleButton(label="Select")

        tool_box.append(self.select_button)

        self.crop_button = Gtk.ToggleButton(label="Crop")
        self.crop_button.set_group(self.select_button)

        tool_box.append(self.crop_button)

        apply_crop_button = Gtk.Button(label="Apply Crop")
        apply_crop_button.connect("clicked", self.on_apply_crop_clicked)
        tool_box.append(apply_crop_button)

        self.brush_button = Gtk.ToggleButton(label="Brush")
        self.brush_button.set_group(self.select_button)

        tool_box.append(self.brush_button)

        self.text_button = Gtk.ToggleButton(label="Text")
        self.text_button.set_group(self.select_button)

        tool_box.append(self.text_button)
        
        
        # Connect signals
        self.select_button.connect("toggled", self.on_tool_toggled, "select")
        self.crop_button.connect("toggled", self.on_tool_toggled, "crop")
        self.brush_button.connect("toggled", self.on_tool_toggled, "brush")
        self.text_button.connect("toggled", self.on_tool_toggled, "text")

        # Brush Controls (initially hidden)
        self.brush_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.brush_controls_box.set_visible(False)
        self.brush_controls_box.set_hexpand(True)
        toolbar_container.append(self.brush_controls_box)

        # Brush Size
        self.brush_size_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.brush_size_scale.set_value(10)
        self.brush_size_scale.set_hexpand(True)
        self.brush_size_scale.connect("value-changed", self.on_tool_size_changed)
        self.brush_controls_box.append(self.brush_size_scale)

        size_label = Gtk.Label(label="Size")
        self.brush_controls_box.append(size_label)

        # Brush Color
        color_label = Gtk.Label(label="Color")
        self.brush_controls_box.append(color_label)
        self.brush_color_button = Gtk.ColorButton()
        default_rgba = Gdk.RGBA()
        default_rgba.parse("#ff0000ff") # let us use red by default
        self.brush_color_button.set_rgba(default_rgba)
        self.brush_color_button.connect("color-set", self.on_brush_color_set)
        self.brush_controls_box.append(self.brush_color_button)

        # Font Selection (initially hidden, shown for Text tool)
        fonts = ["sans-serif", "serif", "monospace"]
        self.font_dropdown = Gtk.DropDown.new_from_strings(fonts)
        self.font_dropdown.connect("notify::selected-item", self.on_font_changed)
        self.brush_controls_box.append(self.font_dropdown)

        # Canvas
        self.canvas = CanvasWidget(self.processor, self.manager)
        
        # Overlay for text entry
        self.overlay = Gtk.Overlay()
        self.overlay.set_child(self.canvas)
        
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.overlay)
        scrolled_window.set_vexpand(True)
        main_box.append(scrolled_window)

        # Pass overlay to canvas for text tool
        self.canvas.set_overlay(self.overlay)

        # Set default tool
        self.select_button.set_active(True)

        # Key Controller
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

        # Create a blank canvas by default so tools work immediately
        self.processor.create_blank_image()

    def _update_tool_ui(self):
        """Show or hide tool-specific controls."""
        tool = self.manager.current_tool
        show_controls = tool in ['brush', 'text']
        self.brush_controls_box.set_visible(show_controls)
        
        # Show/Hide specific controls based on tool
        if tool == 'text':
            self.font_dropdown.set_visible(True)
        else:
            self.font_dropdown.set_visible(False)
        
        # Update scale value based on tool
        if tool == 'brush':
            self.brush_size_scale.set_value(self.processor._brush_size)
        elif tool == 'text':
            self.brush_size_scale.set_value(self.processor._text_size)

        if tool != 'text':
            self.canvas.hide_text_entry()

    def on_key_pressed(self, controller, keyval, keycode, state):
        """Handle key press events."""
        ctrl = (state & Gdk.ModifierType.CONTROL_MASK)
        
        # Undo: Ctrl+Z
        if ctrl and keyval == Gdk.KEY_z:
            if self.processor.undo():
                self.canvas.queue_draw()
            return True
            
        # Redo: Ctrl+Y
        if ctrl and keyval == Gdk.KEY_y:
            if self.processor.redo():
                self.canvas.queue_draw()
            return True

        # Save: Ctrl+S
        if ctrl and keyval == Gdk.KEY_s:
            self.on_save_clicked(None)
            return True

        # Open: Ctrl+O
        if ctrl and keyval == Gdk.KEY_o:
            self.on_open_clicked(None)
            return True

        # Copy: Ctrl+C
        if ctrl and keyval == Gdk.KEY_c:
            self.copy_to_clipboard()
            return True

        # Cut: Ctrl+X
        if ctrl and keyval == Gdk.KEY_x:
            self.cut_to_clipboard()
            return True

        # Paste: Ctrl+V
        if ctrl and keyval == Gdk.KEY_v:
            self.paste_from_clipboard()
            return True

        # Text Tool: Ctrl+T
        if ctrl and keyval == Gdk.KEY_t:
            self.text_button.set_active(True)
            return True


        # Delete key handling
        if keyval == Gdk.KEY_Delete:
            if self.processor._selection_box:
                if self.processor._floating_selection_data:
                    self.processor.clear_floating_selection()
                else:
                    # Clear the selected area
                    self.processor.cut_selection(self.processor._selection_box)
                    self.processor.clear_floating_selection()
                self.canvas.queue_draw()
            return True

        return False

    def copy_to_clipboard(self):
        """Copy current selection to clipboard."""
        selection = self.canvas.get_scaled_selection()
        if selection:
            image = self.processor.copy_selection(selection)
            if image:
                self._copy_image_to_clipboard(image)

    def cut_to_clipboard(self):
        """Cut current selection to clipboard."""
        selection = self.canvas.get_scaled_selection()
        if selection:
            # cut_selection puts it in floating selection
            self.processor.cut_selection(selection)
            # Now we take that floating selection and put it on clipboard
            if self.processor._floating_selection_data:
                self._copy_image_to_clipboard(self.processor._floating_selection_data)
                # Optionally clear floating selection if "Cut" means "remove from canvas completely"
                # usually Cut = Copy + Delete.
                # In GIMP/Paint, Cut leaves a hole.
                # But does it leave a floating selection?
                # In Paint, Cut removes it and puts on clipboard. It does NOT leave a floating selection.
                self.processor.clear_floating_selection()
            self.canvas.queue_draw()

    def _copy_image_to_clipboard(self, surface: cairo.Surface) -> None:
        """Helper to put Cairo surface on clipboard.
        
        Args:
            surface: The Cairo surface to copy to clipboard.
        """
        clipboard = Gdk.Display.get_default().get_clipboard()
        
        # Convert Cairo surface to GdkTexture
        b = io.BytesIO()
        surface.write_to_png(b)
        data = b.getvalue()
        bytes_obj = GLib.Bytes.new(data)
        
        content = Gdk.ContentProvider.new_for_bytes("image/png", bytes_obj)
        clipboard.set_content(content)

    def paste_from_clipboard(self):
        """Paste from clipboard."""
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.read_texture_async(None, self._on_paste_texture_ready)

    def _on_paste_texture_ready(self, clipboard: Gdk.Clipboard, result) -> None:
        """Callback for paste operation when texture is ready.
        
        Args:
            clipboard: The clipboard object.
            result: The async result object.
        """
        try:
            texture = clipboard.read_texture_finish(result)
            if texture:
                # Convert GdkTexture to Cairo Surface
                bytes_obj = texture.save_to_png_bytes()
                
                # Create a Cairo surface from the PNG data
                with io.BytesIO(bytes_obj.get_data()) as f:
                    surface = cairo.ImageSurface.create_from_png(f)

                # Set as floating selection
                self.processor.set_floating_selection(surface, 0, 0)
                self.manager.current_tool = 'select'  # Switch to select tool to move it
                self.canvas.queue_draw()
        except Exception as e:
            self.show_error(f"Failed to paste image: {e}")

    def show_error(self, message):
        """Show an error message dialog."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Error", # Main error title
            secondary_text=message, # Detailed error message
        )
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

    def on_open_clicked(self, widget):
        """Handle the Open button click."""
        dialog = Gtk.FileChooserDialog(
            title="Please choose a file",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL, "_Open", Gtk.ResponseType.ACCEPT
        )

        dialog.connect("response", self.on_open_dialog_response)
        dialog.show()

    def on_open_dialog_response(self, dialog, response):
        """Handle the response from the file chooser dialog."""
        if response == Gtk.ResponseType.ACCEPT:
            try:
                file = dialog.get_file()
                self.processor.load_image(file.get_path())
                self.canvas.queue_draw()
            except cairo.Error as e:
                self.show_error(f"Failed to open image: {e}. Only valid PNG files are supported.")
        dialog.destroy()
        
    def on_save_clicked(self, widget):
        """Handle the Save button click."""
        dialog = Gtk.FileChooserDialog(
            title="Save image as",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL, "_Save", Gtk.ResponseType.ACCEPT
        )

        # Pre-insert filename
        if self.processor.image_path:
            filename = os.path.basename(self.processor.image_path)
            dialog.set_current_name(filename)
        else:
            dialog.set_current_name("unknown.png")

        dialog.connect("response", self.on_save_dialog_response)
        dialog.show()

    def on_save_dialog_response(self, dialog, response):
        """Handle the response from the file chooser dialog."""
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            self.processor.save_image(file.get_path())
        dialog.destroy()

    def on_tool_toggled(self, button, tool_name):
        """Handle tool selection from toggle buttons."""
        if button.get_active():
            self.manager.current_tool = tool_name
            self._update_tool_ui()

    def on_apply_crop_clicked(self, widget):
        """Apply the crop based on the selection."""
        if self.processor._selection_box:
            self.processor.apply_crop(self.processor._selection_box)
            self.canvas.queue_draw()

    def on_tool_size_changed(self, scale):
        """Handle tool size change."""
        size = int(scale.get_value())
        if self.manager.current_tool == 'brush':
            self.processor.set_brush_size(size)
        elif self.manager.current_tool == 'text':
            self.processor.set_text_size(size)

    def on_brush_color_set(self, color_button):
        """Handle brush color change."""
        color = color_button.get_rgba()
        # Convert Gdk.RGBA to a tuple of (r, g, b, a) in 0-255 range
        rgba_255 = (
            int(color.red * 255),
            int(color.green * 255),
            int(color.blue * 255),
            int(color.alpha * 255)
        )
        self.processor.set_brush_color(rgba_255)
        self.canvas.update_text_color(rgba_255)

    def on_font_changed(self, dropdown, pspec):
        """Handle font selection."""
        selected_item = dropdown.get_selected_item()
        if not selected_item:
            return
            
        font_desc = selected_item.get_string()
        self.processor.set_font_path(font_desc)

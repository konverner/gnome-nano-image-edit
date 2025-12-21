"""Main window module for GNOME Nano Image Edit.

This module defines the main application window with all UI components,
toolbar, canvas, and event handlers.
"""

import datetime
import io
import os

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gio, Gdk, GLib  # noqa: E402

from .processor import ImageProcessor  # noqa: E402
from .manager import ToolManager  # noqa: E402
from .canvas import CanvasWidget  # noqa: E402


class MainWindow(Gtk.ApplicationWindow):
    """The main application window."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.processor = ImageProcessor()
        self.manager = ToolManager()

        self.set_default_size(800, 600)
        self.set_title("GNOME Nano Image Edit")

        self._setup_icon()

        # CSS Provider for styling
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(
            b"""
            .toolbar-container {
                margin-bottom: 8px;
                margin-left: 8px;
            }
            .padded-button {
                padding: 5px 10px;
            }
        """
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

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

        # Menu Button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        header_bar.pack_end(menu_button)

        menu = Gio.Menu()
        menu.append("About", "win.about")
        menu.append("Keyboard Shortcuts", "win.shortcuts")
        menu_button.set_menu_model(menu)

        # Actions
        action_about = Gio.SimpleAction.new("about", None)
        action_about.connect("activate", self.on_about_activated)
        self.add_action(action_about)

        action_shortcuts = Gio.SimpleAction.new("shortcuts", None)
        action_shortcuts.connect("activate", self.on_shortcuts_activated)
        self.add_action(action_shortcuts)

        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_child(main_box)

        # Canvas & Overlay
        self.canvas = CanvasWidget(self.processor, self.manager)
        self.overlay = Gtk.Overlay()
        self.overlay.set_child(self.canvas)
        # Pass overlay to canvas for text tool
        self.canvas.set_overlay(self.overlay)

        # Scrolled Window (Canvas Container) - Add this FIRST
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.overlay)
        scrolled_window.set_vexpand(True)
        main_box.append(scrolled_window)

        # Toolbar Container - Add this SECOND (Bottom)
        toolbar_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar_container.add_css_class("toolbar-container")
        main_box.append(toolbar_container)

        # Tool Selector Box
        tool_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tool_box.set_halign(Gtk.Align.START)
        toolbar_container.append(tool_box)

        # Tool Buttons
        tool_size_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        self.select_button = Gtk.ToggleButton(label="Select")
        self.select_button.add_css_class("padded-button")
        tool_size_group.add_widget(self.select_button)
        tool_box.append(self.select_button)

        self.crop_button = Gtk.Button(label="Crop")
        self.crop_button.add_css_class("padded-button")
        tool_size_group.add_widget(self.crop_button)
        tool_box.append(self.crop_button)

        self.brush_button = Gtk.ToggleButton(label="Brush")
        self.brush_button.set_group(self.select_button)
        self.brush_button.add_css_class("padded-button")
        tool_size_group.add_widget(self.brush_button)
        tool_box.append(self.brush_button)

        self.text_button = Gtk.ToggleButton(label="Text")
        self.text_button.set_group(self.select_button)
        self.text_button.add_css_class("padded-button")
        tool_size_group.add_widget(self.text_button)
        tool_box.append(self.text_button)

        # Connect signals
        self.select_button.connect("toggled", self.on_tool_toggled, "select")
        self.crop_button.connect("clicked", self.on_crop_clicked)
        self.brush_button.connect("toggled", self.on_tool_toggled, "brush")
        self.text_button.connect("toggled", self.on_tool_toggled, "text")

        # Brush Controls (initially hidden)
        self.brush_controls_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12
        )
        self.brush_controls_box.set_visible(False)
        self.brush_controls_box.set_hexpand(True)
        toolbar_container.append(self.brush_controls_box)

        # Brush Size
        self.brush_size_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 1, 100, 1
        )
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
        default_rgba.parse("#ff0000ff")  # let us use red by default
        self.brush_color_button.set_rgba(default_rgba)
        self.brush_color_button.connect("color-set", self.on_brush_color_set)
        self.brush_controls_box.append(self.brush_color_button)

        # Font Selection (initially hidden, shown for Text tool)
        fonts = ["sans-serif", "serif", "monospace"]
        self.font_dropdown = Gtk.DropDown.new_from_strings(fonts)
        self.font_dropdown.connect("notify::selected-item", self.on_font_changed)
        self.brush_controls_box.append(self.font_dropdown)

        # Set default tool
        self.select_button.set_active(True)

        # Key Controller
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

        # Create a blank canvas by default so tools work immediately
        self.processor.create_blank_image()
        self.file_dialog = None

    def on_about_activated(self, widget, _):
        about_dialog = Gtk.AboutDialog(
            transient_for=self,
            modal=True,
            program_name="GNOME Nano Image Edit",
            version="0.1.0",
            copyright="© 2025-2026 Verner K.",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/konverner/gnome-nano-image-edit",
            comments="This program comes with absolutely no warranty.",
            authors=["Verner K."], # Optional
            # translators=["Your Name <your.email@example.com>"], # Optional
        )
        # Set the application icon
        try:
            about_dialog.set_logo_icon_name("com.github.konverner.gnome-nano-image-edit")
        except Exception as e:
            print(f"Warning: Failed to set about dialog icon: {e}")
        about_dialog.present()

    def on_shortcuts_activated(self, widget, _):
        shortcuts_window = Gtk.ShortcutsWindow(
            transient_for=self,
            modal=True,
            title="Keyboard Shortcuts"
        )

        # Create a section for general shortcuts
        section_general = Gtk.ShortcutsSection(title="General")
        shortcuts_window.add_section(section_general)

        # Create a group within the section
        group_general = Gtk.ShortcutsGroup(title="General Actions")
        section_general.add_group(group_general)

        # Add shortcuts to the group
        group_general.add_shortcut(
            Gtk.ShortcutsShortcut(
                title="Open Image",
                accelerator="<Control>o"
            )
        )
        group_general.add_shortcut(
            Gtk.ShortcutsShortcut(
                title="Save Image",
                accelerator="<Control>s"
            )
        )
        group_general.add_shortcut(
            Gtk.ShortcutsShortcut(
                title="Undo",
                accelerator="<Control>z"
            )
        )
        group_general.add_shortcut(
            Gtk.ShortcutsShortcut(
                title="Redo",
                accelerator="<Control>y"
            )
        )
        group_general.add_shortcut(
            Gtk.ShortcutsShortcut(
                title="Copy Selection",
                accelerator="<Control>c"
            )
        )
        group_general.add_shortcut(
            Gtk.ShortcutsShortcut(
                title="Cut Selection",
                accelerator="<Control>x"
            )
        )
        group_general.add_shortcut(
            Gtk.ShortcutsShortcut(
                title="Paste Selection",
                accelerator="<Control>v"
            )
        )
        group_general.add_shortcut(
            Gtk.ShortcutsShortcut(
                title="Activate Text Tool",
                accelerator="<Control>t"
            )
        )
        group_general.add_shortcut(
            Gtk.ShortcutsShortcut(
                title="Delete Selection",
                accelerator="Delete"
            )
        )


        shortcuts_window.present()

    def _setup_icon(self):
        """Configure the application icon from the installed icon theme."""
        try:
            self.set_icon_name("com.github.konverner.gnome-nano-image-edit")
        except Exception as e:
            print(f"Warning: Failed to set application icon: {e}")

    def _update_tool_ui(self):
        """Show or hide tool-specific controls."""
        tool = self.manager.current_tool
        show_controls = tool in ["brush", "text"]
        self.brush_controls_box.set_visible(show_controls)

        # Show/Hide specific controls based on tool
        if tool == "text":
            self.font_dropdown.set_visible(True)
        else:
            self.font_dropdown.set_visible(False)

        # Update scale value based on tool
        if tool == "brush":
            self.brush_size_scale.set_value(self.processor._brush_size)
        elif tool == "text":
            self.brush_size_scale.set_value(self.processor._text_size)

        if tool != "text":
            self.canvas.hide_text_entry()

    def on_key_pressed(self, controller, keyval, keycode, state):
        """Handle key press events."""
        ctrl = state & Gdk.ModifierType.CONTROL_MASK

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
        else:
            # If no selection, copy the entire canvas
            if self.processor.current_image:
                self._copy_image_to_clipboard(self.processor.current_image)

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
                self.manager.current_tool = "select"  # Switch to select tool to move it
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
            text="Error",  # Main error title
            secondary_text=message,  # Detailed error message
        )
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

    def on_open_clicked(self, widget):
        """Handle the Open button click."""
        print("DEBUG: on_open_clicked called")
        self.file_dialog = Gtk.FileChooserDialog(
            title="Please choose a file",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        self.file_dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL, "_Open", Gtk.ResponseType.ACCEPT
        )
        print("DEBUG: Gtk.FileChooserDialog created")

        filter_img = Gtk.FileFilter()
        filter_img.set_name("Image files")
        filter_img.add_mime_type("image/png")
        filter_img.add_mime_type("image/jpeg")
        filter_img.add_mime_type("image/gif")
        self.file_dialog.add_filter(filter_img)
        print("DEBUG: Image filter added")

        filter_all = Gtk.FileFilter()
        filter_all.set_name("All files")
        filter_all.add_pattern("*")
        self.file_dialog.add_filter(filter_all)
        print("DEBUG: All files filter added")

        self.file_dialog.connect("response", self._on_open_dialog_response)
        print("DEBUG: 'response' signal connected")
        self.file_dialog.show()
        print("DEBUG: dialog.show() called")

    def _on_open_dialog_response(self, dialog, response_id):
        """Handle the response from the file chooser dialog."""
        print(f"DEBUG: _on_open_dialog_response called with response_id: {response_id}")
        if response_id == Gtk.ResponseType.ACCEPT:
            print("DEBUG: Response is ACCEPT")
            try:
                file = dialog.get_file()
                if file:
                    file_path = file.get_path()
                    print(f"DEBUG: File selected: {file_path}")

                    # Check file size restrictions (0.01MB to 8MB)
                    file_size = os.path.getsize(file_path)
                    min_size = 10 * 1024  # 0.01 MB
                    max_size = 8 * 1024 * 1024  # 8 MB

                    if not (min_size <= file_size <= max_size):
                        print("DEBUG: File size error")
                        self.show_error("File size must be between 0.01 MB and 8.0 MB.")
                    else:
                        print("DEBUG: Loading image...")
                        self.processor.load_image(file_path)
                        self.canvas.queue_draw()
                        print("DEBUG: Image loaded and canvas queued for draw")
                else:
                    print("DEBUG: dialog.get_file() returned None")
            except GLib.Error as e:
                print(f"DEBUG: GLib.Error: {e}")
                self.show_error(f"Failed to open file: {e}")
            except cairo.Error as e:
                print(f"DEBUG: cairo.Error: {e}")
                self.show_error(
                    f"Failed to open image: {e}. The file may be corrupt or an unsupported format."
                )
            except Exception as e:
                print(f"DEBUG: Exception: {e}")
                self.show_error(f"An error occurred while opening the file: {e}")
        elif response_id == Gtk.ResponseType.CANCEL:
            print("DEBUG: Response is CANCEL")
        else:
            print(f"DEBUG: Response is something else: {response_id}")

        dialog.destroy()
        self.file_dialog = None
        print("DEBUG: dialog destroyed")

    def on_save_clicked(self, widget):
        """Handle the Save button click."""
        print("DEBUG: on_save_clicked called")

        # Auto-apply crop if pending
        if self.processor._is_cropping:
            self.processor.apply_crop()
            self.canvas.queue_draw()

        if self.file_dialog is not None:
            print("DEBUG: Another dialog is already open.")
            return

        self.file_dialog = Gtk.FileChooserDialog(
            title="Save Image As", transient_for=self, action=Gtk.FileChooserAction.SAVE
        )
        self.file_dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL, "_Save", Gtk.ResponseType.ACCEPT
        )
        print("DEBUG: Gtk.FileChooserDialog for save created")

        # Pre-insert filename
        if self.processor.image_path:
            filename = os.path.basename(self.processor.image_path)
            self.file_dialog.set_current_name(filename)
            print(f"DEBUG: Setting initial name from existing path: {filename}")
        else:
            now = datetime.datetime.now()
            filename = now.strftime("image-%Y-%m-%dT%H-%M-%S.png")
            self.file_dialog.set_current_name(filename)
            print(f"DEBUG: Setting initial name to new timestamp: {filename}")

        # Add filter for PNG files
        filter_png = Gtk.FileFilter()
        filter_png.set_name("PNG images")
        filter_png.add_mime_type("image/png")
        filter_png.add_pattern("*.png")
        self.file_dialog.add_filter(filter_png)
        print("DEBUG: PNG filter added")

        self.file_dialog.connect("response", self._on_save_dialog_response)
        print("DEBUG: 'response' signal connected for save")
        self.file_dialog.show()
        print("DEBUG: save dialog.show() called")

    def _on_save_dialog_response(self, dialog, response_id):
        """Handle the response from the file chooser dialog."""
        print(f"DEBUG: _on_save_dialog_response called with response_id: {response_id}")
        if response_id == Gtk.ResponseType.ACCEPT:
            print("DEBUG: Save response is ACCEPT")
            try:
                file = dialog.get_file()
                if file:
                    path = file.get_path()
                    print(f"DEBUG: Saving to path: {path}")
                    # Ensure the filename has a .png extension if not provided
                    if not path.lower().endswith(".png"):
                        path += ".png"
                        print(f"DEBUG: Appended .png, new path: {path}")
                    self.processor.save_image(path)
                    print("DEBUG: processor.save_image called")
                else:
                    print("DEBUG: dialog.get_file() returned None for save")
            except GLib.Error as e:
                print(f"DEBUG: GLib.Error on save: {e}")
                if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                    self.show_error(f"Failed to save file: {e}")
            except Exception as e:
                print(f"DEBUG: Exception on save: {e}")
                self.show_error(f"An error occurred while saving the file: {e}")
        else:
            print("DEBUG: Save response is not ACCEPT")

        dialog.destroy()
        self.file_dialog = None
        print("DEBUG: save dialog destroyed")

    def on_tool_toggled(self, button, tool_name):
        """Handle tool selection from toggle buttons."""
        if button.get_active():
            if self.processor._is_cropping:
                self.processor.cancel_crop()
                self.canvas.queue_draw()
            self.manager.current_tool = tool_name
            self._update_tool_ui()

    def on_crop_clicked(self, widget):
        """Handle the crop button click."""
        if self.processor._is_cropping:
            self.processor.apply_crop()
        elif self.processor._selection_box:
            self.manager.current_tool = "select"  # Ensure no other tool is active
            self.select_button.set_active(True)
            self.processor.start_crop()
        self.canvas.queue_draw()

    def on_tool_size_changed(self, scale):
        """Handle tool size change."""
        size = int(scale.get_value())
        if self.manager.current_tool == "brush":
            self.processor.set_brush_size(size)
        elif self.manager.current_tool == "text":
            self.processor.set_text_size(size)
            self.canvas.update_text_color(self.processor._brush_color)

    def on_brush_color_set(self, color_button):
        """Handle brush color change."""
        color = color_button.get_rgba()
        # Convert Gdk.RGBA to a tuple of (r, g, b, a) in 0-255 range
        rgba_255 = (
            int(color.red * 255),
            int(color.green * 255),
            int(color.blue * 255),
            int(color.alpha * 255),
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

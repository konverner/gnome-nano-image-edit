"""Canvas widget module for GNOME Nano Image Edit.

This module provides the custom drawing canvas widget that handles image display,
user input events, tool interactions, and text entry overlays.
"""

import gi  # noqa: E402
import cairo

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk  # noqa: E402


def _create_text_css_provider(
    color_rgba: tuple = (255, 255, 255, 255),
    font_size: float = 20.0,
) -> Gtk.CssProvider:
    """Creates a CSS provider with the specified text color.

    Args:
        color_rgba: RGBA color tuple (0-255). Defaults to white.
        font_size: Font size in pixels. Defaults to 20.0.

    Returns:
        A GTK CSS provider configured for text entry styling.
    """
    r, g, b, a = color_rgba
    # Convert 0-255 to CSS rgba string
    css = f"""
    textview.canvas-text-overlay {{
        background-color: transparent;
        color: rgba({r}, {g}, {b}, {a/255.0});
        caret-color: rgba({r}, {g}, {b}, {a/255.0});
        font-size: {font_size}px;
    }}
    
    textview.canvas-text-overlay text,
    textview.canvas-text-overlay view {{
        background-color: transparent;
    }}
    
    textview.canvas-text-overlay border {{
        border: 1px dashed rgba({r}, {g}, {b}, 0.7);
        border-radius: 4px;
    }}
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode("utf-8"))
    return provider


class CanvasWidget(Gtk.DrawingArea):
    """Custom drawing widget for image display and editing.

    This widget handles rendering of the image, selection overlays,
    user input events, and tool interactions.
    """

    RESIZE_HANDLE_SIZE = 12
    RESIZE_HANDLE_MARGIN = 8

    def __init__(self, processor, manager):
        super().__init__()
        self.processor = processor
        self.manager = manager

        self.set_draw_func(self.on_draw)
        self.selection_box = None
        self._start_point = None
        self._stroke_points = []
        self._text_entry = None
        self._overlay = None
        self._text_entry_pos = None
        self._text_entry_initial_dims = None
        self._drag_mode = "none"  # 'none', 'select', 'move', 'move_crop_image'
        self._drag_start_offset = (0, 0)
        self._start_pan_offset = (0, 0)
        self._image_display_rect = None
        self._hover_resize_handle = None
        self._active_resize_handle = None
        self._resize_start_pointer = None
        self._resize_start_size = None
        self._resize_anchor = ("left", "top")
        self._canvas_resize_in_progress = False

        # Zoom state
        self._zoom_level = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 10.0

        # Drag gesture
        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        self.add_controller(drag)

        # Click gesture
        click = Gtk.GestureClick.new()
        click.connect("pressed", self.on_canvas_pressed)
        self.add_controller(click)

        self._motion_controller = Gtk.EventControllerMotion()
        self._motion_controller.connect("motion", self.on_motion)
        self._motion_controller.connect("leave", self.on_motion_leave)
        self.add_controller(self._motion_controller)

        # Scroll controller for zooming
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self.on_scroll)
        self.add_controller(scroll)

    def set_overlay(self, overlay):
        """Store a reference to the overlay that wraps this canvas.
        Do not try to replace the overlay's child from here — MainWindow controls that."""
        self._overlay = overlay

    def _update_text_entry_size(self, font_size):
        """Update the size request of the text entry based on font size."""
        if not self._text_entry or not self._text_entry_initial_dims:
            return

        cw, ch = self._text_entry_initial_dims

        # Ensure height accommodates the font size
        # Using 1.5 as a safe factor for line-height + border padding
        required_h = font_size * 1.5

        req_w = max(150, int(cw))
        req_h = max(30, int(ch), int(required_h))

        self._text_entry.set_size_request(req_w, req_h)

    def show_text_entry(self, x, y, w, h):
        """Create a text entry positioned over the canvas at the given image coords."""
        if not self._overlay:
            return
        # Remove any existing text entry
        self._finalize_text_entry()

        canvas_rect = self._image_box_to_canvas_rect(x, y, w, h)
        if canvas_rect is None:
            return
        cx, cy, cw, ch = canvas_rect
        self._text_entry_initial_dims = (cw, ch)

        # Use a TextView for multiline support
        self._text_entry = Gtk.TextView()
        self._text_entry.set_wrap_mode(Gtk.WrapMode.NONE)

        # Apply current color
        color = self.processor._brush_color
        scale = self._image_display_rect[4] if self._image_display_rect else 1.0
        font_size = self.processor._text_size * scale
        self._apply_text_entry_style(color, font_size)

        # Style the text view to look like a text box
        self._update_text_entry_size(font_size)

        # Position using margins
        self._text_entry.set_margin_start(int(cx))
        self._text_entry.set_margin_top(int(cy))
        self._text_entry.set_halign(Gtk.Align.START)
        self._text_entry.set_valign(Gtk.Align.START)

        # Connect focus-leave
        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect("leave", self._on_text_focus_out)
        self._text_entry.add_controller(focus_controller)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_text_entry_key_press)
        self._text_entry.add_controller(key_controller)

        self._overlay.add_overlay(self._text_entry)
        self._text_entry.grab_focus()

        # Remember the image-space position to place text in the PIL image.
        self._text_entry_pos = (int(x), int(y))

    def _calculate_image_display_geometry(self):
        """
        Calculates and caches the image's display geometry (position, size, scale).
        This is the single source of truth for widget<->image coordinate mapping.
        """
        if not self.processor.current_image:
            self._image_display_rect = None
            return None

        alloc = self.get_allocation()
        widget_w, widget_h = alloc.width, alloc.height
        img_w, img_h = (
            self.processor.current_image.get_width(),
            self.processor.current_image.get_height(),
        )

        if img_w == 0 or img_h == 0 or widget_w == 0 or widget_h == 0:
            self._image_display_rect = None
            return None

        aspect_ratio = img_w / img_h
        area_aspect_ratio = widget_w / widget_h

        if aspect_ratio > area_aspect_ratio:
            # Fit to width
            display_width = widget_w
            display_height = widget_w / aspect_ratio
        else:
            # Fit to height
            display_height = widget_h
            display_width = widget_h * aspect_ratio

        scale = (display_width / img_w) * self._zoom_level

        # Apply zoom
        display_width *= self._zoom_level
        display_height *= self._zoom_level

        x_offset = (widget_w - display_width) / 2
        y_offset = (widget_h - display_height) / 2

        self._image_display_rect = (
            x_offset,
            y_offset,
            display_width,
            display_height,
            scale,
        )
        return self._image_display_rect

    def on_draw(self, area, cr, width, height):
        """The draw function."""
        geom = self._calculate_image_display_geometry()
        if not geom or not self.processor.current_image:
            # Draw a background if no image
            cr.set_source_rgb(0.1, 0.1, 0.1)
            cr.paint()
            return

        x_offset, y_offset, _, _, scale = geom

        # Draw background
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.paint()

        # Draw image
        surface = self.processor.current_image
        cr.save()
        cr.translate(x_offset, y_offset)
        cr.scale(scale, scale)

        if self.processor._is_cropping:
            pan_x, pan_y = self.processor._crop_pan_offset
            cr.set_source_surface(surface, pan_x, pan_y)
        else:
            cr.set_source_surface(surface, 0, 0)

        cr.get_source().set_filter(cairo.FILTER_BEST)
        cr.paint()
        cr.restore()

        # Draw crop overlay or selection rectangle
        if self.processor._is_cropping and self.processor._selection_box:
            cr.save()
            x, y, w, h = self.processor._selection_box
            p1 = self._image_to_canvas_coords(x, y)
            p2 = self._image_to_canvas_coords(x + w, y + h)
            if p1 and p2:
                canvas_x, canvas_y = p1
                canvas_w, canvas_h = p2[0] - p1[0], p2[1] - p1[1]

                cr.rectangle(0, 0, width, height)
                cr.rectangle(canvas_x, canvas_y, canvas_w, canvas_h)
                cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
                cr.set_source_rgba(0, 0, 0, 0.5)
                cr.fill()

                cr.set_source_rgba(1, 1, 1, 0.7)
                cr.set_dash([3, 3])
                cr.set_line_width(1)
                cr.rectangle(canvas_x, canvas_y, canvas_w, canvas_h)
                cr.stroke()
            cr.restore()
        elif (
            self.processor._selection_box
            and not self.processor._floating_selection_data
        ):
            x, y, w, h = self.processor._selection_box
            p1 = self._image_to_canvas_coords(x, y)
            p2 = self._image_to_canvas_coords(x + w, y + h)
            if p1 and p2:
                cr.save()
                cr.set_source_rgba(0.1, 0.4, 0.8, 0.5)
                cr.set_dash([5, 5])
                cr.set_line_width(2)
                cr.rectangle(p1[0], p1[1], p2[0] - p1[0], p2[1] - p1[1])
                cr.stroke()
                cr.restore()
        elif (
            self._drag_mode == "select" or self._drag_mode == "text_create"
        ) and self.selection_box:
            cr.save()
            cr.set_source_rgba(0.1, 0.4, 0.8, 0.5)
            cr.set_dash([5, 5])
            cr.set_line_width(2)
            x, y, w, h = self.selection_box
            cr.rectangle(x, y, w, h)
            cr.stroke()
            cr.restore()

        self._draw_resize_handles(cr)

    def on_motion(self, controller, x, y):
        if self._canvas_resize_in_progress:
            return
        # Ensure geometry is calculated before hit testing
        self._calculate_image_display_geometry()
        handle = self._hit_test_resize_handle(x, y)
        if handle != self._hover_resize_handle:
            self._hover_resize_handle = handle
            self._update_cursor_for_handle(handle)

        if not handle and self.processor._is_cropping and self.processor._selection_box:
            sel_x, sel_y, sel_w, sel_h = self.processor._selection_box
            p1 = self._image_to_canvas_coords(sel_x, sel_y)
            p2 = self._image_to_canvas_coords(sel_x + sel_w, sel_y + sel_h)
            if p1 and p2:
                cx1, cy1 = p1
                cx2, cy2 = p2
                if cx1 <= x <= cx2 and cy1 <= y <= cy2:
                    cursor = Gdk.Cursor.new_from_name("move")
                    self.set_cursor(cursor)
                elif self._hover_resize_handle is None:
                    self.set_cursor(None)

        elif not handle and self.manager.current_tool == "select":
            # Check for hover over selection box (floating or not)
            box = None
            if self.processor._floating_selection_data:
                # If floating, use its position
                pos = self.processor._floating_selection_position
                w = self.processor._floating_selection_data.get_width()
                h = self.processor._floating_selection_data.get_height()
                box = (pos[0], pos[1], w, h)
            elif self.processor._selection_box:
                box = self.processor._selection_box

            if box:
                bx, by, bw, bh = box
                p1 = self._image_to_canvas_coords(bx, by)
                p2 = self._image_to_canvas_coords(bx + bw, by + bh)
                if p1 and p2:
                    cx1, cy1 = p1
                    cx2, cy2 = p2
                    if cx1 <= x <= cx2 and cy1 <= y <= cy2:
                        cursor = Gdk.Cursor.new_from_name("move")
                        self.set_cursor(cursor)
                    elif self._hover_resize_handle is None:
                        self.set_cursor(None)
                elif self._hover_resize_handle is None:
                    self.set_cursor(None)
            elif self._hover_resize_handle is None:
                self.set_cursor(None)

        elif not handle and self._hover_resize_handle is None:
            # Ensure cursor is reset if we left the handle and aren't over crop or selection
            self.set_cursor(None)

    def on_motion_leave(self, controller):
        if self._canvas_resize_in_progress:
            return
        self._hover_resize_handle = None
        self._update_cursor_for_handle(None)

    def on_scroll(self, controller, dx, dy):
        """Handle scroll events for zooming with Ctrl modifier."""
        # Get the current event to check modifiers
        event = controller.get_current_event()
        if event:
            state = event.get_modifier_state()
            ctrl = state & Gdk.ModifierType.CONTROL_MASK

            if ctrl:
                # Zoom in/out
                zoom_factor = 1.1
                if dy < 0:  # Scroll up
                    new_zoom = self._zoom_level * zoom_factor
                else:  # Scroll down
                    new_zoom = self._zoom_level / zoom_factor

                # Clamp zoom level
                self._zoom_level = max(self._min_zoom, min(self._max_zoom, new_zoom))
                self.queue_draw()
                return True
        return False

    def on_drag_begin(self, gesture, start_x, start_y):
        # Ensure geometry is calculated before any drag logic
        self._calculate_image_display_geometry()
        handle = self._hit_test_resize_handle(start_x, start_y)
        if handle and self.processor.current_image:
            self._active_resize_handle = handle
            self._resize_start_pointer = (start_x, start_y)
            self._resize_start_size = (
                self.processor.current_image.get_width(),
                self.processor.current_image.get_height(),
            )
            self._resize_anchor = self._anchor_for_handle(handle)
            self._canvas_resize_in_progress = True
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            return

        if self.processor._is_cropping:
            sel_x, sel_y, sel_w, sel_h = self.processor._selection_box
            p1 = self._image_to_canvas_coords(sel_x, sel_y)
            p2 = self._image_to_canvas_coords(sel_x + sel_w, sel_y + sel_h)
            if p1 and p2 and p1[0] <= start_x <= p2[0] and p1[1] <= start_y <= p2[1]:
                self._drag_mode = "move_crop_image"
                self._drag_start_offset = (start_x, start_y)
                self._start_pan_offset = self.processor._crop_pan_offset
                return

        # If we are already editing text, clicking outside should commit it.
        # But drag begin might be the start of a new text box.
        if self._text_entry:
            self._finalize_text_entry()

        self.hide_text_entry()
        self._start_point = (start_x, start_y)
        current_tool = self.manager.current_tool

        if current_tool == "text":
            self._drag_mode = "text_create"
            self.selection_box = None
            return

        if current_tool == "select":
            if self.processor._floating_selection_data:
                # Check if drag starts inside the floating selection
                f_pos = self.processor._floating_selection_position
                f_w = self.processor._floating_selection_data.get_width()
                f_h = self.processor._floating_selection_data.get_height()

                # Scale floating box to widget coords
                w_coords = self._image_to_canvas_coords(f_pos[0], f_pos[1])
                w_coords2 = self._image_to_canvas_coords(f_pos[0] + f_w, f_pos[1] + f_h)

                if (
                    w_coords
                    and w_coords2
                    and w_coords[0] <= start_x <= w_coords2[0]
                    and w_coords[1] <= start_y <= w_coords2[1]
                ):
                    self._drag_mode = "move"
                    self._drag_start_offset = (
                        start_x - w_coords[0],
                        start_y - w_coords[1],
                    )
                else:
                    # Clicked outside, so paste and start new selection
                    self.processor.paste_selection()
                    self._drag_mode = "select"

            elif self.processor._selection_box:
                # Check if drag starts inside existing selection box
                sel_x, sel_y, sel_w, sel_h = self.processor._selection_box
                p1 = self._image_to_canvas_coords(sel_x, sel_y)
                p2 = self._image_to_canvas_coords(sel_x + sel_w, sel_y + sel_h)

                if (
                    p1
                    and p2
                    and p1[0] <= start_x <= p2[0]
                    and p1[1] <= start_y <= p2[1]
                ):
                    # Cut selection to make it floating
                    self.processor.cut_selection(self.processor._selection_box)
                    self._drag_mode = "move"

                    # p1 is canvas coord of selection top-left
                    self._drag_start_offset = (
                        start_x - p1[0],
                        start_y - p1[1],
                    )
                    self.queue_draw()
                else:
                    self._drag_mode = "select"

            else:
                self._drag_mode = "select"

        elif current_tool == "brush":
            self._drag_mode = "brush"
            self._stroke_points = []
            scaled_point = self._canvas_to_image_coords(start_x, start_y)
            if scaled_point:
                self.processor.start_drawing()
                self._stroke_points.append(scaled_point)

    def on_drag_update(self, gesture, offset_x, offset_y):
        # Ensure geometry is calculated before drag updates
        self._calculate_image_display_geometry()
        # Normalize the offsets based on the current scale
        if self._canvas_resize_in_progress:
            self._apply_canvas_resize(offset_x, offset_y)
            return

        if not self._start_point:
            # This can happen if drag mode is move_crop_image
            if self._drag_mode != "move_crop_image":
                return

        result = gesture.get_offset()
        if isinstance(result, tuple):
            if len(result) == 3:
                success, offset_x, offset_y = result
                if not success:
                    return
            elif len(result) == 2:
                offset_x, offset_y = result
        else:
            return

        start_x, start_y = (
            self._start_point if self._start_point else self._drag_start_offset
        )

        if self._drag_mode == "select" or self._drag_mode == "text_create":
            x1 = min(start_x, start_x + offset_x)
            y1 = min(start_y, start_y + offset_y)
            x2 = max(start_x, start_x + offset_x)
            y2 = max(start_y, start_y + offset_y)
            self.selection_box = (x1, y1, x2 - x1, y2 - y1)
            self.queue_draw()

        elif self._drag_mode == "move":
            new_widget_x = start_x + offset_x - self._drag_start_offset[0]
            new_widget_y = start_y + offset_y - self._drag_start_offset[1]

            scaled_pos = self._canvas_to_image_coords(new_widget_x, new_widget_y)
            if scaled_pos:
                self.processor.move_floating_selection(scaled_pos[0], scaled_pos[1])
                self.queue_draw()

        elif self._drag_mode == "move_crop_image":
            start_pan_x, start_pan_y = self._start_pan_offset
            drag_start_x, drag_start_y = self._drag_start_offset
            dx = (drag_start_x + offset_x) - drag_start_x
            dy = (drag_start_y + offset_y) - drag_start_y

            if self._image_display_rect:
                scale = self._image_display_rect[4]
                if scale > 0:
                    img_dx = dx / scale
                    img_dy = dy / scale
                    self.processor._crop_pan_offset = (
                        start_pan_x + img_dx,
                        start_pan_y + img_dy,
                    )
                    self.queue_draw()

        elif self._drag_mode == "brush":
            end_x = start_x + offset_x
            end_y = start_y + offset_y
            scaled_point = self._canvas_to_image_coords(end_x, end_y)
            if scaled_point:
                self._stroke_points.append(scaled_point)
                if len(self._stroke_points) > 1:
                    self.processor.draw_brush_stroke(self._stroke_points[-2:])
                    self.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
        if self._canvas_resize_in_progress:
            self._canvas_resize_in_progress = False
            self._active_resize_handle = None
            self._resize_start_pointer = None
            self._resize_start_size = None
            self._update_cursor_for_handle(self._hover_resize_handle)
            return

        if self._drag_mode == "text_create" and self.selection_box:
            scaled_selection = self.get_scaled_selection()
            if scaled_selection:
                # Show text entry at the selected area
                self.show_text_entry(*scaled_selection)
            self.selection_box = None
            self._drag_mode = "none"
            self.queue_draw()
            return

        if self._drag_mode == "select" and self.selection_box:
            scaled_selection = self.get_scaled_selection()
            if scaled_selection and scaled_selection[2] > 0 and scaled_selection[3] > 0:
                # For select tool, we just define the selection area.
                # Any existing floating selection is pasted in on_drag_begin.
                if self.processor._is_cropping:
                    self.processor.cancel_crop()

                self.processor.paste_selection()
                self.processor._selection_box = scaled_selection

            self.selection_box = None

        self._drag_mode = "none"
        self._start_point = None
        self._stroke_points = []
        self.queue_draw()

    def get_scaled_selection(self):
        """Scales the selection box from widget coordinates to image coordinates."""
        if not self.selection_box:
            return None

        # This method is now the source of truth for geometry
        geom = self._calculate_image_display_geometry()
        if not geom or not self.processor.current_image:
            return None

        x_offset, y_offset, _, _, scale = geom

        if scale == 0:
            return None

        x, y, w, h = self.selection_box

        # img_x = (canvas_x - offset) / scale
        img_x1 = (x - x_offset) / scale
        img_y1 = (y - y_offset) / scale
        img_x2 = ((x + w) - x_offset) / scale
        img_y2 = ((y + h) - y_offset) / scale

        # Clamp to image boundaries
        img_w, img_h = (
            self.processor.current_image.get_width(),
            self.processor.current_image.get_height(),
        )
        img_x1 = max(0, min(img_x1, img_w))
        img_y1 = max(0, min(img_y1, img_h))
        img_x2 = max(0, min(img_x2, img_w))
        img_y2 = max(0, min(img_y2, img_h))

        return (int(img_x1), int(img_y1), int(img_x2 - img_x1), int(img_y2 - img_y1))

    def _apply_canvas_resize(self, offset_x, offset_y):
        if not self._resize_start_size or not self._image_display_rect:
            return
        scale = self._image_display_rect[4]
        if scale == 0:
            return
        dx = offset_x / scale
        dy = offset_y / scale
        width, height = self._resize_start_size
        handle = self._active_resize_handle
        new_width = width
        new_height = height
        if handle in ("left", "top-left", "bottom-left"):
            new_width -= dx
        elif handle in ("right", "top-right", "bottom-right"):
            new_width += dx
        if handle in ("top", "top-left", "top-right"):
            new_height -= dy
        elif handle in ("bottom", "bottom-left", "bottom-right"):
            new_height += dy
        new_width = max(1, int(round(new_width)))
        new_height = max(1, int(round(new_height)))
        self.processor.resize_canvas(new_width, new_height, anchor=self._resize_anchor)
        self.queue_draw()

    def on_canvas_pressed(self, gesture, n_press, x, y):
        if not self.processor.current_image:
            return

        image_point = self._canvas_to_image_coords(x, y)

        # Handle selection clearing, but not if we are in crop mode
        if (
            self.processor._selection_box
            and not self.processor._floating_selection_data
            and not self.processor._is_cropping
        ):
            sel_x, sel_y, sel_w, sel_h = self.processor._selection_box
            is_inside_selection = False
            if image_point:
                px, py = image_point
                if sel_x <= px < sel_x + sel_w and sel_y <= py < sel_y + sel_h:
                    is_inside_selection = True

            if not is_inside_selection:
                self.processor._selection_box = None
                self.queue_draw()

        if image_point is None:
            # If click is outside image, paste any floating selection
            if self.processor._floating_selection_data:
                self.processor.paste_selection()
                self.queue_draw()
            return

        if self.manager.current_tool == "text":
            if self._text_entry:
                self._finalize_text_entry()
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        elif self.manager.current_tool == "brush":
            self.processor.draw_brush_dab(image_point)
            self.queue_draw()

    def _canvas_to_image_coords(self, x, y):
        # Ensure geometry is fresh
        if not self._calculate_image_display_geometry():
            return None

        draw_x, draw_y, width, height, scale = self._image_display_rect
        if scale == 0:
            return None

        # Check if inside the displayed image area
        if not (draw_x <= x < draw_x + width and draw_y <= y < draw_y + height):
            return None

        img_x = (x - draw_x) / scale
        img_y = (y - draw_y) / scale

        img_w, img_h = (
            self.processor.current_image.get_width(),
            self.processor.current_image.get_height(),
        )
        if 0 <= img_x < img_w and 0 <= img_y < img_h:
            return (int(round(img_x)), int(round(img_y)))
        return None

    def _image_to_canvas_coords(self, img_x, img_y):
        """Convert image-space coordinates (pixels) to canvas coordinates."""
        if not self._calculate_image_display_geometry():
            return None

        draw_x, draw_y, _, _, scale = self._image_display_rect
        if scale == 0:
            return None
        canvas_x = draw_x + img_x * scale
        canvas_y = draw_y + img_y * scale
        return (canvas_x, canvas_y)

    def _image_box_to_canvas_rect(self, x1, y1, x2, y2):
        """Convert image-space box to canvas rect (x, y, w, h)."""
        p1 = self._image_to_canvas_coords(x1, y1)
        p2 = self._image_to_canvas_coords(x2, y2)
        if not p1 or not p2:
            return None
        return (p1[0], p1[1], p2[0] - p1[0], p2[1] - p1[1])

    def _hit_test_resize_handle(self, x, y):
        if not self._image_display_rect:
            return None
        img_x, img_y, img_w, img_h, _ = self._image_display_rect
        if img_w <= 0 or img_h <= 0:
            return None
        margin = self.RESIZE_HANDLE_MARGIN
        x_min, x_max = img_x, img_x + img_w
        y_min, y_max = img_y, img_y + img_h

        on_left = abs(x - x_min) <= margin
        on_right = abs(x - x_max) <= margin
        on_top = abs(y - y_min) <= margin
        on_bottom = abs(y - y_max) <= margin

        if on_top:
            if on_left:
                return "top-left"
            if on_right:
                return "top-right"
            return "top"
        if on_bottom:
            if on_left:
                return "bottom-left"
            if on_right:
                return "bottom-right"
            return "bottom"
        if on_left:
            return "left"
        if on_right:
            return "right"

        return None

    def _anchor_for_handle(self, handle):
        mapping = {
            "top-left": ("right", "bottom"),
            "top": ("left", "bottom"),
            "top-right": ("left", "bottom"),
            "right": ("left", "top"),
            "bottom-right": ("left", "top"),
            "bottom": ("left", "top"),
            "bottom-left": ("right", "top"),
            "left": ("right", "top"),
        }
        return mapping.get(handle, ("left", "top"))

    def _update_cursor_for_handle(self, handle):
        display = self.get_display()
        if not display:
            return
        cursor_name = None
        if handle in ("top-left", "bottom-right"):
            cursor_name = "nwse-resize"
        elif handle in ("top-right", "bottom-left"):
            cursor_name = "nesw-resize"
        elif handle in ("left", "right"):
            cursor_name = "ew-resize"
        elif handle in ("top", "bottom"):
            cursor_name = "ns-resize"
        cursor = Gdk.Cursor.new_from_name(cursor_name) if cursor_name else None
        self.set_cursor(cursor)

    def _draw_resize_handles(self, cr):
        """Draws the canvas resize handles using Cairo."""
        if not self._image_display_rect or not self.processor.current_image:
            return

        size = self.RESIZE_HANDLE_SIZE
        x, y, w, h, _ = self._image_display_rect

        # Define handle centers
        centers = [
            (x, y),
            (x + w / 2, y),
            (x + w, y),
            (x, y + h / 2),
            (x + w, y + h / 2),
            (x, y + h),
            (x + w / 2, y + h),
            (x + w, y + h),
        ]

        # Draw a thin border around the image canvas
        cr.save()
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.3)
        cr.set_line_width(1)
        cr.rectangle(x, y, w, h)
        cr.stroke()

        # Draw handles (with a slight shadow for visibility)
        for cx, cy in centers:
            # Shadow
            cr.set_source_rgba(0.1, 0.1, 0.1, 0.5)
            cr.rectangle(cx - size / 2 + 1, cy - size / 2 + 1, size, size)
            cr.fill()
            # Fill
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)
            cr.rectangle(cx - size / 2, cy - size / 2, size, size)
            cr.fill()
            # Border
            cr.set_source_rgba(0.1, 0.1, 0.1, 0.8)
            cr.set_line_width(1)
            cr.rectangle(cx - size / 2, cy - size / 2, size, size)
            cr.stroke()
        cr.restore()

    def _apply_text_entry_style(self, color, font_size=20.0):
        """Apply CSS style with the given color to the text entry."""
        if not self._text_entry:
            return

        context = self._text_entry.get_style_context()

        # Remove old provider if we stored it (we didn't store it per instance before,
        # but we should probably manage it better. For now, adding a new one with
        # APPLICATION priority overrides the old one if we keep adding them?
        # No, we should remove the old one.
        # But Gtk.StyleContext.add_provider_for_display adds it globally for the display?
        # Wait, the previous code used add_provider_for_display. That affects ALL widgets.
        # We should use add_provider (for context) for this specific widget.

        provider = _create_text_css_provider(color, font_size)
        context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self._text_entry.add_css_class("canvas-text-overlay")

    def update_text_color(self, color):
        """Update the color of the active text entry."""
        if self._text_entry:
            scale = self._image_display_rect[4] if self._image_display_rect else 1.0
            font_size = self.processor._text_size * scale
            self._apply_text_entry_style(color, font_size)
            self._update_text_entry_size(font_size)

    def _commit_text_entry(self):
        if not self._text_entry or not self.processor:
            return
        text = self._text_entry.get_text().strip()
        if text and self._text_entry_pos:
            x, y = self._text_entry_pos
            self.processor.add_text(text, x, y)
            self.queue_draw()

    def _on_text_focus_out(self, controller, *args):
        """Called when the entry loses focus (via EventControllerFocus 'leave')."""
        self._finalize_text_entry()

    def _on_text_entry_key_press(self, controller, keyval, keycode, state):
        """Finalize text when Enter is pressed without modifiers."""
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK):
                return False
            self._finalize_text_entry()
            return True
        return False

    def _on_text_entry_activate(self, entry):
        """Called when the user presses Enter inside the entry."""
        # For TextView, Enter creates a newline, so we don't finalize on Enter.
        pass

    def _finalize_text_entry(self):
        """Commit text to image and remove the overlay entry."""
        if not self._text_entry:
            return

        buffer = self._text_entry.get_buffer()
        # text = buffer.get_text(start_iter, end_iter, True).strip()
        text = buffer.props.text.strip()

        if text:
            x, y = self._text_entry_pos or (0, 0)
            # Add text to the image (ImageProcessor does the drawing in image coords)
            self.processor.add_text(text, x, y)
            self.queue_draw()

        # Remove and cleanup the GTK entry overlay
        if self._overlay and self._text_entry:
            try:
                self._overlay.remove_overlay(self._text_entry)
            except (AttributeError, TypeError):
                # Handle cases where overlay or text entry is invalid
                pass

        self._text_entry = None
        self._text_entry_pos = None
        self._text_entry_initial_dims = None

    def hide_text_entry(self) -> None:
        """Hides and removes the text entry overlay without committing text."""
        if not self._text_entry:
            return
        # Remove the overlay without adding text to the image
        if self._overlay and self._text_entry:
            try:
                self._overlay.remove_overlay(self._text_entry)
            except (AttributeError, TypeError):
                # Handle cases where overlay or text entry is invalid
                pass
        self._text_entry = None
        self._text_entry_pos = None
        self._text_entry_initial_dims = None

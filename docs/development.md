# Development

## Installation

### 1. Prerequisites (Ubuntu/Debian)

Ensure you have the Python GTK bindings and associated development packages installed:

```
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0
```

### 2. Set-up source code

Clone this repository:

```
git clone https://github.com/konverner/gnome-nano-image-edit
cd gnome-nano-image-edit
```

Create and activate virtual environment for Python:

```
python -m venv .venv
source .venv/bin/activate
```

Install Python dependencies:

```
pip install -e .
```

### 3. Running the Application

Run the main application file:

```
python -m src.main
```

### 4. Build after modifying the source

1. Activate the virtual environment if needed: `source .venv/bin/activate`.
2. Upgrade build tooling: `python -m pip install --upgrade build`.
3. Produce artifacts: `python -m build`.
4. Reinstall the wheel for verification: `python -m pip install --force-reinstall dist/gnome_nano_image_edit-*.whl`.
5. Launch to confirm:
   - From source: `python -m src.main`
   - From the installed wheel: `python -m gnome_nano_image_edit.main`

## Test checklist

This checklist covers core features, stability, and user experience to ensure a smooth release.

### General Functionality
- [ ] Application launches without errors on supported systems.
- [ ] Main window and UI elements (toolbar, header bar, canvas) display correctly.
- [ ] All tool buttons (Select, Crop, Brush, Text) are present and toggle as expected.
- [ ] Keyboard shortcuts (Ctrl+Z, Ctrl+Y, Ctrl+C, Ctrl+X, Ctrl+V) work as described.

### File Operations
- [ ] "Open Image" dialog works and loads PNG/JPEG images.
- [ ] "Save" and "Export" options save images correctly (PNG at minimum).
- [ ] Error dialogs appear for unsupported or corrupted files.

### Editing Tools
- [ ] Select Tool: Can select, move, and paste image regions; transparent area left after move.
- [ ] Crop Tool: Can select and crop image to desired area.
- [ ] Brush Tool: Draws with selected size and color; brush strokes render smoothly.
- [ ] Text Tool: Adds text overlay at any position; text color and font are correct.

### Canvas & Rendering
- [ ] Canvas resizes and zooms (Ctrl+Scroll) as expected.
- [ ] Selection overlays and resize handles display and function correctly.
- [ ] Drag-and-drop for selection and moving works smoothly.

### Undo/Redo & Clipboard
- [ ] Undo/redo stack works for all editing actions.
- [ ] Clipboard operations (copy, cut, paste) function as expected.

### Performance & Stability
- [ ] No memory leaks or crashes during extended use.
- [ ] Large images open, edit, and save without significant lag.
- [ ] Undo/redo does not cause excessive memory usage.

### Edge Cases & Error Handling
- [ ] Handles very small (from 0.1 mb) and very large (up to 8mb) images.
- [ ] Handles rapid tool switching and repeated actions.
- [ ] Graceful handling of invalid user input and file errors.

### Documentation & Packaging
- [ ] README and help/documentation are up to date.
- [ ] All dependencies are listed in requirements.txt.
- [ ] App can be installed and run following documented steps.

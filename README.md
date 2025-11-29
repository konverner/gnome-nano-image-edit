# GNOME Nano Image Edit

# Overview

GNOME Nano Image Edit (GNIE) is a lightweight, minimal image editing utility designed specifically for quick, essential tasks on the GNOME environment. Unlike complex editors like GIMP, GNIE focuses on simple, common operations—making it the ideal tool for fast screen-shot edits, simple cropping, and quick annotations without the distraction of layers or advanced filters.

It is developed using Python and PyGObject (GTK4) to ensure seamless integration and native performance within the Linux ecosystem.

![demo](./docs/assets/demo.png)

# Key Features

Copy & Paste Section: Select a rectangular area and copy its contents (pixel data) to be pasted elsewhere in the image.

Crop Tool: Define a selection rectangle to trim the image to the desired area.

Text Overlay: Add simple, single-color text annotations anywhere on the image.

Brush Overlay: Add brush annotation with selected size and color.

Select and Move: Select an arbitrary section of the image and move it to a new location, leaving a transparent "hole" (or background color) where it originated.

# Technology Stack

Programming Language: Python 3

GUI Framework: PyGObject (GTK4)

Image Processing: pycairo

# Installation (Local Development)

## 1. Prerequisites (Ubuntu/Debian)

Ensure you have the Python GTK bindings and associated development packages installed:


```
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0
pip install pycairo
```

## 2. Running the Application

Clone this repository:

```
git clone https://github.com/konverner/gnome-nano-image-edit
cd gnome-nano-image-edit
```

Run the main application file (assuming it's named gnie.py):

```
python3 gnie.py
```

# Usage

Open: Use the "Open Image" button to load a standard image file (PNG, JPEG).

Select Tool: Choose a tool (Crop, Move, Text) from the toolbar.

Execute:

For Crop/Move, drag on the image to create a selection.

For Text, click on the canvas to place a text entry box.

Save: Use the "Save" or "Export" option to finalize your edits.

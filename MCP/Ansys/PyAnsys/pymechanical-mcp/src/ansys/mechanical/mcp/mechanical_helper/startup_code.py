# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Startup code for PyMechanical persistent Python session.

This module contains helper functions and configurations that are
loaded when the persistent Python session starts.
"""

import base64
from io import BytesIO, TextIOWrapper
import sys

# Set UTF-8 encoding for stdout and stderr to handle Unicode characters
if sys.stdout.encoding != "utf-8":
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Matplotlib is optional; needed only for create_custom_plot
try:
    import matplotlib
    import matplotlib.pyplot as plt

    matplotlib.use("Agg")
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Optional: Try to import PyVista for 3D visualization
try:
    from PIL import Image
    import pyvista as pv

    # Enable off-screen rendering globally
    pv.OFF_SCREEN = True

    # Set a clean default theme
    pv.set_plot_theme("document")

    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False


def save_plot(plotter) -> str:
    """
    Save the PyVista plot to file and return as base64.

    Parameters
    ----------
    plotter : pv.Plotter
        PyVista plotter to save.

    Returns
    -------
    str
        Base64 data URI of the plot.
    """
    if not PYVISTA_AVAILABLE:
        return "Error: PyVista is not available"

    try:
        # Capture screenshot
        img_array = plotter.screenshot(return_img=True, transparent_background=False)

        # Convert to PIL Image
        img = Image.fromarray(img_array)

        # Save to buffer
        buffer = BytesIO()
        img.save(buffer, format="PNG")

        # Seek to beginning before reading
        buffer.seek(0)

        # Encode to base64
        img_base64 = base64.b64encode(buffer.read()).decode("utf-8")

        # Create data URI
        result = f"data:image/png;base64,{img_base64}"

        # Clean up and return
        plotter.close()
        return result
    except Exception as e:
        plotter.close()
        return f"Error in save_plot: {str(e)}"


def save_matplotlib_plot(dpi=150):
    """
    Return the current Matplotlib plot as a base64-encoded PNG image.

    Parameters
    ----------
    dpi : int
        Resolution in dots per inch.

    Returns
    -------
    str
        Base64 data URI of the plot.
    """
    if not MATPLOTLIB_AVAILABLE:
        return "Error: matplotlib is not available"

    buffer = BytesIO()
    plt.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    buffer.seek(0)

    img_base64 = base64.b64encode(buffer.read()).decode("utf-8")
    result = f"data:image/png;base64,{img_base64}"
    plt.close()
    return result


# Print confirmation
if MATPLOTLIB_AVAILABLE:
    print("Matplotlib configured with non-interactive backend (Agg)")
else:
    print("Matplotlib not available (optional: install for custom plots)")
if PYVISTA_AVAILABLE:
    print("PyVista configured for off-screen rendering")
else:
    print("PyVista not available (optional)")

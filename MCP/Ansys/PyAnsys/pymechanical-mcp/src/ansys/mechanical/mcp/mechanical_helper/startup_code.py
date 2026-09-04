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
import os
import sys

# Set UTF-8 encoding for stdout and stderr to handle Unicode characters
if sys.stdout.encoding != "utf-8":
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Configure optional plotting packages only when a plotting helper is called.
# Starting a plotting/VTK stack during the MCP initialize handshake can delay
# clients that never request a custom plot. This environment setting also makes
# user code that imports pyplot use a non-interactive backend in headless hosts.
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")


def _load_matplotlib():
    """Load Matplotlib with the non-interactive backend selected first."""
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        return plt
    except Exception:
        return None


def _load_pyvista():
    """Load PyVista only when a three-dimensional plot is requested."""
    try:
        from PIL import Image
        import pyvista as pv

        pv.OFF_SCREEN = True
        pv.set_plot_theme("document")
        return Image, pv
    except Exception:
        return None, None


def save_plot(plotter) -> str:
    """Save the PyVista plot to file and return as base64.

    Parameters
    ----------
    plotter : pv.Plotter
        PyVista plotter to save.

    Returns
    -------
    str
        Base64 data URI of the plot.
    """
    image_module, _ = _load_pyvista()
    if image_module is None:
        return "Error: PyVista is not available"

    try:
        img_array = plotter.screenshot(return_img=True, transparent_background=False)
        img = image_module.fromarray(img_array)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        plotter.close()
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        plotter.close()
        return f"Error in save_plot: {str(e)}"


def save_matplotlib_plot(dpi=150):
    """Return the current Matplotlib plot as a base64-encoded PNG image.

    Parameters
    ----------
    dpi : int
        Resolution in dots per inch.

    Returns
    -------
    str
        Base64 data URI of the plot.
    """
    plt = _load_matplotlib()
    if plt is None:
        return "Error: matplotlib is not available"

    buffer = BytesIO()
    plt.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.read()).decode("utf-8")
    result = f"data:image/png;base64,{img_base64}"
    plt.close()
    return result

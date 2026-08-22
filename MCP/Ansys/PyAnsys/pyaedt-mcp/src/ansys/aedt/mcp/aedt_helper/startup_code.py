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

"""Startup code for a persistent Python session in PyAEDT-MCP.

This module is executed when a persistent Python session is started
for running user code in the MCP server context.
"""

import base64
from io import BytesIO

try:
    import matplotlib

    # Use non-interactive backend to prevent blocking on plot displays
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import pyvista as pv

    # Enable off-screen rendering globally
    pv.OFF_SCREEN = True
    # Set a clean default theme
    pv.set_plot_theme("document")
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def save_matplotlib_plot(filename="plot.png", return_base64=False, dpi=150):
    """Save a Matplotlib plot to a file and optionally return as base64.

    Uses the current Matplotlib figure.

    Parameters
    ----------
    filename : str, default: ``"plot.png"``
        Output filename.
    return_base64 : bool, default: False
        Whether to return the plot as base64-encoded image data.
    dpi : int,  default: 150
        Resolution in dots per inch.

    Returns
    -------
    str
        File path or base64 data URI.
    """
    if not MATPLOTLIB_AVAILABLE:
        return "Matplotlib is not installed. Cannot save plot."

    if return_base64:
        buffer = BytesIO()
        plt.savefig(buffer, format="PNG", dpi=dpi, bbox_inches="tight")
        buffer.seek(0)
        plt.close()

        img_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        return f"data:image/png;base64,{img_base64}"
    else:
        plt.savefig(filename, dpi=dpi, bbox_inches="tight")
        plt.close()
        return f"Plot saved to {filename}"


def save_pyvista_plot(plotter, filename="plot.png", return_base64=False):
    """
    Save a PyVista plot to a file and optionally return as base64.

    Parameters
    ----------
    plotter : pv.Plotter
        PyVista plotter to save.
    filename : str, default: ``"plot.png"``
        Output filename.
    return_base64 : bool, default: False
        Whether to return the plot as base64-encoded image data.

    Returns
    -------
    str
        File path or base64 data URI.
    """
    if not PYVISTA_AVAILABLE:
        return "PyVista is not available"

    if return_base64 and PIL_AVAILABLE:
        img_array = plotter.screenshot(return_img=True, transparent_background=False)
        plotter.close()

        img = Image.fromarray(img_array)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        img_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        return f"data:image/png;base64,{img_base64}"
    else:
        plotter.screenshot(filename, transparent_background=False)
        plotter.close()
        return f"Plot saved to {filename}"


# Convenience functions for AEDT operations
def get_aedt_version():
    """Get the PyAEDT version."""
    try:
        import ansys.aedt.core as aedt

        return aedt.__version__
    except ImportError:
        return "PyAEDT not available"
    except AttributeError:
        return "Version not available"


def list_aedt_applications():
    """List available AEDT applications."""
    return [
        "Hfss - High-Frequency Structure Simulator",
        "Maxwell2d - 2D Electromagnetic Simulation",
        "Maxwell3d - 3D Electromagnetic Simulation",
        "Q3d - 3D Quasi-Static Extraction",
        "Q2d - 2D Quasi-Static Extraction",
        "Icepak - Thermal Management",
        "Circuit - Circuit Simulation",
        "TwinBuilder - System Modeling",
        "Mechanical - Structural Analysis",
        "Emit - EMI/EMC Analysis",
        "RMXprt - Rotating Machine Design",
        "Hfss3dLayout - High-Speed Electronics Layout",
    ]

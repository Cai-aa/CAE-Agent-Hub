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

"""Sphinx documentation configuration file."""

from datetime import datetime
import os
from pathlib import Path

from ansys_sphinx_theme import ansys_favicon, get_version_match, pyansys_logo_black

from ansys.aedt.mcp import __version__

# Project information
project = "pyaedt-mcp"
copyright = f"(c) {datetime.now().year} Synopsys, Inc. and ANSYS, Inc. All rights reserved"
author = "Synopsys, Inc. and ANSYS, Inc."
release = version = __version__
cname = os.getenv("DOCUMENTATION_CNAME", "aedt-mcp.docs.pyansys.com")
switcher_version = get_version_match(__version__)

REPOSITORY_NAME = "pyaedt-mcp"
USERNAME = "ansys"
BRANCH = "main"

# Select desired logo, theme, and declare the html title
html_logo = pyansys_logo_black
html_theme = "ansys_sphinx_theme"
html_short_title = html_title = "PyAEDT-MCP"

# Favicon
html_favicon = ansys_favicon

# specify the location of your github repository
html_theme_options = {
    "github_url": f"https://github.com/{USERNAME}/{REPOSITORY_NAME}",
    "show_prev_next": False,
    "show_breadcrumbs": True,
    "collapse_navigation": True,
    "use_edit_page_button": True,
    "additional_breadcrumbs": [
        ("PyAnsys", "https://docs.pyansys.com/"),
    ],
    "icon_links": [
        {
            "name": "Support",
            "url": f"https://github.com/{USERNAME}/{REPOSITORY_NAME}/discussions",
            "icon": "fa fa-comment fa-fw",
        },
    ],
    "switcher": {
        "json_url": f"https://{cname}/versions.json",
        "version_match": switcher_version,
    },
    "check_switcher": False,
    "ansys_sphinx_theme_autoapi": {
        "project": project,
    },
}

html_context = {
    "display_github": True,
    "github_user": USERNAME,
    "github_repo": REPOSITORY_NAME,
    "github_version": BRANCH,
    "doc_path": "doc/source",
}

# Sphinx extensions
extensions = [
    "ansys_sphinx_theme.extension.autoapi",
    "numpydoc",
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
]

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pyaedt": ("https://aedt.docs.pyansys.com/version/stable/", None),
}

# numpydoc configuration
numpydoc_show_class_members = False
numpydoc_xref_param_type = True
autosectionlabel_prefix_document = True

numpydoc_validate = True
numpydoc_validation_checks = {
    "GL06",  # Found unknown section
    "GL07",  # Sections are in the wrong order.
    # "GL08",  # The object does not have a docstring
    "GL09",  # Deprecation warning should precede extended summary
    "GL10",  # reST directives {directives} must be followed by two colons
    "SS01",  # No summary found
    "SS02",  # Summary does not start with a capital letter
    # "SS03", # Summary does not end with a period
    "SS04",  # Summary contains heading whitespaces
    # "SS05", # Summary must start with infinitive verb, not third person
    "RT02",  # The first line of the Returns section should contain only the
    # type, unless multiple values are being returned"
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]
html_static_path = ["_static"]

# The suffix(es) of source filenames.
source_suffix = ".rst"

# The master toctree document.
master_doc = "index"


def prepare_jinja_env(jinja_env) -> None:
    """Customize the jinja env.

    Notes
    -----
    See https://jinja.palletsprojects.com/en/3.0.x/api/#jinja2.Environment

    """
    jinja_env.globals["project_name"] = project


autoapi_prepare_jinja_env = prepare_jinja_env

language = "en"

exclude_patterns = [
    "_build",
    "links.rst",
]

suppress_warnings = [
    "toc.not_included",
    "toc.not_readable",
    "autoapi.python_import_resolution",
    "design.fa-build",
]

# make rst_epilog a variable, so you can add other epilog parts to it
rst_epilog = ""
# Read link all targets from file
with Path("links.rst").open() as f:
    rst_epilog += f.read()

linkcheck_exclude_documents = ["404", "changelog"]
linkcheck_ignore = [
    "https://github.com/ansys/pyaedt-mcp/*",
    "https://modelcontextprotocol.io/*",
    "https://www.sphinx-doc.org/*",
]

linkcheck_allowed_redirect = [
    r"https://tox.wiki/",
]

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

latex_documents = [
    (
        master_doc,
        f"{project}-Documentation-{__version__}.tex",
        f"{project} Documentation",
        author,
        "manual",
    ),
]

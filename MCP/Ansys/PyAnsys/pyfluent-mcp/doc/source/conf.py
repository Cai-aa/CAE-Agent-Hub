"""Sphinx documentation configuration file."""

from datetime import datetime
import os
from pathlib import Path

from ansys_sphinx_theme import ansys_favicon, get_version_match, pyansys_logo_black

from ansys.fluent.mcp import __version__

# Project information
project = "pyfluent-mcp"
copyright = f"(c) {datetime.now().year} Synopsys, Inc. and ANSYS, Inc. All rights reserved"
author = "ANSYS, Inc."
release = version = __version__
cname = os.getenv("DOCUMENTATION_CNAME", "fluent-mcp.docs.pyansys.com")
switcher_version = get_version_match(__version__)

REPOSITORY_NAME = "pyfluent-mcp"
USERNAME = "ansys"
BRANCH = "main"

# Select desired logo, theme, and declare the html title
html_logo = pyansys_logo_black
html_theme = "ansys_sphinx_theme"
html_short_title = html_title = "PyFluent-MCP"

# Favicon
html_favicon = ansys_favicon

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
    # "switcher": {
    #     "json_url": f"https://{cname}/versions.json",
    #     "version_match": switcher_version,
    # },
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

extensions = [
    "ansys_sphinx_theme.extension.autoapi",
    "numpydoc",
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "ansys-fluent-core": ("https://fluent.docs.pyansys.com/version/stable/", None),
}

numpydoc_show_class_members = False
numpydoc_xref_param_type = True
autosectionlabel_prefix_document = True

numpydoc_validate = True
numpydoc_validation_checks = {
    "GL08",
    "GL09",
    "GL10",
    "SS01",
    "SS04",
    "RT02",
}

templates_path = ["_templates"]

# Add any paths that contain custom static files.
html_static_path = ["_static"]

source_suffix = ".rst"
master_doc = "index"


def prepare_jinja_env(jinja_env) -> None:
    """Customize the jinja env.

    Parameters
    ----------
    jinja_env : Any
        Jinja environment being configured for Sphinx templates.

    Returns
    -------
    None
        The function completes through its side effects.
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
    "autoapi.python_import_resolution",  # Needed due to autoapi limitations
    "design.fa-build",
]

rst_epilog = ""
with Path("links.rst").open(encoding="utf-8") as f:
    rst_epilog += f.read()

linkcheck_exclude_documents = ["404", "changelog"]
linkcheck_ignore = [
    "https://github.com/ansys/pyansys-common-mcp/*",
    "https://github.com/ansys/pyfluent-mcp/*",
    "https://modelcontextprotocol.io/*",
    "https://www.sphinx-doc.org/*",
]

linkcheck_allowed_redirect = [
    r"https://tox.wiki/",
]

pygments_style = "sphinx"
graphviz_output_format = "png"

latex_documents = [
    (
        master_doc,
        f"{project}-Documentation-{__version__}.tex",
        f"{project} Documentation",
        author,
        "manual",
    ),
]

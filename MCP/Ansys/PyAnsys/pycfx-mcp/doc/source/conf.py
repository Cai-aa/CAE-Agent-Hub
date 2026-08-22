"""Sphinx documentation configuration file."""

from datetime import datetime
import os
from pathlib import Path

from ansys_sphinx_theme import ansys_favicon, get_version_match, pyansys_logo_black

try:
    from ansys.cfx.mcp import __version__
except ImportError:
    __version__ = "0.1.0"

project = "pycfx-mcp"
copyright = f"(c) {datetime.now().year} Synopsys, Inc. and ANSYS, Inc. All rights reserved"
author = "Synopsys, Inc. and ANSYS, Inc."
release = version = __version__
switcher_version = get_version_match(__version__)

REPOSITORY_NAME = "pycfx-mcp"
USERNAME = "ansys"
BRANCH = "main"

html_logo = pyansys_logo_black
html_theme = "ansys_sphinx_theme"
html_short_title = html_title = "PyCFX-MCP"
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
            "url": f"https://github.com/{USERNAME}/{REPOSITORY_NAME}/issues",
            "icon": "fa fa-comment fa-fw",
        },
    ],
    "ansys_sphinx_theme_autoapi": {
        "project": project,
    },
}

if os.getenv("DOCUMENTATION_HAS_VERSION_SWITCHER"):
    cname = os.getenv("DOCUMENTATION_CNAME", "cfx-mcp.docs.pyansys.com")
    html_theme_options["switcher"] = {
        "json_url": f"https://{cname}/versions.json",
        "version_match": switcher_version,
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
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "ansys-cfx-core": ("https://cfx.docs.pyansys.com/version/stable/", None),
}

numpydoc_show_class_members = False
numpydoc_xref_param_type = True
autosectionlabel_prefix_document = True
numpydoc_validate = True
numpydoc_validation_checks = {
    "GL09",
    "GL10",
    "SS01",
    "SS04",
    "RT02",
}

templates_path = ["_templates"]
html_static_path = ["_static"]
source_suffix = ".rst"
master_doc = "index"
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

rst_epilog = ""
links = Path("links.rst")
if links.exists():
    rst_epilog += links.read_text(encoding="utf-8")

linkcheck_exclude_documents: list[str] = []
linkcheck_ignore = [
    "https://github.com/ansys/pyansys-common-mcp/*",
    "https://github.com/ansys/pycfx-mcp/*",
    "https://modelcontextprotocol.io/*",
    "https://www.sphinx-doc.org/*",
]

linkcheck_allowed_redirect = [
    r"https://tox.wiki/",
]

pygments_style = "sphinx"
graphviz_output_format = "png"


def prepare_jinja_env(jinja_env) -> None:
    """Customize the jinja env.

    Notes
    -----
    See https://jinja.palletsprojects.com/en/3.0.x/api/#jinja2.Environment

    """
    jinja_env.globals["project_name"] = project


autoapi_prepare_jinja_env = prepare_jinja_env
autoapi_member_order = "alphabetical"

# Use the booktabs table style without ``colorrows``. The default Sphinx
# ``colorrows`` style manipulates colortbl's ``\CT@everycr`` in a way that
# recurses infinitely with current MiKTeX/TeX Live ``colortbl``, causing a
# "TeX capacity exceeded [input stack size]" fatal error during ``pdflatex``.
latex_table_style = ["booktabs"]

latex_elements = {
    "preamble": r"""
\DeclareUnicodeCharacter{2190}{\ensuremath{\leftarrow}}
\DeclareUnicodeCharacter{2192}{\ensuremath{\rightarrow}}
\DeclareUnicodeCharacter{2194}{\ensuremath{\leftrightarrow}}
\DeclareUnicodeCharacter{00B1}{\ensuremath{\pm}}
\DeclareUnicodeCharacter{00D7}{\ensuremath{\times}}
\DeclareUnicodeCharacter{221A}{\ensuremath{\sqrt{}}}
\DeclareUnicodeCharacter{221E}{\ensuremath{\infty}}
\DeclareUnicodeCharacter{2208}{\ensuremath{\in}}
\DeclareUnicodeCharacter{2209}{\ensuremath{\notin}}
\DeclareUnicodeCharacter{2229}{\ensuremath{\cap}}
\DeclareUnicodeCharacter{222A}{\ensuremath{\cup}}
\DeclareUnicodeCharacter{2248}{\ensuremath{\approx}}
\DeclareUnicodeCharacter{2260}{\ensuremath{\neq}}
\DeclareUnicodeCharacter{2264}{\ensuremath{\leq}}
\DeclareUnicodeCharacter{2265}{\ensuremath{\geq}}
""",
}

latex_documents = [
    (
        master_doc,
        f"{project}-Documentation-{__version__}.tex",
        f"{project} Documentation",
        author,
        "manual",
    ),
]

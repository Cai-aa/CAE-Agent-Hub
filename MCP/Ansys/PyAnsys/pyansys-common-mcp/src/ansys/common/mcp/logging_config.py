# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
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

"""Logging configuration for PyAnsys MCP servers.

This module provides centralized logging configuration that ensures
log messages are properly routed to stderr (not stdout) to avoid
interfering with the MCP protocol on stdio transport.
"""

import logging
import os
import sys
from typing import Optional


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """Configure logging for MCP servers.

    This method sets up logging to stderr (to avoid interfering with MCP protocol on stdout)
    and optionally to a file. You can control the log level using the ``LOGLEVEL``
    environment variable or the ``level`` parameter.

    Parameters
    ----------
    level : str, default: None
        Log level. Options are ``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``
        and, ``"CRITICAL"``. In ``None``, the ``LOGLEVEL`` environment variable is
        used or it defaults to ``"INFO"``.
    log_file : str, default: None
        Path to the log file. If a path is provided, logs are written to both
        stderr and the specified file.
    format_string : str, default: None
        Custom format string for log messages. If ``None``, the default format is used.

    Returns
    -------
    logging.Logger
        Root logger instance.

    Examples
    --------
    Basic setup (logs to stderr):

    >>> from ansys.common.mcp.logging_config import setup_logging
    >>> logger = setup_logging()
    >>> logger.info("Server starting...")

    With file output:

    >>> logger = setup_logging(level="DEBUG", log_file="server.log")

    Using environment variable:

    >>> # Set LOGLEVEL=DEBUG before running
    >>> logger = setup_logging()

    Notes
    -----
    - Logs are sent to stderr, NOT stdout. stdout is reserved for MCP protocol.
    - If logs went to stdout, it would break the MCP protocol and cause client
      communication to fail.
    - The ``LOGLEVEL`` environment variable can be used to set the log level.
    - The root logger is configured, so all loggers in your application use this configuration.

    """
    # Determine log level
    if level is None:
        level = os.getenv("LOGLEVEL", "INFO").upper()
    else:
        level = level.upper()

    # Validate log level
    numeric_level = getattr(logging, level, None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")

    # Default format string
    if format_string is None:
        format_string = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(format_string)

    # Stderr handler (always present)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(numeric_level)
    stderr_handler.setFormatter(formatter)
    root_logger.addHandler(stderr_handler)

    # File handler (optional)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            root_logger.info(f"Logging to file: {log_file}")
        except Exception as e:
            root_logger.warning(f"Failed to setup file logging to {log_file}: {e}")

    root_logger.debug(f"Logging configured at level: {level}")

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name.

    This is a convenience wrapper around ``logging.getLogger()`` that ensures
    logging has been configured. If ``setup_logging()`` hasn't been called,
    it is called with default settings.

    Parameters
    ----------
    name : str
        Logger name (typically __name__ of the calling module).

    Returns
    -------
    logging.Logger
        Logger instance.

    Examples
    --------
    >>> from ansys.common.mcp.logging_config import get_logger
    >>> logger = get_logger(__name__)
    >>> logger.info("Processing request...")

    """
    # Check if root logger has handlers
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        # Setup with defaults if not already configured
        setup_logging()

    return logging.getLogger(name)

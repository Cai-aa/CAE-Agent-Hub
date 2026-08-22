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

"""Tests for logging_config module."""

import logging
import os
from pathlib import Path
import sys
import tempfile

import pytest

from ansys.common.mcp.logging_config import get_logger, setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_uses_stderr(self):
        """Test that setup_logging routes to stderr (critical for MCP protocol)."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        logger = setup_logging()

        # Must use stderr, not stdout (MCP protocol uses stdout)
        stderr_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and h.stream == sys.stderr
        ]
        assert len(stderr_handlers) > 0, "Logging must go to stderr for MCP compatibility"

    def test_setup_logging_respects_level(self):
        """Test setup_logging respects log level parameter."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        logger = setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG

        root_logger.handlers.clear()
        logger = setup_logging(level="ERROR")
        assert logger.level == logging.ERROR

    def test_setup_logging_with_file(self):
        """Test setup_logging with file output."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            logger = setup_logging(log_file=str(log_file))

            # Write a log message
            logger.info("Test message")

            # Check that file exists and contains the message
            assert log_file.exists()
            content = log_file.read_text()
            assert "Test message" in content

            # Clean up file handlers
            for handler in logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    handler.close()

    def test_setup_logging_invalid_level(self):
        """Test setup_logging with invalid log level."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        with pytest.raises(ValueError, match="Invalid log level"):
            setup_logging(level="INVALID")

    def test_setup_logging_environment_variable(self):
        """Test setup_logging respects LOGLEVEL environment variable."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        os.environ["LOGLEVEL"] = "WARNING"
        try:
            logger = setup_logging()
            assert logger.level == logging.WARNING
        finally:
            del os.environ["LOGLEVEL"]


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_basic(self):
        """Test basic get_logger functionality."""
        logger = get_logger("test_module")

        assert logger is not None
        assert logger.name == "test_module"

    def test_get_logger_auto_initializes(self):
        """Test that get_logger automatically initializes logging if needed."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        get_logger("test_module")

        # Root logger should now have handlers
        assert len(root_logger.handlers) > 0

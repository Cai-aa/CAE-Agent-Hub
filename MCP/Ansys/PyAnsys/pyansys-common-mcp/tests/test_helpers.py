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

"""Unit tests for helpers module."""

import queue
import sys
import tempfile

import pytest

from ansys.common.mcp.helpers import PersistentPythonSession, _prepare_repl_code

# ============================================================================
# _prepare_repl_code Unit Tests
# ============================================================================


class TestPrepareReplCode:
    """Unit tests for the _prepare_repl_code pure function."""

    def test_empty_code_returned_unchanged(self):
        assert _prepare_repl_code("") == ""

    def test_flat_code_returned_unchanged(self):
        code = "x = 1\nprint(x)"
        assert _prepare_repl_code(code) == code

    def test_blank_line_inside_block_replaced_with_comment(self):
        code = "for i in range(5):\n\n    print(i)"
        result = _prepare_repl_code(code)
        assert "\n\n" not in result
        assert "#" in result

    def test_blank_line_with_spaces_inside_block_replaced(self):
        code = "for i in range(5):\n   \n    print(i)"
        result = _prepare_repl_code(code)
        lines = result.splitlines()
        assert any(line.strip() == "#" for line in lines)

    def test_blank_line_inserted_after_block(self):
        code = "for i in range(5):\n    print(i)\nprint('done')"
        result = _prepare_repl_code(code)
        lines = result.splitlines()
        # A blank line must appear between the end of the block and print('done')
        idx = lines.index("print('done')")
        assert lines[idx - 1] == ""

    def test_trailing_blank_line_inserted_when_ending_on_indented_block(self):
        code = "for i in range(5):\n    print(i)"
        result = _prepare_repl_code(code)
        assert result.endswith("\n")

    def test_no_trailing_blank_line_when_ending_on_flat_code(self):
        code = "for i in range(5):\n    print(i)\nprint('done')"
        result = _prepare_repl_code(code)
        assert not result.endswith("\n\n")

    def test_continuation_keywords_do_not_trigger_extra_blank_line(self):
        code = "if x:\n    pass\nelse:\n    pass"
        result = _prepare_repl_code(code)
        lines = result.splitlines()
        # No blank line should appear before 'else'
        idx = lines.index("else:")
        assert lines[idx - 1] != ""

    def test_nested_blocks_handled(self):
        code = "for i in range(5):\n    if i > 2:\n        print(i)\nprint('done')"
        result = _prepare_repl_code(code)
        assert "print('done')" in result
        # Blank line must appear before 'print('done')'
        lines = result.splitlines()
        idx = lines.index("print('done')")
        assert lines[idx - 1] == ""

    def test_comment_lines_preserved_as_is(self):
        code = "# a comment\nx = 1"
        result = _prepare_repl_code(code)
        assert result.startswith("# a comment")

    def test_only_single_blank_line_inserted_not_double(self):
        """append('') joined with '\\n' must produce exactly one blank line, not two."""
        code = "for i in range(5):\n    print(i)\nprint('done')"
        result = _prepare_repl_code(code)
        assert "\n\n\n" not in result


# ============================================================================
# PersistentPythonSession Unit Tests
# ============================================================================


class TestPersistentPythonSessionInitialization:
    """Test suite for PersistentPythonSession initialization and configuration.

    Tests that sessions are correctly initialized with various parameters.
    """

    def test_default_initialization(self):
        """Test that default initialization sets correct values."""
        session = PersistentPythonSession()

        assert session.python_executable == sys.executable
        assert session.startup_code is None
        assert session.working_directory is None
        assert session.process is None
        assert not session._is_running
        assert session.metadata == {}

    def test_custom_python_executable(self):
        """Test initialization with custom python executable path."""
        executable = "/custom/python"
        session = PersistentPythonSession(python_executable=executable)

        assert session.python_executable == executable

    def test_startup_code_parameter(self):
        """Test initialization with startup code."""
        startup_code = "import numpy as np\nx = 42"
        session = PersistentPythonSession(startup_code=startup_code)

        assert session.startup_code == startup_code

    def test_working_directory_parameter(self):
        """Test initialization with working directory."""
        work_dir = "/tmp/workspace"
        session = PersistentPythonSession(working_directory=work_dir)

        assert session.working_directory == work_dir

    def test_all_required_attributes_exist(self):
        """Test that all required attributes are properly initialized."""
        session = PersistentPythonSession()

        # Verify all attributes exist
        assert hasattr(session, "python_executable")
        assert hasattr(session, "startup_code")
        assert hasattr(session, "working_directory")
        assert hasattr(session, "process")
        assert hasattr(session, "_output_thread")
        assert hasattr(session, "_error_thread")
        assert hasattr(session, "_output_queue")
        assert hasattr(session, "_error_queue")
        assert hasattr(session, "_is_running")
        assert hasattr(session, "_execution_lock")
        assert hasattr(session, "metadata")

        # Verify queue types
        assert isinstance(session._output_queue, queue.Queue)
        assert isinstance(session._error_queue, queue.Queue)


class TestPersistentPythonSessionBasicOperations:
    """Test suite for basic PersistentPythonSession operations.

    Tests basic operations that don't require actual subprocess execution.
    """

    def test_is_running_initial_state(self):
        """Test that is_running() returns False for new session."""
        session = PersistentPythonSession()
        assert not session.is_running()

    def test_stop_when_not_running(self):
        """Test that stop() returns error when session is not running."""
        session = PersistentPythonSession()

        result = session.stop()

        assert not result["success"]
        assert "not running" in result.get("error", "").lower()

    def test_execute_without_starting(self):
        """Test that execute() returns error when session is not running."""
        session = PersistentPythonSession()

        result = session.execute("x = 1")

        assert not result["success"]
        assert "not running" in result.get("error", "").lower()

    def test_execute_result_structure(self):
        """Test that execute() returns properly structured result dict."""
        session = PersistentPythonSession()

        result = session.execute("x = 1")

        assert isinstance(result, dict)
        assert "success" in result
        assert "stdout" in result
        assert "stderr" in result
        assert "error" in result


class TestPersistentPythonSessionMetadata:
    """Test suite for metadata handling in PersistentPythonSession.

    Tests that metadata can be stored and retrieved correctly.
    """

    def test_metadata_initialization(self):
        """Test that metadata is initialized as empty dict."""
        session = PersistentPythonSession()
        assert session.metadata == {}
        assert isinstance(session.metadata, dict)

    def test_metadata_modification(self):
        """Test that metadata can be modified and retrieved."""
        session = PersistentPythonSession()

        session.metadata["key1"] = "value1"
        session.metadata["key2"] = {"nested": "value"}

        assert session.metadata["key1"] == "value1"
        assert session.metadata["key2"]["nested"] == "value"

    def test_metadata_isolation(self):
        """Test that metadata is isolated between different session instances."""
        session1 = PersistentPythonSession()
        session2 = PersistentPythonSession()

        session1.metadata["key"] = "session1"

        assert "key" not in session2.metadata


class TestPersistentPythonSessionInternalMethods:
    """Test suite for internal methods of PersistentPythonSession.

    Tests internal helper methods used by the session.
    """

    def test_drain_queues(self):
        """Test that _drain_queues successfully clears pending output."""
        session = PersistentPythonSession()

        # Add items to output queue
        session._output_queue.put("line1")
        session._output_queue.put("line2")

        # Drain should remove items
        session._drain_queues(timeout=0.5)

        # Queue should be empty
        try:
            session._output_queue.get_nowait()
            empty = False
        except queue.Empty:
            empty = True

        assert empty

    def test_read_stream_callable(self):
        """Test that _read_stream method exists and is callable."""
        session = PersistentPythonSession()
        assert callable(session._read_stream)

    def test_execution_lock_exists(self):
        """Test that execution lock is initialized for thread safety."""
        session = PersistentPythonSession()

        assert hasattr(session, "_execution_lock")
        assert session._execution_lock is not None

    def test_lock_can_be_acquired(self):
        """Test that execution lock can be acquired and released."""
        session = PersistentPythonSession()

        # Verify the lock can be acquired
        acquired = session._execution_lock.acquire(blocking=False)
        if acquired:
            session._execution_lock.release()
            assert True
        else:
            assert False, "Lock could not be acquired"


class TestPersistentPythonSessionContextManager:
    """Test suite for context manager functionality.

    Tests that PersistentPythonSession works correctly as a context manager.
    """

    def test_context_manager_basic(self):
        """Test basic context manager usage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = PersistentPythonSession(working_directory=tmpdir)

            with session:
                # Session should be running or attempting to run
                pass

            # After exiting context, session should be stopped
            assert not session.is_running()


class TestPersistentPythonSessionErrorHandling:
    """Test suite for error handling scenarios.

    Tests various error conditions and edge cases.
    """

    def test_invalid_python_executable(self):
        """Test that start() fails gracefully with invalid Python executable."""
        session = PersistentPythonSession(python_executable="/nonexistent/python")

        result = session.start()

        assert not result["success"]
        assert "not found" in result.get("error", "").lower()

    def test_restart_when_not_running(self):
        """Test that restart() works even when session is not running."""
        session = PersistentPythonSession()

        result = session.restart()

        # Should contain proper structure
        assert "success" in result
        assert "error" in result or "message" in result


# ============================================================================
# PersistentPythonSession Integration Tests
# ============================================================================


@pytest.mark.integration
class TestPersistentPythonSessionIntegration:
    """Integration test suite for PersistentPythonSession with actual subprocess execution.

    These tests use real Python subprocesses to verify end-to-end functionality.
    They are marked with @pytest.mark.integration and may take longer to run.
    """

    def test_start_and_stop(self):
        """Test starting and stopping a real Python session."""
        session = PersistentPythonSession()

        # Start session
        result = session.start()
        assert result["success"], f"Failed to start: {result.get('error')}"
        assert session.is_running()

        # Stop session
        result = session.stop()
        assert result["success"], f"Failed to stop: {result.get('error')}"
        assert not session.is_running()

    def test_execute_empty_code(self):
        """Test executing an empty Python code snippet in session."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Execute simple assignment
            result = session.execute("")
            assert result["success"], f"Execution failed: {result.get('error')}"
            assert isinstance(result["stdout"], str)
        finally:
            session.stop()

    def test_execute_simple_code(self):
        """Test executing simple Python code in session."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Execute simple assignment
            result = session.execute("x = 42")
            assert result["success"], f"Execution failed: {result.get('error')}"
            assert isinstance(result["stdout"], str)
        finally:
            session.stop()

    def test_execute_with_output(self):
        """Test executing code that produces stdout output."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Execute code that prints
            result = session.execute("print('hello world')")
            assert result["success"], f"Execution failed: {result.get('error')}"
            assert "hello world" in result["stdout"]
        finally:
            session.stop()

    def test_state_persistence(self):
        """Test that session maintains state across multiple executions."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Define a variable
            result1 = session.execute("x = 100")
            assert result1["success"], f"First execution failed: {result1.get('error')}"

            # Use that variable in next execution
            result2 = session.execute("y = x + 50")
            assert result2["success"], f"Second execution failed: {result2.get('error')}"

            # Check the result
            result3 = session.execute("print(y)")
            assert result3["success"], f"Third execution failed: {result3.get('error')}"
            assert "150" in result3["stdout"]
        finally:
            session.stop()

    def test_execute_with_error(self):
        """Test executing code that produces a runtime error is properly caught."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Execute code that raises an error
            result = session.execute("1/0")
            assert not result["success"], "Error should be caught"
            assert result["stderr"], "stderr should contain error info"
            assert "error" in result["stderr"].lower() or "exception" in result["stderr"].lower()
        finally:
            session.stop()

    def test_execute_with_syntax_error(self):
        """Test executing code with syntax error is properly caught."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Execute code with syntax error
            result = session.execute("if True print('bad syntax')")
            assert not result["success"], "Syntax error should be caught"
            assert result["stderr"], "stderr should contain error info"
        finally:
            session.stop()

    def test_execute_multiline_with_error(self):
        """Test executing multiline code where error occurs mid-execution."""
        session = PersistentPythonSession()

        try:
            session.start()

            code = """
x = 10
y = 20
z = x / 0
print('hello')
"""
            result = session.execute(code)
            assert not result["success"], "Error should be caught"
            assert "ZeroDivisionError" in result["stderr"] or "division by zero" in result["stderr"]
        finally:
            session.stop()

    def test_execute_with_error_no_primary_prompt(self):
        """Test runtime error is properly reported without the primary prompt."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Execute code that raises an error
            result = session.execute("print(1)\nprint(2)\nprint(3)\nif True print(i)")
            assert not result["success"], "Error should be caught"
            assert result["stderr"], "stderr should contain error info"
            assert "error" in result["stderr"].lower() or "exception" in result["stderr"].lower()
            assert ">>>" not in result["stderr"]
        finally:
            session.stop()

    def test_execute_with_error_no_secondary_prompt(self):
        """Test runtime error is properly reported without the secondary prompt."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Execute code that raises an error
            result = session.execute("for i in range(1, 5):\n   if True print(i)")
            assert not result["success"], "Error should be caught"
            assert result["stderr"], "stderr should contain error info"
            assert "error" in result["stderr"].lower() or "exception" in result["stderr"].lower()
            assert "..." not in result["stderr"]
        finally:
            session.stop()

    def test_with_startup_code(self):
        """Test session with startup code that runs on initialization."""
        startup_code = "import math\nPI = 3.14159"
        session = PersistentPythonSession(startup_code=startup_code)

        try:
            result = session.start()
            assert result["success"], f"Failed to start: {result.get('error')}"

            # Verify startup code was executed
            check_result = session.execute("print(PI)")
            assert check_result["success"], f"Execution failed: {check_result.get('error')}"
            assert "3.14159" in check_result["stdout"]
        finally:
            session.stop()

    def test_context_manager_with_execution(self):
        """Test session usage as a context manager with code execution."""
        with PersistentPythonSession() as session:
            assert session.is_running()

            result = session.execute("print('context manager test')")
            assert result["success"], f"Execution failed: {result.get('error')}"
            assert "context manager test" in result["stdout"]

        # After exiting context, session should be stopped
        assert not session.is_running()

    def test_restart_functionality(self):
        """Test restarting a session clears state and re-runs startup code."""
        session = PersistentPythonSession(startup_code="x = 10")

        try:
            # Start and verify startup code ran
            session.start()
            result1 = session.execute("print(x)")
            assert result1["success"], f"First execution failed: {result1.get('error')}"
            assert "10" in result1["stdout"]

            # Modify the variable
            session.execute("x = 999")

            # Verify modification
            result1 = session.execute("print(x)")
            assert result1["success"], f"First execution failed: {result1.get('error')}"
            assert "999" in result1["stdout"]

            # Restart session
            restart_result = session.restart()
            assert restart_result["success"], f"Restart failed: {restart_result.get('error')}"
            assert session.is_running()

            # Startup code should have run again, resetting x to 10
            result2 = session.execute("print(x)")
            assert result2["success"], f"Second execution failed: {result2.get('error')}"
            assert "10" in result2["stdout"]
        finally:
            if session.is_running():
                session.stop()

    def test_multiple_sequential_executions(self):
        """Test running multiple commands sequentially in the same session."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Run multiple commands
            for i in range(5):
                result = session.execute(f"print({i})")
                assert result["success"], f"Execution {i} failed: {result.get('error')}"
                assert str(i) in result["stdout"]
        finally:
            session.stop()

    def test_with_one_indented_code_block(self):
        """Test running code with an indented block."""
        session = PersistentPythonSession()

        try:
            session.start()

            code = """\
for i in range(1,5):
    print(i)
print('done')
"""
            result = session.execute(code)

            assert result["success"], f"Execution failed: {result.get('error')}"

            expected_result = """\
1
2
3
4
done"""
            assert expected_result in result["stdout"]
        finally:
            session.stop()

    def test_ending_with_one_indented_code_block(self):
        """Test running code with an indented block."""
        session = PersistentPythonSession()

        try:
            session.start()

            code = """\
for n in range(1, 5):
    if n % 2 == 0:
        continue
    print(n)"""
            result = session.execute(code)

            assert result["success"], f"Execution failed: {result.get('error')}"

            expected_result = """\
1
3"""
            assert expected_result in result["stdout"]
        finally:
            session.stop()

    def test_with_nested_indented_code_blocks(self):
        """Test running code with multiple nested and indented blocks."""
        session = PersistentPythonSession()

        try:
            session.start()

            code = """\
for i in range(1,5):
    if i > 3:
        print(i)
    else:
        for j in range(1, i):
            print(j)
print('done')
"""
            result = session.execute(code)

            assert result["success"], f"Execution failed: {result.get('error')}"

            expected_result = """\
1
1
2
4
done"""
            assert expected_result in result["stdout"]
        finally:
            session.stop()

    def test_with_blank_lines_in_indented_blocks(self):
        """Test running code with multiple nested blocks that include blank lines."""
        session = PersistentPythonSession()

        try:
            session.start()

            code = """\
for i in range(1,5):
    if i > 3:

        print(i)

    else:
        for j in range(1, i):

            print(j)
print('done')
"""
            result = session.execute(code)

            assert result["success"], f"Execution failed: {result.get('error')}"

            expected_result = """\
1
1
2
4
done"""
            assert expected_result in result["stdout"]
        finally:
            session.stop()

    def test_ending_with_deep_nested_code_blocks(self):
        """Test running code ending on a deeply indented section."""
        session = PersistentPythonSession()

        try:
            session.start()

            code = """\
for i in range(1,5):
    if i % 2 == 0:
        if i > 1:
            if i == 2:
                print(2)
"""
            result = session.execute(code)

            assert result["success"], f"Execution failed: {result.get('error')}"

            expected_result = "2"
            assert expected_result in result["stdout"]
        finally:
            session.stop()

    def test_repeated_indented_code_blocks(self):
        """Test running code with an indented block."""
        session = PersistentPythonSession()

        try:
            session.start()

            code = """\
for n in range(1, 5):
    if n % 2 == 0:
        continue
    print(n)
for n in range(1, 5):
    if n % 2 == 0:
        if n % 2 == 0:
            if n % 2 == 0:
                if n % 2 == 0:
                    continue
    print(2*n)


for n in range(1, 5):
    if n % 2 == 0:

        continue

    print(3*n)
for n in range(1, 5):
    if n % 2 == 0:
        continue
    print(4*n)"""

            result = session.execute(code)

            assert result["success"], f"Execution failed: {result.get('error')}"

            expected_result = """\
1
3
2
6
3
9
4
12"""
            assert expected_result in result["stdout"]
        finally:
            session.stop()

    def test_indented_code_blocks_with_continuations(self):
        """Test running code with indented blocks containing else|elif|except|finally."""
        session = PersistentPythonSession()

        try:
            session.start()

            code = """\
n = 5
score = 85

if n % 2 == 0:
    print(f"{n} is even")
else:
    print(f"{n} is odd")
try:
    result = 10 / 0
except ZeroDivisionError:
    print("Error: divide by zero!")
finally:
    print("finally")
if score >= 90:
    print("Grade: A")
elif score >= 80:
    print("Grade: B")
elif score >= 70:
    print("Grade: C")
else:
    print("Grade: F")"""

            result = session.execute(code)

            assert result["success"], f"Execution failed: {result.get('error')}"

            expected_result = """\
5 is odd
Error: divide by zero!
finally
Grade: B"""
            assert expected_result in result["stdout"]
        finally:
            session.stop()

    def test_metadata_persistence_across_executions(self):
        """Test that metadata persists across code executions."""
        session = PersistentPythonSession()
        session.metadata["test_key"] = "test_value"

        try:
            session.start()
            result = session.execute("x = 1")
            assert result["success"], f"Execution failed: {result.get('error')}"

            # Metadata should still be accessible
            assert session.metadata["test_key"] == "test_value"
        finally:
            session.stop()

    def test_stderr_collection_after_marker(self):
        """Test that stderr is properly collected even after marker is found."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Execute code that writes to stderr after printing
            code = """
import sys
print('stdout message')
sys.stderr.write('stderr message\\n')
"""
            result = session.execute(code)
            assert result["success"], f"Execution failed: {result.get('error')}"
            assert "stdout message" in result["stdout"]
            assert "stderr message" in result["stderr"]
        finally:
            session.stop()

    def test_execute_with_warning(self):
        """Test that Python warnings are captured in stderr."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Generate a deprecation warning
            code = """
import warnings
warnings.warn('This is a test warning', DeprecationWarning)
print('done')
"""
            result = session.execute(code)
            # Warnings go to stderr but shouldn't fail execution
            assert "done" in result["stdout"]
        finally:
            session.stop()

    def test_no_output_timeout_fires_by_default(self):
        """Test that the default no_output_timeout (1.2s) interrupts code with no output."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Sleeps well beyond the default 1.2s idle timeout without producing output
            code = """
import time
time.sleep(3)
print('done')
"""
            result = session.execute(code)

            # Execution should be interrupted before 'done' is printed
            assert "done" not in result["stdout"]

        finally:
            session.stop()

    def test_no_output_timeout_can_be_disabled(self):
        """Test that setting no_output_timeout=None disables the idle check."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Sleeps briefly, but longer than the default 1.2s idle timeout
            code = """
import time
time.sleep(1.4)
print('done')
"""
            # no_output_timeout=None disables the check; rely on the outer timeout instead
            result = session.execute(code, no_output_timeout=None)

            assert "done" in result["stdout"]

        finally:
            session.stop()

    def test_no_output_timeout_custom_value(self):
        """Test that a custom no_output_timeout is respected."""
        session = PersistentPythonSession()

        try:
            session.start()

            # Sleeps longer than the custom timeout but shorter than the default
            code = """
import time
time.sleep(1)
print('done')
"""
            # 0.5s idle timeout should fire before the 1s sleep finishes
            result = session.execute(code, no_output_timeout=0.5)

            assert "done" not in result["stdout"]

        finally:
            session.stop()

    def test_no_output_timeout_invalid_values(self):
        """Test that invalid no_output_timeout values raise ValueError."""
        session = PersistentPythonSession()
        session.start()

        try:
            for bad_value in (0, -1, float("nan"), float("-inf"), "5"):
                with pytest.raises(ValueError, match="no_output_timeout"):
                    session.execute("print('hi')", no_output_timeout=bad_value)
        finally:
            session.stop()

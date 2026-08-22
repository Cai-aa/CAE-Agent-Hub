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

"""Pytest configuration for ansys-common-mcp tests."""

from pathlib import Path
import sys

# Add the examples/src directory to the Python path so that
# examples.src.pyexample_mcp can be imported in tests
examples_src = Path(__file__).parent.parent / "examples" / "src"
if examples_src.exists() and str(examples_src) not in sys.path:
    sys.path.insert(0, str(examples_src))

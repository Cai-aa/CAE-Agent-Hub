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

"""Mock PyExample library for testing purposes.

This module simulates a real Ansys product API to enable end-to-end testing
of the pyansys-common-mcp framework without requiring an actual product installation.
"""

from dataclasses import dataclass, field
import random
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class Model:
    """Represents a model in PyExample."""

    name: str
    model_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "created"

    def __repr__(self) -> str:
        """Return a string representation of the model."""
        return f"Model(name='{self.name}', type='{self.model_type}', status='{self.status}')"


@dataclass
class SimulationResult:
    """Represents simulation results."""

    model_name: str
    status: str
    convergence_iterations: int = 0
    max_stress: float = 0.0
    displacement: float = 0.0

    def summary(self) -> str:
        """Return a summary of the simulation results."""
        return (
            f"Simulation Results for '{self.model_name}':\n"
            f"  Status: {self.status}\n"
            f"  Convergence Iterations: {self.convergence_iterations}\n"
            f"  Max Stress: {self.max_stress:.2f} MPa\n"
            f"  Max Displacement: {self.displacement:.4f} mm"
        )


class PyExample:
    """Mock PyExample class simulating a real Ansys product.

    This class provides a realistic API surface that mimics common patterns
    found in PyAnsys libraries like PyMAPDL, PyFluent, etc.

    Parameters
    ----------
    mode : str
        Launch mode: 'local', 'remote', or 'grpc'
    timeout : int
        Connection timeout in seconds
    port : Optional[int]
        Port number for connection

    Attributes
    ----------
    version : str
        Version of the PyExample library
    models : Dict[str, Model]
        Dictionary of created models
    active_model : Optional[str]
        Name of the currently active model

    """

    def __init__(
        self,
        mode: str = "local",
        timeout: int = 60,
        port: Optional[int] = None,
    ):
        """Initialize PyExample instance."""
        self.mode = mode
        self.timeout = timeout
        self.port = port or 50052
        self.version = "2026.1.0"
        self.models: Dict[str, Model] = {}
        self.active_model: Optional[str] = None
        self._is_connected = True
        self._command_count = 0

    def __repr__(self) -> str:
        """Return a string representation of the PyExample instance."""
        return f"PyExample(version='{self.version}', mode='{self.mode}')"

    def run_command(self, command: str, **parameters: Any) -> str:
        """Execute a command on a model and return the result.

        Parameters
        ----------
        command : str
            Command string to execute
        **parameters : Any
            Additional model parameters for model creation

        Returns
        -------
        str
            Command execution result

        """
        self._command_count += 1
        command = command.strip()

        if command.startswith("CREATE MODEL"):
            parts = command.split()
            if len(parts) >= 3:
                model_name = parts[2]
                model_type = parts[4] if len(parts) >= 5 else "default"
                self.create_model(name=model_name, model_type=model_type, parameters=parameters)
                return f"Model '{model_name}' created successfully (type: {model_type})"

        elif command.startswith("SOLVE MODEL"):
            parts = command.split()
            if len(parts) >= 3:
                model_name = parts[2]
                if model_name in self.models:
                    self.models[model_name].status = "solved"
                    return f"Model '{model_name}' solved successfully"
                return f"Error: Model '{model_name}' not found"

        elif command.startswith("LIST MODELS"):
            if not self.models:
                return "No models created"
            model_list = "\n".join([f"  - {name}: {model}" for name, model in self.models.items()])
            return f"Models:\n{model_list}"

        elif command == "STATUS":
            output = f"""
PyExample {self.version} - {len(self.models)} models, {self._command_count} commands executed
            """
            return output

        return f"Executed: {command}"

    def create_model(self, name: str, model_type: str = "default", **parameters: Any) -> Model:
        """Create a new model.

        Parameters
        ----------
        name : str
            Model name
        model_type : str
            Type of model to create
        **parameters : Any
            Additional model parameters

        Returns
        -------
        Model
            The created model

        """
        model = Model(name=name, model_type=model_type, parameters=parameters)
        self.models[name] = model
        self.active_model = name
        return model

    def solve(self, model_name: Optional[str] = None) -> SimulationResult:
        """Run a simulation.

        Parameters
        ----------
        model_name : Optional[str]
            Model to solve. If None, uses active model.

        Returns
        -------
        SimulationResult
            Results of the simulation

        """
        target = model_name or self.active_model
        if not target:
            raise ValueError("No model specified or active")

        if target not in self.models:
            raise ValueError(f"Model '{target}' not found")

        model = self.models[target]
        model.status = "solved"

        # Mock simulation results with random values based on model name for consistency
        random.seed(hash(target))  # nosec B311

        result = SimulationResult(
            model_name=target,
            status="converged",
            convergence_iterations=random.randint(5, 15),  # nosec B311
            max_stress=random.uniform(50.0, 500.0),  # nosec B311
            displacement=random.uniform(0.001, 0.1),  # nosec B311
        )

        return result

    def get_model(self, name: str) -> Model:
        """Get a model by name.

        Parameters
        ----------
        name : str
            Model name

        Returns
        -------
        Model
            The requested model

        """
        if name not in self.models:
            raise ValueError(f"Model '{name}' not found")
        return self.models[name]

    def list_models(self) -> List[Model]:
        """List all created models.

        Returns
        -------
        List[Model]
            List of all models

        """
        return list(self.models.values())

    def exit(self):
        """Close the PyExample connection."""
        self._is_connected = False
        self.models.clear()
        self.active_model = None

    @property
    def is_connected(self) -> bool:
        """Check if PyExample is connected."""
        return self._is_connected


def launch_pyexample(
    mode: str = "local",
    timeout: int = 60,
    port: Optional[int] = None,
) -> PyExample:
    """Launch a PyExample instance.

    This function simulates the launcher pattern common in PyAnsys libraries.

    Parameters
    ----------
    mode : str
        Launch mode: 'local', 'remote', or 'grpc'
    timeout : int
        Connection timeout in seconds
    port : Optional[int]
        Port number for connection

    Returns
    -------
    PyExample
        Connected PyExample instance

    """
    return PyExample(mode=mode, timeout=timeout, port=port)

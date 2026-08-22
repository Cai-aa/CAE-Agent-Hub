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

"""INTERCONNECT-specific guideline topics.

Owns every Lumerical INTERCONNECT-flavoured guideline:

- ``interconnect_workflow`` -- chunked build/setup stages for photonic
  circuit simulation: element addition, naming, selection, connection,
  compound elements, and property discovery.
- ``interconnect_simulation`` -- root element simulation configuration
  (time-domain vs. frequency-domain modes, ``"simulation input"``
  selector, ONA frequency-domain workflow), and ``getresult``
  discovery pattern for analyzers.
- ``interconnect_commands`` -- reference of INTERCONNECT-specific lumapi
  commands grouped by category (element library, design kits,
  measurements, scripted elements).
"""

from __future__ import annotations


def get_guidelines_for_interconnect_workflow() -> str:
    """INTERCONNECT-specific build/setup workflow: stages, element management, simulation config."""
    return """# INTERCONNECT Workflow (Build & Setup)

This topic covers the INTERCONNECT-specific **build/setup** workflow
for photonic circuit simulation: the chunked stage list, element
management (adding, naming, selecting, connecting), compact-model
library discovery, property discovery, analyzer/result discovery, and
root-element simulation configuration.

**Read ``workflow`` first** for the generic execution model
(``_lum_get`` / ``_lum_print_json`` helpers), snippet structure,
parameter management, and the "do NOT make assumptions / do NOT
invent or re-run" rules that apply to every Lumerical product.

## INTERCONNECT Build Stages (Chunked)

Follow this order. Each stage is one ``execute_python_code`` snippet:

1. **Parameters** -- declare all user-configurable values (bitrate,
  wavelengths, modulation depth, analyzer settings, bias points,
  etc.) with SI units where applicable.
2. **Discover before configure** -- call ``ic.library()`` and verify
  the exact installed element names before adding anything. For any
  unfamiliar element, inspect its ports and properties before trying
  to wire or configure it. If a required compact model library is
  missing, install the needed ``.cml`` design kit first with
  ``installdesignkit(filename, path, overwrite)``.
3. **Add elements and position them** -- ``addelement`` + immediate
  ``get("name")`` to capture the auto-assigned instance name.
  Immediately set ``"x position"`` and ``"y position"`` on each
  element in the same snippet so elements are never stacked at the origin.
  Verify each ``addelement`` succeeded before proceeding (see "Handling
  addelement Failures" below).
4. **Discover ports and connection roles** -- use ``getports()`` for
  every element to build the connection plan and identify any
  digital-to-electrical bridges needed.
5. **Connect elements** -- wire compatible ports with ``connect()``.
6. **Configure elements and root mode** -- set element properties only
  after confirming the exact property names, active state, and enum
  choices. Set the root element's ``simulation input`` mode before
  configuring time-domain properties that depend on it.
7. **Save** -- ``ic.save(path)``.
8. **Run** -- ``ic.run()`` (only after user confirmation).
9. **Extract results** -- discover dataset names first, then extract
  analyzer outputs and inspect the returned payload before indexing
  into it.

## Element Library Discovery

Use ``library()`` to get a complete list of elements available in
the currently installed element libraries. This returns all
primitive elements (sources, modulators, detectors, analyzers) as
well as any installed foundry PDK elements.

For foundry compact models, **do not assume the user-facing shorthand
matches the installed leaf name**. Lumfoundry-style models often show
up with a ``lum_`` prefix or another library-specific prefix, and the
exact installed spelling varies across design kits. Always search the
current ``library()`` output and use the exact discovered name.

```python
ic = _lum_get("wdm_tx")
lib_list = ic.library()
print(lib_list)
```

## Adding Elements

Use ``addelement("element_name")`` to add an element to the
schematic. The element name must match the **exact** library name
(case-insensitive, but whitespace-sensitive).

**IMPORTANT**: Always call ``ic.library()`` first and verify that the
element name exists in the output before calling ``addelement``. Do
NOT guess element names -- installed libraries vary across
installations and PDK configurations, and compact-model aliases in one
environment may be absent in another.

## Element Naming Convention

After ``addelement``, INTERCONNECT auto-assigns an abbreviated name
with an incrementing suffix, for example ``"CW Laser"`` → ``CWL_1``.

**Always call ``get("name")`` immediately after ``addelement``** to
capture the auto-assigned name, then use ``setnamed(..., "name", ...)``
if you need a deterministic instance name.

If no ``addelement`` name argument is given, a compound element is
added by default.

## Element Positioning (Schematic Layout)

Set ``"x position"`` and ``"y position"`` on every element in the
same snippet where it is added so the schematic stays readable. Do not
leave elements stacked at the origin.

## Handling addelement Failures

If ``addelement("name")`` fails (e.g., wrong library name), do
**NOT** call ``get("name")`` afterward -- it will return the
previously-selected element's name (stale state), and any
subsequent ``setnamed`` rename will corrupt an unrelated element.

Safe pattern: call ``get("name")`` only after a successful
``addelement``.

If a batch of ``addelement`` calls fails mid-way, the safest
recovery is to clear the circuit (``ic.selectall()`` +
``ic.delete()``) and rebuild from scratch rather than trying to
fix corrupted naming state in-place.

## Connecting Elements

Use ``connect("element1", "port1", "element2", "port2")`` to wire
ports together. Get an element's port names using
``getports("element_name")``.

``getports()`` is the universal port-discovery mechanism for both
primitive elements and compact-model-library elements. Prefer it over
trying to infer ports from ``getnamed(element, "ports")`` or other
property dumps.

**Port type matching**: always connect same-type ports. There are
3 common port types: electrical, optical, digital. Use
``getports("element", "port type")`` to list ports of a specific
type:

```python
optical_ports = ic.getports("RING_1", "optical")
electrical_ports = ic.getports("RING_1", "electrical")
digital_ports = ic.getports("PRBS_1", "digital")
```

**Always discover port types before connecting.** A common pattern is
PRBS ``output`` = digital, NRZ ``modulation`` = digital, and NRZ
``output`` = electrical.

## Signal Chain: Driving Electrically-Modulated Elements

PRBS generators produce **digital** output, but modulators (ring,
MZM) expect **electrical** modulation input. You cannot connect
digital to electrical directly.

Use an **NRZ Pulse Generator** as the digital→electrical bridge:

```
PRBS (digital out) → NRZ Pulse Generator (digital in, electrical out) → Modulator (electrical in)
```

```python
ic.connect("PRBS_1", "output", "NRZ_1", "modulation")  # digital→digital
ic.connect("NRZ_1", "output", "RING_1", "modulation")   # electrical→electrical
```

The NRZ Pulse Generator converts digital bit patterns to an
electrical voltage waveform. In the reference docs, ``amplitude`` is
the output peak amplitude before bias is added, and ``bias`` is the DC
offset added afterward. For an NRZ-driven electrical signal, treat the
low level as the bias and the high level as ``bias + amplitude``.

## Hierarchical Circuits

For hierarchical circuits, use ``::`` paths for internal elements and
remember that compound external ports map to internal ``RELAY_n``
elements in the order returned by ``getports(compound_name)``.

## Compound Elements / Compact Models

Select core elements / children with ``select`` and ``shiftselect``,
then call ``createcompound()`` to turn the selection into a compound element.
Add ports explicitly with ``addport(element, name, type, data)`` — each call
creates a ``RELAY_N`` inside the compound in order. Connect relays to internal
element ports using ``COMPOUND::RELAY_N`` path syntax.

## Property Discovery

There is **no** ``getproperties()`` method in INTERCONNECT's lumapi.
To discover element properties:

- **Option 1**: select the element and call ``set()`` with no
  arguments -- this prints all available properties.
- **Option 2**: call ``setnamed("element_name")`` with no second
  argument -- same effect without needing to select first.

```python
props = ic.setnamed("RING_1")
```

To get a property value: ``ic.getnamed("element_name", "property")``
To set a property value: ``ic.setnamed("element_name", "property", value)``

Before writing a property, verify all of the following locally:

1. The property name exists exactly as written.
2. The property is currently active for the element's current mode.
3. If it is an enum, the value is one of the allowed choices.
4. If it is numeric, the supplied units/range match the property table.

Use ``ic.ispropertyactive(element, property_name)`` when available to
check whether a property is currently writable in the active mode.

If a prompt asks for ``notes`` and the field is empty or absent, fall
back to the element ``description``, the library path/name, and the
verified property table rather than fabricating notes.

## Expression-Locked Properties

Some element properties are bound to the root element via
expressions and **cannot** be directly overwritten with
``setnamed``. For example, the PRBS bitrate is typically tied to
the root element's bitrate.

Preferred fix: set the controlling value on ``"::Root Element"``.
Only clear the expression with ``setexpression(...)`` if you truly need
per-element control.

See also: ``workflow``, ``sweeps``, ``interconnect_commands``,
``interconnect_simulation``.
"""


def get_guidelines_for_interconnect_simulation() -> str:
    """INTERCONNECT simulation config: root element, time/freq domain, result extraction."""
    return """# INTERCONNECT Simulation Configuration and Results

This topic covers INTERCONNECT **simulation configuration** and
**result extraction**: root element setup (time-domain modes and the
``"simulation input"`` selector), frequency-domain workflow via the
Optical Network Analyzer (ONA), and the ``getresult`` discovery
pattern for analyzers.

**Read ``workflow`` and ``interconnect_workflow`` first** for the
generic execution model, the discover-before-configure workflow, and
the build/setup stages.

## Root Element / Simulation Configuration

The INTERCONNECT root element controls global simulation settings.
Access it as ``"::Root Element"``.

**WARNING**: Do NOT use FDTD-style property names:
- ~~``"simulation window"``~~ → use ``"time window"``
- ~~``"bit rate"``~~ → use ``"bitrate"``

**Setting up time domain simulation**: the root element exposes a
``"simulation input"`` selector that determines which global property
set is active. The optimizer domain context documents the allowed
values as ``"time window"``, ``"sequence length"``, and
``"sample rate"``. Only the active mode's dependent properties are
settable; inactive properties raise errors.

- **``"sequence length"`` mode**: ``"bitrate"`` +
  ``"samples per bit"`` + ``"sequence length"``
- **``"time window"`` mode**: ``"time window"`` +
  ``"number of samples"``
- **``"sample rate"`` mode**: ``"sample rate"`` + the complementary
  root settings needed by the active solver setup

You **cannot** safely mix properties from different modes. Set
``"simulation input"`` first, then configure the dependent properties.
If you get "property is inactive", the root element is in another
mode.

```python
# Sequence-length mode: define via bitrate parameters
ic.setnamed("::Root Element", "simulation input", "sequence length")
ic.setnamed("::Root Element", "bitrate", 25e9)
ic.setnamed("::Root Element", "samples per bit", 64)
ic.setnamed("::Root Element", "sequence length", 128)

# Time-window mode: define duration directly
ic.setnamed("::Root Element", "simulation input", "time window")
ic.setnamed("::Root Element", "time window", 5.12e-9)
ic.setnamed("::Root Element", "number of samples", 8192)
```

In practice, ``"samples per bit"`` is a common inactive-property trap:
if it fails, verify that ``"simulation input"`` is set to
``"sequence length"`` before retrying.

Common starting values are ``sequence length = 128`` and
``samples per bit = 64``.

## Frequency Domain Simulation

Frequency domain simulation is performed using an **Optical Network
Analyzer (ONA)**. The ONA output port acts as the source and its
input port(s) collect optical signals from the circuit as results.

Typical pattern: ONA ``output`` drives the device under test and one or
more ONA ``input n`` ports collect the response.

For ONA simulations, ``"simulation bandwidth"`` is the practical
analogue of the Root Element ``"sample rate"``; ideally, set
``"simulation bandwidth"`` to inherit the Root ``"sample rate"`` via
an expression ``%sample rate%`` so ONA and any other active sources
(for example, DC sources) stay synchronized.

## Result Extraction (Discovery Pattern)

**Never guess result/dataset names.** Always discover first:

```python
datasets = ic.getresult("OSA_1")
result = ic.getresult("OSA_1", "sum/signal")
_lum_print_json(result)
```

Common analyzer result names (always verify with discovery first):

- OSA: ``"sum/signal"``, ``"mode 1/signal"``, ``"sum/spectrogram"``
- Eye Diagram: ``"measurement/BER"`` plus other
  ``"measurement/..."`` outputs

Treat listed result names as discoverable hints, not guarantees that
the dataset is populated. An analyzer can expose a result name yet
still return an empty or unusable dataset if the signal chain is
broken or the analyzer has no valid data. Always inspect the returned
payload with ``_lum_print_json(...)`` before indexing into nested keys.

See also: ``workflow``, ``interconnect_workflow``,
``interconnect_commands``, ``sweeps``.
"""


def get_guidelines_for_interconnect_commands() -> str:
    """INTERCONNECT-specific lumapi command reference by category."""
    return """# INTERCONNECT Commands Reference

This topic provides the INTERCONNECT-specific lumapi commands
grouped by category. These commands are called as methods on the
INTERCONNECT session handle (e.g., ``ic.library()``) or via
``ic.eval("<lsf>;")`` for script-only commands.

**Read ``workflow`` and ``interconnect_workflow`` first** for the
execution model, discover-before-configure workflow, and build/setup
stages.

## Element Library Commands

| Command | Description |
|---------|-------------|
| ``library()`` | Returns the installed element list, including custom elements. |
| ``addtolibrary()`` | Adds an element to the currently selected custom library. |
| ``customlibrary()`` | Returns the path of the custom library. |
| ``saveelement()`` | Saves an element to file. |
| ``loadelement()`` | Loads an element from file. |
| ``probe()`` | Places a probe analyzer at a specified port. |
| ``loadcustom()`` | Redirects the Custom folder path and reloads its contents. |
| ``replacelibrary()`` | Replaces all instances of the current library in the Element Library. |
| ``hideproperty()`` | Hides the property of a given element. |
| ``protectproperty()`` | Protects the property of a given element. |
| ``hidecategory()`` | Hides all properties of a given category of a given element. |
| ``annotateproperty()`` | Enables property annotation on a given element. |
| ``ispropertyactive()`` | Returns true if the property from an element is active. |
| ``parsebackannotation()`` | Parses the waveguide back annotation. |
| ``parsewaveguidebackannotation()`` | Parses waveguide back annotation at a given temperature. |

## Design Kit Commands

| Command | Description |
|---------|-------------|
| ``loaddesignkit()`` | Loads a design kit and directs its contents to a user-defined path. |
| ``enabledesignkit()`` | Enables a design kit in the Design Kits folder. |
| ``disabledesignkit()`` | Disables a design kit in the Design Kits folder. |
| ``removedesignkit()`` | Removes a design kit from the element library 'Design kits' folder. |
| ``reloaddesignkit()`` | Reloads a design kit from the element library Design kits folder. |
| ``packagedesignkit()`` | Creates a design kit file from a Custom folder. |
| ``installdesignkit()`` | Installs a ``.cml`` design kit to the Design Kits folder. |
| ``uninstalldesignkit()`` | Uninstalls a design kit from the Design Kits folder. |
| ``importlib()`` | Imports the .lib file for a CML in the Custom folder. |
| ``exportlib()`` | Exports the .lib file for a CML in the Custom folder. |
| ``renameport()`` | Renames the port name for a Compound or Scripted element. |
| ``removecustom()`` | Removes a folder in the Custom folder in Element Library. |

If a required compact model library is missing, install it with:

```python
ic.installdesignkit("dk.cml", "C:/Users/xxx", True)
```

``filename`` is the ``.cml`` file, ``path`` is the folder that holds
it, and ``overwrite=True`` replaces an existing kit with the same
name. With ``overwrite=False``, INTERCONNECT asks for confirmation
before replacing an existing kit.

## Measurement & Analyzer Commands

| Command | Description |
|---------|-------------|
| ``validate()`` | Reruns the analysis of an analyzer. |
| ``validateall()`` | Reruns the analysis of all analyzers in the simulation. |
| ``setresult()`` | Sets the result of a Scripted or a Compound element. |
| ``getresultdata()`` | Gets results from an analyzer as matrices. |
| ``getvalue()`` | Gets an internal value for an element internal parameter. |
| ``setvalue()`` | Sets an internal value for an element internal parameter. |

Use only commands verified in the deployed lumapi version. In
particular, do **not** assume convenience helpers such as
``getproperties()`` exist just because they appear in external
examples; in INTERCONNECT, property discovery is done with ``set()`` or
``setnamed(element)`` plus targeted ``getnamed(...)`` calls.

## Scripted Element / S-Parameter Commands

These commands are used for creating scripted elements and
S-parameter elements:

| Command | Description |
|---------|-------------|
| ``popportdata()`` | Extracts the first available data value from the input port. |
| ``pushportdata()`` | Sends the data to the output port. |
| ``cloneportdata()`` | Clones an existing data value. |
| ``popportframe()`` | Returns a frame structure for the input signal on a given port. |
| ``pushportframe()`` | Writes a frame structure for the output signal on a given port. |
| ``getmonitorframe()`` | Reads the available frames from an analyzer input port. |
| ``getmonitorwaveform()`` | Returns a waveform structure from an analyzer input port. |
| ``portdatasize()`` | Returns the number of data values available at the input port. |
| ``setsparameter()`` | Sets the S-parameter between output and input port. |
| ``importsparameter()`` | Imports Script-workspace S-parameter data into S-parameter elements. |
| ``setfir()`` | Initializes a FIR filter using the current S-parameters. |
| ``setiir()`` | Initializes an IIR filter using the current S-parameters. |
| ``getports()`` | Returns a list of ports in an element. |

## User-Defined Settings Commands

| Command | Description |
|---------|-------------|
| ``setsetting()`` | Sets the value of a user-defined setting. |
| ``getsetting()`` | Returns the value of a user-defined setting. |

## Optimization Commands

| Command | Description |
|---------|-------------|
| ``runoptimization()`` | Optimizes a chosen element property under specified conditions. |

## Export & Utility Commands

| Command | Description |
|---------|-------------|
| ``exportimage()`` | Exports an image of the current circuit schematic. |
| ``constructgeneratormatrix()`` | Constructs a symmetric coding generator matrix. |
| ``importtemperaturemap()`` | Imports an Icepak data file to an INTERCONNECT schematic design. |

## Result Extraction

**Never guess result/dataset names.** Use the discovery pattern:

1. ``getresult(element)`` with no second argument lists available
   dataset names.
2. ``getresult(element, dataset_name)`` returns the data as a dict.

Common analyzer result names (always verify with step 1):

| Analyzer | Typical dataset names |
|----------|----------------------|
| OSA | ``"sum/signal"``, ``"mode 1/signal"`` |
| ONA | ``"input 1/mode 1/gain"``, ``"input 1/mode 1/neff"`` |
| Eye Diagram | ``"measurement/BER"``, ``"measurement/Q factor"`` |

The returned dataset is a dict with keys like ``"Frequency"``,
``"power (dBm)"``, etc.

If ``getresult(element)`` lists a dataset but the returned payload is
empty or only contains a placeholder ``Lumerical_dataset`` envelope,
do not continue with blind indexing. Treat that as a data-health issue:
validate the signal chain, analyzer configuration, and whether the
analyzer is appropriate for the current workflow (for example, ONA is
often more informative than OSA for passive transfer-function checks).

See also: ``workflow``, ``interconnect_workflow``, ``sweeps``.
"""


__all__ = [
    "get_guidelines_for_interconnect_commands",
    "get_guidelines_for_interconnect_simulation",
    "get_guidelines_for_interconnect_workflow",
]

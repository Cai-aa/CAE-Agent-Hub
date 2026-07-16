# Socket Bridge Connection

## Description

Connect to Abaqus CAE via socket bridge for curing simulation. Invoke when user needs to use socket bridge, connect to Abaqus, or execute Python in Abaqus kernel.

## Content

### Socket Bridge Overview

The socket bridge provides a TCP connection to Abaqus CAE at `127.0.0.1:48152`, allowing remote execution of Python code in the Abaqus kernel.

### Prerequisites

- Abaqus CAE must be open and running
- The socket bridge plugin must be active in Abaqus

### Connection Check

Use the `check_abaqus_connection` MCP tool to verify the bridge status before executing any commands.

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `check_abaqus_connection` | Verify bridge connection status |
| `run_python` | Execute Python code in Abaqus kernel |
| `submit_job` | Submit a job and wait for completion |
| `monitor_job_status` | Check .sta/.msg file diagnostics |
| `inspect_odb` | Read ODB results and field outputs |
| `set_workdir` | Set the working directory |
| `list_jobs` | List existing jobs in the session |

### run_python Usage

When using `run_python`, set the `result` variable to return data back to the caller:

```python
# Example: get list of steps
result = []
for step_name in odb.steps.keys():
    result.append(step_name)
```

### Abaqus Python Environment Quirks

The Abaqus Python environment has several important quirks to be aware of:

#### Python Version
- Abaqus 2020+ uses Python 2.7 based environment
- Do not use Python 3 specific syntax

#### Unicode Issues
- `print()` statements with unicode may cause errors
- Use `result = ...` to return data instead of printing

#### Imports
- Must import constants: `from abaqusConstants import *`
- This provides access to all Abaqus constants (OFF, ON, RUNNING, etc.)

#### String Formatting
- Use the `%` operator for string formatting
- Do NOT use `.format()` or f-strings (not supported in Python 2.7)

```python
# Correct
text = '%d nodes found' % node_count

# Incorrect (will fail)
text = '{} nodes found'.format(node_count)
text = f'{node_count} nodes found'
```

#### Dictionary Keys
- Plain strings work reliably as dictionary keys
- Unicode keys may fail in some operations

### Standard Workflow

1. **Check connection:** Use `check_abaqus_connection` to verify bridge is active
2. **Set working directory:** Use `set_workdir` to configure the work directory
3. **Create jobs:** Use `run_python` to create jobs from input files
4. **Submit jobs:** Use `submit_job` or `run_python` with `submit()`
5. **Monitor:** Use `monitor_job_status` to check for errors or convergence issues
6. **Copy ODB:** Copy the ODB file from scratch to work directory
7. **Extract data:** Use `inspect_odb` or `run_python` to read results

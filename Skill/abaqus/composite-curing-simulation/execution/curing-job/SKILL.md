# Curing Job Execution

## Description

Submit Abaqus curing simulation jobs with UMAT subroutine via socket bridge. Invoke when user needs to create, submit, or monitor curing simulation jobs.

## Content

### Job Creation with UMAT

Create a job from an input file with the UMAT subroutine specified:

```python
from abaqusConstants import *

job = mdb.JobFromInputFile(
    name='job_name',
    inputFileName=work_dir + '\\job_name.inp',
    userSubroutine=umat_path,
    numCpus=4,
    numDomains=4
)
```

### Job Submission

Submit the job with `consistencyChecking=OFF` to avoid unicode TypeError issues:

```python
mdb.jobs['job_name'].submit(consistencyChecking=OFF)
```

**Important:** You MUST use `consistencyChecking=OFF` when submitting. Without this parameter, Abaqus may raise a unicode TypeError during the consistency check phase.

### Monitoring Job Status

Check the current status of a submitted job:

```python
status = mdb.jobs['job_name'].status
# Possible values: RUNNING, COMPLETED, SUBMITTED, etc.
```

### Common Pitfalls

#### Unicode Errors
- Avoid using `print()` with `%` formatting in the Abaqus kernel
- Use `result = ...` to return data instead of printing

#### String Key Issues
- Use plain strings for job names, not unicode strings
- Dictionary keys should be plain strings; unicode keys may fail

#### Multiple Jobs
- Submit jobs sequentially, not in parallel
- The first `submit()` call in a loop may submit all jobs if not handled carefully
- Wait for each job to complete before submitting the next

### Job Output Location

- **Scratch directory:** `C:\Temp`
- **ODB file generated at:** `C:\Temp\job_name.odb`

### Post-Completion

After the job completes, copy the ODB file from the scratch directory to the work directory:

```python
import shutil

shutil.copy(
    'C:\\Temp\\job_name.odb',
    work_dir + '\\job_name.odb'
)
```

### Workflow Summary

1. Create job from input file with UMAT subroutine path
2. Submit with `consistencyChecking=OFF`
3. Monitor job status until COMPLETED
4. Copy ODB from `C:\Temp` to work directory
5. Proceed to post-processing (ODB extraction, CSV export)

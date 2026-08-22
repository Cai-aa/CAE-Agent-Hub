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

"""
CFX worker process.

This module is executed in a separate Python interpreter so PyCFX can be
imported without colliding with protocol buffer descriptors from other
loaded packages.

Communication protocol: JSON lines over stdin/stdout.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback

logger = logging.getLogger(__name__)


def main() -> None:
    """Execute the module entry point for PyCFX-MCP.

    Returns
    -------
    None
        No value is returned. Side effects are applied to the relevant cache, session, or
        server.
    """
    import ansys.cfx.core as pycfx

    session = None

    for line in sys.stdin:
        try:
            msg = json.loads(line)
            cmd = msg.get("cmd")

            if cmd == "launch_pre":
                launcher = msg.get("launcher", "from_install")
                launch = getattr(pycfx.PreProcessing, launcher)
                kwargs = msg.get("kwargs", {})
                session = launch(**kwargs)
                try:
                    session.file.new_case()
                except Exception as exc:
                    logger.debug("Could not initialize a new CFX-Pre case: %s", exc)
                sys.stdout.write(json.dumps({"status": "ok"}) + "\n")
                sys.stdout.flush()

            elif cmd == "run_code":
                code = msg.get("code", "")
                ns = {"cfxpre": session, "session": session}
                exec(code, ns)  # nosec B102
                sys.stdout.write(json.dumps({"status": "ok"}) + "\n")
                sys.stdout.flush()

            elif cmd == "exit":
                if session:
                    session.exit()
                sys.stdout.write(json.dumps({"status": "ok"}) + "\n")
                sys.stdout.flush()
                break

            else:
                sys.stdout.write(
                    json.dumps({"status": "error", "message": f"Unknown cmd {cmd}"}) + "\n"
                )
                sys.stdout.flush()

        except Exception as exc:
            sys.stdout.write(
                json.dumps(
                    {
                        "status": "error",
                        "message": str(exc),
                        "trace": traceback.format_exc(),
                    }
                )
                + "\n"
            )
            sys.stdout.flush()


if __name__ == "__main__":
    main()

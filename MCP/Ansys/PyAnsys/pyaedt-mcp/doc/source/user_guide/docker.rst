.. _ref_docker:

Docker deployment
=================

You can run PyAEDT-MCP as a containerized service with HTTP transport.
Because AEDT does not have a publicly available Docker image, the MCP
container connects to an AEDT instance running on your host machine or on a
remote server.

.. warning::
   HTTP transport is not encrypted. Use it only on trusted networks or behind a
   reverse proxy (such as Nginx or HAProxy) that provides TLS/SSL.

Quick start with Docker Compose
--------------------------------

Use Docker Compose for the fastest setup.

#. Start AEDT on the host machine first:

   .. code-block:: bash

      # Windows
      "C:\Program Files\ANSYS Inc\v261\AnsysEM\ansysedt.exe" -grpcsrv 50051

   Or open AEDT from the desktop icon.

#. Build and start the MCP container:

   .. code-block:: bash

      docker compose -f docker/docker-compose.yml up -d --build

   The MCP server is available at ``http://localhost:8080``.

#. Check the logs:

   .. code-block:: bash

      docker compose -f docker/docker-compose.yml logs -f pyaedt-mcp

#. Stop the server:

   .. code-block:: bash

      docker compose -f docker/docker-compose.yml down

MCP client configuration
------------------------

After the container starts, point your MCP client to the HTTP server.

**Visual Studio Code**

Edit the ``.vscode/mcp.json`` file:

.. code-block:: json

   {
     "servers": {
       "pyaedt-mcp": {
         "type": "http",
         "url": "http://localhost:8080"
       }
     }
   }

**Claude Desktop**:

.. code-block:: json

   {
     "mcpServers": {
       "pyaedt-mcp": {
         "url": "http://localhost:8080",
         "transport": "http"
       }
     }
   }

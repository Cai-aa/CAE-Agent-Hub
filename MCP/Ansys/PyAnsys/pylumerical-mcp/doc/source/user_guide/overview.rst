Overview
========

This page provides an overview of PyLumerical-MCP. Additional tips and best practices are in the :doc:`Best practices <best_practices>` page.

.. vale off

What is PyLumerical-MCP?
------------------------

.. vale on

PyLumerical-MCP provides an interface for agents to connect to Lumerical tools. Built as a standard
Model Context Protocol (MCP) server, it allows agents to connect to a live Lumerical session and write
PyLumerical scripts to control the simulation.

Simulation sessions
-------------------

PyLumerical-MCP provides tools for managing multiple live Lumerical sessions. These sessions persist across
different chats, letting you and other agents work on the same simulation with different contexts. You can
also control different sessions from a single chat.

For example, the following prompt opens two different Lumerical sessions, one for INTERCONNECT and one for FDTD:

.. code:: text

    Please open one INTERCONNECT and one FDTD session.

By default, simulation sessions open with the GUI so you can work with the agent to build your simulation.

You can also open sessions with the GUI hidden:

.. code:: text

    Please open a DEVICE session with the GUI hidden.

After you open a session, the agent can control your simulation. You can ask the agent to show the GUI again
when needed.

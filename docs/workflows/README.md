# Workflow Documentation

This directory will contain one Markdown document per implemented workflow or reusable subworkflow. Use stable, descriptive filenames that match the workflow's role. Group documents into subdirectories only when the number of workflows makes that clearer.

Each workflow document should contain:

- purpose;
- input contract;
- output contract;
- a readable node diagram;
- a node-by-node explanation;
- errors and edge cases;
- dependencies, including called subworkflows and storage paths;
- repeatable tests and their expected results;
- workflows that consume it.

Documentation should distinguish a planned contract from an implemented and verified one. Record the n8n workflow name and stable identifier when one exists, but do not include credentials, tokens, sensitive payloads, or exported secrets.

Implementation changes are normally reviewed through GitHub Pull Requests before they are merged into `main`.

Reusable subworkflows should expose a narrow contract and hide implementation details from their callers. Update the workflow document and `docs/implementation/STATUS.md` whenever implementation status or a public contract changes.

"""Import-flow tests (workstream E). A package, so this folder's conftest is
imported as `flow.conftest` and never shadows another folder's `conftest`
(tests/ui imports names from its own conftest by that bare name)."""

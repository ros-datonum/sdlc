"""In-memory FiberyWorkspace used to test deterministic `project init` behaviour."""

from __future__ import annotations

import itertools

from sdlc.fibery_workspace import FiberyError, ProjectRecord

PLANNED_STATE = "Planned"


class FakeFiberyWorkspace:
    """Records every call and mutation so tests can assert on both."""

    def __init__(
        self,
        projects: list[ProjectRecord] | None = None,
        known_states: tuple[str, ...] = (PLANNED_STATE,),
    ) -> None:
        self.projects = {record.id: record for record in projects or []}
        self.descriptions: dict[str, str] = {}
        self.known_states = known_states
        self.mutations: list[str] = []
        self.calls: list[str] = []

        # Fault injection.
        self.failures: dict[str, FiberyError] = {}
        # Simulate a write that silently did not take effect.
        self.ignore_state_writes = False

        self._ids = itertools.count(1)

    # -- reads ---------------------------------------------------------

    def find_project_by_name(self, name: str) -> ProjectRecord | None:
        self._record_call("find_project_by_name")
        return next(
            (record for record in self.projects.values() if record.name == name), None
        )

    def count_projects_with_code(self, code: str) -> int:
        self._record_call("count_projects_with_code")
        return sum(1 for record in self.projects.values() if record.code == code)

    def read_project(self, project_id: str) -> ProjectRecord | None:
        self._record_call("read_project")
        return self.projects.get(project_id)

    # -- writes --------------------------------------------------------

    def create_project(self, name: str, code: str) -> str:
        self._record_call("create_project")
        project_id = f"project-{next(self._ids)}"
        self.projects[project_id] = ProjectRecord(
            id=project_id,
            name=name,
            code=code,
            state=None,
        )
        self.mutations.append(f"create_project {name} {code}")
        return project_id

    def set_project_state(self, project_id: str, state: str) -> None:
        self._record_call("set_project_state")
        if state not in self.known_states:
            raise FiberyError(f"Unknown state {state!r}.")
        self.mutations.append(f"set_project_state {project_id} {state}")
        if self.ignore_state_writes:
            return
        self._replace(project_id, state=state)

    def set_project_description(self, project_id: str, description: str) -> None:
        self._record_call("set_project_description")
        self.mutations.append(f"set_project_description {project_id}")
        self.descriptions[project_id] = description

    # -- helpers -------------------------------------------------------

    def _record_call(self, method: str) -> None:
        self.calls.append(method)
        failure = self.failures.pop(method, None)
        if failure is not None:
            raise failure

    def _replace(self, project_id: str, **changes: object) -> None:
        current = self.projects[project_id]
        self.projects[project_id] = ProjectRecord(
            id=current.id,
            name=changes.get("name", current.name),
            code=changes.get("code", current.code),
            state=changes.get("state", current.state),
        )


def planned_project(
    project_id: str = "existing-1",
    name: str = "SDLC",
    code: str = "SDLC",
) -> ProjectRecord:
    return ProjectRecord(id=project_id, name=name, code=code, state=PLANNED_STATE)

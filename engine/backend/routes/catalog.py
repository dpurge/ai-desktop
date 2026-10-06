from fastapi import APIRouter, Request

from backend.skills.loader import skill_scanner
from backend.tools.registry import default_registry

router = APIRouter()


@router.get("/tools")
def list_tools(request: Request) -> list[dict]:
    return default_registry(request.app.state.settings).describe()


@router.get("/skills")
def list_skills(request: Request) -> dict:
    settings = request.app.state.settings
    catalog = skill_scanner(settings.state_dir, settings.config().skills.workspace_dir)()
    # Bodies and absolute paths stay inside the engine; the list only needs to identify skills.
    return {
        "skills": [
            {"name": s.name, "description": s.description, "source": s.source}
            for s in catalog.skills
        ],
        "problems": [{"path": p.folder, "message": p.message} for p in catalog.problems],
    }

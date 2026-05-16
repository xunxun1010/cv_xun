import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_YAML = os.environ.get("EASYCV_YAML", "resume.yaml")

app = FastAPI(title="easy-cv", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class ResumeDataPayload(BaseModel):
    data: Dict[str, Any]


class ResumeRawPayload(BaseModel):
    yaml_text: str


YAML_DIRS = [BASE_DIR, BASE_DIR / "cv"]


def _resolve_file(filename: str) -> Path:
    """Resolve a YAML filename, blocking path traversal. Searches root and cv/."""
    p = Path(filename)
    if ".." in str(p) or p.is_absolute():
        raise HTTPException(status_code=400, detail="不允许的路径")

    # Direct path (e.g. "cv/xun.yaml" or "resume.yaml")
    candidate = BASE_DIR / p
    if candidate.exists():
        return candidate

    # Try cv/ subdirectory as fallback
    cv_candidate = BASE_DIR / "cv" / p.name
    if cv_candidate.exists():
        return cv_candidate

    # File doesn't exist yet — use the direct path for writes
    return candidate


def _list_yaml_files() -> List[str]:
    """List all *.yaml / *.yml files in root and cv/."""
    files = []
    for d in YAML_DIRS:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix in (".yaml", ".yml") and f.is_file():
                rel = str(f.relative_to(BASE_DIR)).replace("\\", "/")
                files.append(rel)
    return files


def _read_resume(filename: str) -> Dict[str, Any]:
    path = _resolve_file(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{filename} 不存在")
    text = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text) or {}
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail=f"{filename} 顶层必须是对象")
    return parsed


def _write_resume(filename: str, data: Dict[str, Any]) -> None:
    path = _resolve_file(filename)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


@app.get("/", include_in_schema=False)
def root(request: Request) -> HTMLResponse:
    files = _list_yaml_files()
    return templates.TemplateResponse(
        request, "index.html", context={"files": files}
    )


@app.get("/resume", response_class=HTMLResponse, include_in_schema=False)
def resume_page(request: Request, file: str = Query(default=DEFAULT_YAML)) -> HTMLResponse:
    data = _read_resume(file)
    return templates.TemplateResponse(
        request,
        "resume.html",
        context={
            "resume": data,
            "basics": data.get("basics", {}),
            "education": data.get("education", []),
            "code": data.get("code", []),
            "personal_docs": data.get("personal_docs"),
            "team_projects": data.get("team_projects", []),
            "personal_projects": data.get("personal_projects", []),
            "lab_tutorials": data.get("lab_tutorials", []),
            "skills": data.get("skills", []),
            "awards": data.get("awards", []),
            "publications": data.get("publications", []),
            "honors": data.get("honors", []),
            "current_file": file,
            "all_files": _list_yaml_files(),
        },
    )


@app.get("/editor", response_class=HTMLResponse, include_in_schema=False)
def editor_page(request: Request, file: str = Query(default=DEFAULT_YAML)) -> HTMLResponse:
    path = _resolve_file(file)
    yaml_text = path.read_text(encoding="utf-8") if path.exists() else ""
    return templates.TemplateResponse(
        request,
        "editor.html",
        context={
            "yaml_text": yaml_text,
            "current_file": file,
            "all_files": _list_yaml_files(),
        },
    )


@app.get("/api/resume")
def get_resume_data(file: str = Query(default=DEFAULT_YAML)) -> Dict[str, Any]:
    return _read_resume(file)


@app.put("/api/resume")
def put_resume_data(payload: ResumeDataPayload, file: str = Query(default=DEFAULT_YAML)) -> Dict[str, str]:
    _write_resume(file, payload.data)
    return {"message": f"已更新 {file}"}


@app.get("/api/resume/raw")
def get_resume_raw(file: str = Query(default=DEFAULT_YAML)) -> Dict[str, str]:
    path = _resolve_file(file)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{file} 不存在")
    return {"yaml_text": path.read_text(encoding="utf-8")}


@app.put("/api/resume/raw")
def put_resume_raw(payload: ResumeRawPayload, file: str = Query(default=DEFAULT_YAML)) -> Dict[str, str]:
    try:
        parsed = yaml.safe_load(payload.yaml_text) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"YAML 解析失败: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="YAML 顶层必须是对象")
    _write_resume(file, parsed)
    return {"message": f"YAML 已保存到 {file}"}


if __name__ == "__main__":
    import sys
    import subprocess
    import platform

    host = "127.0.0.1"
    port = 8010

    if platform.system() == "Darwin":
        url = f"http://{host}:{port}"
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        import uvicorn
    except ImportError:
        print("uvicorn 未安装，请先运行: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    uvicorn.run("app:app", host=host, port=port, reload=True)

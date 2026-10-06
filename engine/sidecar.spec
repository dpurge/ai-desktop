# PyInstaller spec for the engine sidecar. Build with `task engine:sidecar`.
# onedir (not onefile): onefile unpacks itself on every launch, which makes app start-up slow.
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# aisuite picks its provider module by name at run time ("ollama" -> aisuite.providers.ollama_provider),
# so static analysis never sees them. Collect the whole package, not just the providers we use today.
aisuite_datas, aisuite_binaries, aisuite_hiddenimports = collect_all("aisuite")

datas = [
    # config.toml and the built-in skills are read through importlib.resources at run time.
    # Listed by path because the engine is not an installed package, so collect_data_files cannot find it.
    ("backend/defaults", "backend/defaults"),
    # httpx/openai verify TLS against certifi's CA bundle file.
    *collect_data_files("certifi"),
    *aisuite_datas,
]

hiddenimports = [
    *aisuite_hiddenimports,
    # The openai SDK lazily imports many resource modules.
    *collect_submodules("openai"),
    # uvicorn picks its event loop, HTTP and websocket implementations by string name.
    *collect_submodules("uvicorn"),
]

analysis = Analysis(
    ["backend/__main__.py"],  # same entry point as `python -m backend`, so the arguments match
    pathex=["."],
    binaries=aisuite_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest"],
)

executable = EXE(
    PYZ(analysis.pure),
    analysis.scripts,
    exclude_binaries=True,
    name="backend",
    console=True,
)

COLLECT(executable, analysis.binaries, analysis.datas, name="backend")

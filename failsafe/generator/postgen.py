from pathlib import Path
from importlib.resources import files as pkg_files

def _render_template(src_path: Path, context: dict[str, str]) -> str:
    """Minimal, fast substitution renderer for {{var}} placeholders."""
    text = src_path.read_text()
    for k, v in context.items():
        # Ensure v is string to prevent type errors
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text

def inject_custom_templates(out_dir: Path, package_name: str, app_name: str, app_version: str, server_port: str) -> list[Path]:
    """
    Copies and renders custom templates. 
    Returns a list of Path objects that were created/modified.
    """
    tmpl_root = pkg_files("failsafe").joinpath("generator/templates/python-fastapi")
    injected_files = []

    # explicit templates
    explicit = {
        ".dockerignore.mustache": out_dir / ".dockerignore",
        "telemetry.mustache": out_dir / "src" / package_name / "telemetry.py",
        "settings.mustache": out_dir / "src" / package_name / "settings.py",
        ".config/otel-config.yaml.mustache": out_dir / ".config" / "otel-config.yaml",
        ".config/prometheus.yml.mustache": out_dir / ".config" / "prometheus.yml",
    }

    context = {
        "packageName": package_name,
        "appName": app_name,
        "appVersion": app_version,
        "serverPort": server_port
    }

    # render explicit
    for rel_name, target_path in explicit.items():
        src_path = tmpl_root / rel_name
        if src_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(_render_template(src_path, context))
            injected_files.append(target_path)

    # optional: auto-detect anything under custom/
    custom_dir = tmpl_root / "custom"
    if custom_dir.exists():
        for src_path in custom_dir.rglob("*.mustache"):
            rel = src_path.relative_to(custom_dir)
            target = out_dir / rel.with_suffix("")  # strip .mustache
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_render_template(src_path, context))
            injected_files.append(target_path)

    return injected_files
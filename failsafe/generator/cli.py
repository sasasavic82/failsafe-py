import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from enum import Enum
from importlib.resources import files as pkg_files
import typer
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree
from rich.table import Table
from rich.style import Style

from .postgen import inject_custom_templates

app = typer.Typer(help="Failsafe code generator: wraps openapi-generator with resiliency templates")
console = Console()


class ProtectionType(str, Enum):
    INGRESS = "INGRESS"
    EGRESS = "EGRESS"
    FULL = "FULL"


class TelemetryType(str, Enum):
    OTEL = "OTEL"
    PROMETHEUS = "PROMETHEUS"
    NONE = "NONE"


@app.callback()
def root() -> None:
    pass

def _resolve_generator() -> list[str]:
    for cand in ("openapi-generator", "openapi-generator-cli"):
        if shutil.which(cand):
            return [cand]
    if shutil.which("docker"):
        return [
            "docker", "run", "--rm",
            "-v", f"{Path.cwd()}:/local",
            "openapitools/openapi-generator-cli",
        ]
    # Use console print instead of raw SystemExit for prettier error
    console.print("[bold red]Error:[/bold red] openapi-generator not found. Install binary/CLI or Docker image.")
    raise typer.Exit(1)


@app.command("generate")
def generate(
    spec: Path = typer.Argument(..., exists=True, readable=True, help="Path to openapi.yaml/json"),
    out_dir: Path = typer.Option(Path("generated-server"), "--out", "-o", help="Output directory"),
    package_name: str = typer.Option("service", "--package-name"),
    app_name: str = typer.Option("service", "--app-name"),
    app_version: str = typer.Option("0.1.0", "--app-version"),
    server_port: int = typer.Option(8080, "--server-port"),
    dockerfile: bool = typer.Option(True, "--dockerfile/--no-dockerfile"),
    git_creds: bool = typer.Option(True, "--git-creds/--no-git-creds"),
    
    # Telemetry options
    telemetry: TelemetryType = typer.Option(TelemetryType.OTEL, "--telemetry", "-t"),
    otel_endpoint: str = typer.Option("http://otel-collector:4318/v1/metrics", "--otel-endpoint"),
    
    # Protection options
    protection: bool = typer.Option(True, "--protection/--no-protection"),
    protection_type: ProtectionType = typer.Option(ProtectionType.INGRESS, "--protection-type"),
    
    # Control plane options
    controlplane: bool = typer.Option(True, "--controlplane/--no-controlplane"),
    controlplane_prefix: str = typer.Option("/failsafe", "--controlplane-prefix"),
    
    extra_props: Optional[str] = typer.Option(None, "--extra-props"),
):
    """
    Generate a FastAPI service stub with Failsafe templates and resiliency patterns.
    """
    tmpl_dir = pkg_files("failsafe").joinpath("generator/templates/python-fastapi")
    if not tmpl_dir.exists():
        console.print("[bold red]Critical:[/bold red] Templates not found inside package.")
        raise typer.Exit(1)

    generator = _resolve_generator()
    
    # --- 1. PRETTY CONFIG SUMMARY ---
    grid = Table.grid(expand=True)
    grid.add_column(style="bold cyan")
    grid.add_column()
    
    grid.add_row("Spec File:", str(spec))
    grid.add_row("Output Dir:", str(out_dir))
    grid.add_row("Telemetry:", f"{telemetry.value} ({otel_endpoint if telemetry == TelemetryType.OTEL else 'N/A'})")
    grid.add_row("Protection:", f"{protection_type.value if protection else 'Disabled'}")
    grid.add_row("Control Plane:", f"{controlplane_url if controlplane else 'Disabled'}")

    console.print(Panel(
        grid, 
        title=f"[bold green]Failsafe Generator: {package_name}[/bold green]",
        border_style="green",
        expand=False
    ))

    # Build template properties
    props = [
        f"packageName={package_name}",
        f"appName={app_name}",
        f"appVersion={app_version}",
        f"serverPort={server_port}",
        f"gitCreds={'true' if git_creds else 'false'}",
        f"otel={'true' if telemetry == TelemetryType.OTEL else 'false'}",
        f"prometheus={'true' if telemetry == TelemetryType.PROMETHEUS else 'false'}",
        f"otelEndpoint={otel_endpoint}",
        f"protection={'true' if protection else 'false'}",
        f"protectionType={protection_type.value}",
        f"controlplane={'true' if controlplane else 'false'}",
        f"controlplanePrefix={controlplane_prefix}",
    ]
    
    if dockerfile:
        props.append("generateDockerfile=true")
    if extra_props:
        props.extend(p.strip() for p in extra_props.split(",") if p.strip())

    cmd = [
        *generator,
        "generate",
        "-i", str(spec if generator[0] != "docker" else Path("/local") / spec.name),
        "-g", "python-fastapi",
        "-o", str(out_dir if generator[0] != "docker" else Path("/local") / out_dir.name),
        "-t", str(
            tmpl_dir
            if generator[0] != "docker"
            else Path("/local") / "failsafe" / "generator" / "templates" / "python-fastapi"
        ),
        "--additional-properties", ",".join(props),
    ]

    if generator[0] == "docker" and spec.parent != Path.cwd():
        console.print("[yellow]Warning:[/yellow] For Docker mode, put the spec file in the current working directory.")

    # --- 2. RUN SILENTLY WITH SPINNER ---
    try:
        with console.status("[bold blue]Running OpenAPI Generator...[/bold blue] (this may take a few seconds)"):
            result = subprocess.run(
                list(map(str, cmd)), 
                check=False,          # Don't raise immediately, we want to handle output
                capture_output=True,  # SILENCES THE OUTPUT
                text=True
            )
            
            if result.returncode != 0:
                console.print("[bold red]Generator Failed![/bold red]")
                console.print(Panel(result.stderr, title="Error Log", border_style="red"))
                raise typer.Exit(1)

        # --- 3. POST GEN & TREE OUTPUT ---
        # Call postgen, which now returns a list of files instead of printing
        injected = inject_custom_templates(out_dir, package_name, app_name, app_version, str(server_port))

        # Create a visual tree of the output
        tree = Tree(f":file_folder: [bold]{out_dir}[/bold]")
        
        # Add standard source grouping
        src_group = tree.add(":package: src")
        src_group.add(f"{package_name}/")
        
        # Add config grouping
        if injected:
            config_group = tree.add(":gear: configuration (injected)")
            for f in injected:
                # Calculate relative path for cleaner display
                try:
                    rel = f.relative_to(out_dir)
                    config_group.add(f"[green]{rel}[/green]")
                except ValueError:
                    config_group.add(f"[green]{f.name}[/green]")

        console.print("\n")
        console.print(tree)
        console.print(f"\n[bold green]✓ Generation Complete![/bold green] \ncd {out_dir} && pip install -r requirements.txt")

    except Exception as e:
        console.print(f"[bold red]Unexpected Error:[/bold red] {e}")
        raise typer.Exit(1)
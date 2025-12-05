import subprocess
import logging
import yaml
from typing import Dict, Any, List, Optional

def run_helm_command(command: List[str], logger: logging.Logger) -> subprocess.CompletedProcess:
    """Run a helm command and return the result."""
    full_command = ["helm"] + command
    logger.debug(f"Running command: {' '.join(full_command)}")

    try:
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            check=True
        )
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Helm command failed: {e.stderr}")
        raise

def check_helm_installed(logger: logging.Logger) -> bool:
    """Check if Helm is installed and accessible."""
    try:
        result = subprocess.run(
            ["helm", "version", "--short"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.debug(f"Helm version: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def add_helm_repo(name: str, url: str, logger: logging.Logger) -> bool:
    """Add a Helm repository."""
    try:
        run_helm_command(["repo", "add", name, url], logger)
        run_helm_command(["repo", "update"], logger)
        logger.info(f"Added Helm repo '{name}' from {url}")
        return True
    except subprocess.CalledProcessError:
        logger.error(f"Failed to add Helm repo '{name}'")
        return False

def install_helm_chart(
    release_name: str,
    chart_name: str,
    namespace: str = "default",
    version: Optional[str] = None,
    values: Optional[Dict[Any, Any]] = None,
    create_namespace: bool = True,
    logger: logging.Logger = None
) -> bool:
    """Install a Helm chart."""
    try:
        # Prepare the command
        command = ["upgrade", "--install", release_name, chart_name]

        # Add namespace
        command.extend(["--namespace", namespace])

        # Create namespace if needed
        if create_namespace:
            command.append("--create-namespace")

        # Add version if specified
        if version:
            command.extend(["--version", version])

        # Add values if specified
        if values:
            # Write values to a temporary file
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(values, f)
                values_file = f.name

            command.extend(["--values", values_file])

        # Run the command
        result = run_helm_command(command, logger)
        logger.info(f"Helm chart '{chart_name}' installed successfully as '{release_name}'")

        # Clean up temporary values file
        if values:
            os.unlink(values_file)

        return True
    except subprocess.CalledProcessError:
        logger.error(f"Failed to install Helm chart '{chart_name}'")
        return False

def check_release_exists(release_name: str, namespace: str, logger: logging.Logger) -> bool:
    """Check if a Helm release exists."""
    try:
        result = run_helm_command(["list", "--namespace", namespace], logger)
        return release_name in result.stdout
    except subprocess.CalledProcessError:
        return False
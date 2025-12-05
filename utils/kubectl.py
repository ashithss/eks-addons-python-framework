import subprocess
import json
import logging
from typing import List, Dict, Any, Optional

def run_kubectl_command(command: List[str], logger: logging.Logger) -> subprocess.CompletedProcess:
    """Run a kubectl command and return the result."""
    full_command = ["kubectl"] + command
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
        logger.error(f"Kubectl command failed: {e.stderr}")
        raise

def run_eksctl_command(command: List[str], logger: logging.Logger) -> subprocess.CompletedProcess:
    """Run an eksctl command and return the result."""
    full_command = ["eksctl"] + command
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
        logger.error(f"Eksctl command failed: {e.stderr}")
        raise

def check_cluster_connection(logger: logging.Logger) -> bool:
    """Check if kubectl can connect to a cluster."""
    try:
        result = run_kubectl_command(["cluster-info"], logger)
        return "is running at" in result.stdout
    except subprocess.CalledProcessError:
        return False

def get_cluster_info(logger: logging.Logger) -> Dict[str, Any]:
    """Get cluster information."""
    try:
        result = run_kubectl_command(["cluster-info"], logger)
        return {"connected": True, "info": result.stdout}
    except subprocess.CalledProcessError as e:
        return {"connected": False, "error": str(e)}

def apply_manifest(manifest_file: str, logger: logging.Logger) -> bool:
    """Apply a Kubernetes manifest file."""
    try:
        result = run_kubectl_command(["apply", "-f", manifest_file], logger)
        logger.info(f"Manifest applied successfully: {result.stdout}")
        return True
    except subprocess.CalledProcessError:
        return False

def check_resource_exists(resource_type: str, resource_name: str, namespace: str = "default", logger: logging.Logger = None) -> bool:
    """Check if a Kubernetes resource exists."""
    try:
        command = ["get", resource_type, resource_name]
        if namespace != "default":
            command.extend(["-n", namespace])

        result = run_kubectl_command(command, logger)
        return resource_name in result.stdout
    except subprocess.CalledProcessError:
        return False

def get_nodes(logger: logging.Logger) -> List[Dict[str, Any]]:
    """Get list of nodes in the cluster."""
    try:
        result = run_kubectl_command(["get", "nodes", "-o", "json"], logger)
        nodes_data = json.loads(result.stdout)
        return nodes_data.get("items", [])
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []
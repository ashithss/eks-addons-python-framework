import logging
from utils.helm import check_helm_installed, add_helm_repo, install_helm_chart
from utils.kubectl import run_kubectl_command, check_cluster_connection

class NvidiaDevicePluginInstaller:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.chart_name = "nvidia/gpu-operator"
        self.chart_repo = "https://nvidia.github.io/gpu-operator"
        self.repo_name = "nvidia"
        self.namespace = "gpu-operator"
        self.release_name = "gpu-operator"

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met."""
        self.logger.info("Checking prerequisites for NVIDIA Device Plugin...")

        # Check cluster connection
        if not check_cluster_connection(self.logger):
            self.logger.error("Cannot connect to Kubernetes cluster. Please ensure kubectl is configured.")
            return False

        # Check Helm installation
        if not check_helm_installed(self.logger):
            self.logger.error("Helm is not installed or not accessible.")
            return False

        return True

    def install(self, enable_time_slicing: bool = False) -> bool:
        """Install NVIDIA Device Plugin/GPU Operator."""
        self.logger.info("Installing NVIDIA Device Plugin...")

        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Add Helm repo
        if not add_helm_repo(self.repo_name, self.chart_repo, self.logger):
            self.logger.error("Failed to add Helm repository.")
            return False

        # Prepare values
        values = {
            "operator": {
                "defaultRuntime": "containerd"
            }
        }

        # Enable time-slicing if requested
        if enable_time_slicing:
            values["devicePlugin"] = {
                "config": {
                    "name": "time-slicing-config",
                    "default": "any"
                }
            }

        # Install via Helm
        if not install_helm_chart(
            release_name=self.release_name,
            chart_name=self.chart_name,
            namespace=self.namespace,
            create_namespace=True,
            values=values,
            logger=self.logger
        ):
            self.logger.error("Failed to install NVIDIA Device Plugin via Helm.")
            return False

        self.logger.info("NVIDIA Device Plugin installed successfully.")
        return True

    def check_if_installed(self) -> bool:
        """Check if NVIDIA Device Plugin is already installed."""
        try:
            self.logger.info("Checking if NVIDIA Device Plugin is already installed...")

            # Check if the daemonset exists
            cmd = [
                "get", "daemonset", "nvidia-device-plugin-daemonset",
                "-n", self.namespace,
                "--ignore-not-found=true"
            ]

            result = run_kubectl_command(cmd, self.logger)
            # If output is not empty, the daemonset exists
            if result.stdout.strip():
                self.logger.info("NVIDIA Device Plugin is already installed.")
                return True
            else:
                self.logger.info("NVIDIA Device Plugin is not installed.")
                return False
        except Exception as e:
            self.logger.debug(f"Error checking installation status: {str(e)}")
            return False

    def validate_installation(self) -> bool:
        """Validate that the plugin is installed and running."""
        try:
            self.logger.info("Validating NVIDIA Device Plugin installation...")

            # Check daemonset
            cmd = [
                "get", "daemonset", "nvidia-device-plugin-daemonset",
                "-n", self.namespace,
                "-o", "jsonpath={.status.numberReady}"
            ]

            result = run_kubectl_command(cmd, self.logger)
            ready_nodes = int(result.stdout.strip() or 0)

            if ready_nodes > 0:
                self.logger.info("NVIDIA Device Plugin is running on %d nodes.", ready_nodes)

                # Show GPU resources
                nodes_cmd = [
                    "get", "nodes",
                    "-o", "jsonpath='{.items[*].status.allocatable.nvidia\\.com/gpu}'"
                ]
                nodes_result = run_kubectl_command(nodes_cmd, self.logger)
                self.logger.info("Available GPU resources: %s", nodes_result.stdout.strip())

                return True
            else:
                self.logger.warning("NVIDIA Device Plugin is not ready yet.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to validate installation: {str(e)}")
            return False

    def recommend_gpu_instances(self) -> dict:
        """Provide GPU instance recommendations."""
        recommendations = {
            "p3": {
                "family": "P3",
                "gpus": "1/4/8 Tesla V100",
                "use_case": "General ML/DL training workloads"
            },
            "p4": {
                "family": "P4",
                "gpus": "1/2/4/8 A100",
                "use_case": "High-performance ML/DL training"
            },
            "g4dn": {
                "family": "G4dn",
                "gpus": "1 T4",
                "use_case": "ML inference, game streaming"
            },
            "g5": {
                "family": "G5",
                "gpus": "1/4/8 A10G",
                "use_case": "Graphics rendering, game streaming, ML inference"
            }
        }

        self.logger.info("Recommended GPU instances for EKS:")
        for key, value in recommendations.items():
            self.logger.info(f"  - {key}: {value['gpus']} GPUs - {value['use_case']}")

        return recommendations
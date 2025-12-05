import logging
from utils.helm import check_helm_installed, add_helm_repo, install_helm_chart
from utils.kubectl import run_kubectl_command, check_cluster_connection

class KyvernoInstaller:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.chart_name = "kyverno/kyverno"
        self.chart_repo = "https://kyverno.github.io/kyverno/"
        self.repo_name = "kyverno"
        self.namespace = "kyverno"
        self.release_name = "kyverno"

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met."""
        self.logger.info("Checking prerequisites for Kyverno...")

        # Check cluster connection
        if not check_cluster_connection(self.logger):
            self.logger.error("Cannot connect to Kubernetes cluster. Please ensure kubectl is configured.")
            return False

        # Check Helm installation
        if not check_helm_installed(self.logger):
            self.logger.error("Helm is not installed or not accessible.")
            return False

        return True

    def install(self) -> bool:
        """Install Kyverno policy engine."""
        self.logger.info("Installing Kyverno...")

        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Add Helm repo
        if not add_helm_repo(self.repo_name, self.chart_repo, self.logger):
            self.logger.error("Failed to add Helm repository.")
            return False

        # Install via Helm
        if not install_helm_chart(
            release_name=self.release_name,
            chart_name=self.chart_name,
            namespace=self.namespace,
            create_namespace=True,
            logger=self.logger
        ):
            self.logger.error("Failed to install Kyverno via Helm.")
            return False

        self.logger.info("Kyverno installed successfully.")
        return True

    def check_if_installed(self) -> bool:
        """Check if Kyverno is already installed."""
        try:
            self.logger.info("Checking if Kyverno is already installed...")

            # Check if the deployment exists
            cmd = [
                "get", "deployment", self.release_name,
                "-n", self.namespace,
                "--ignore-not-found=true"
            ]

            result = run_kubectl_command(cmd, self.logger)
            # If output is not empty, the deployment exists
            if result.stdout.strip():
                self.logger.info("Kyverno is already installed.")
                return True
            else:
                self.logger.info("Kyverno is not installed.")
                return False
        except Exception as e:
            self.logger.debug(f"Error checking installation status: {str(e)}")
            return False

    def validate_installation(self) -> bool:
        """Validate that Kyverno is installed and running."""
        try:
            self.logger.info("Validating Kyverno installation...")

            # Check deployment
            cmd = [
                "get", "deployment", self.release_name,
                "-n", self.namespace,
                "-o", "jsonpath={.status.readyReplicas}"
            ]

            result = run_kubectl_command(cmd, self.logger)
            ready_replicas = int(result.stdout.strip() or 0)

            if ready_replicas > 0:
                self.logger.info("Kyverno controller is running.")

                # Check webhook configurations
                webhook_cmd = [
                    "get", "validatingwebhookconfiguration",
                    "-o", "jsonpath={.items[*].metadata.name}"
                ]
                webhook_result = run_kubectl_command(webhook_cmd, self.logger)

                if "kyverno" in webhook_result.stdout:
                    self.logger.info("Kyverno webhook configurations are in place.")
                    return True
                else:
                    self.logger.warning("Kyverno webhook configurations not found.")
                    return False
            else:
                self.logger.warning("Kyverno controller is not ready yet.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to validate installation: {str(e)}")
            return False
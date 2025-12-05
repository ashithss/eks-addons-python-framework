import logging
from utils.helm import check_helm_installed, add_helm_repo, install_helm_chart
from utils.kubectl import run_kubectl_command, check_cluster_connection

class CalicoInstaller:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.chart_name = "projectcalico/tigera-operator"
        self.chart_repo = "https://docs.tigera.io/calico/charts"
        self.repo_name = "calico"
        self.namespace = "calico-system"
        self.release_name = "calico"

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met."""
        self.logger.info("Checking prerequisites for Calico...")

        # Check cluster connection
        if not check_cluster_connection(self.logger):
            self.logger.error("Cannot connect to Kubernetes cluster. Please ensure kubectl is configured.")
            return False

        # Check Helm installation
        if not check_helm_installed(self.logger):
            self.logger.error("Helm is not installed or not accessible.")
            return False

        # Check that AWS VPC CNI is still in place
        if not self._check_aws_cni():
            self.logger.error("AWS VPC CNI does not appear to be properly configured.")
            return False

        return True

    def _check_aws_cni(self) -> bool:
        """Check that AWS VPC CNI is present."""
        try:
            cmd = [
                "get", "daemonset", "aws-node",
                "-n", "kube-system",
                "-o", "jsonpath={.metadata.name}"
            ]

            result = run_kubectl_command(cmd, self.logger)
            return "aws-node" in result.stdout
        except Exception:
            return False

    def install(self) -> bool:
        """Install Calico policy engine."""
        self.logger.info("Installing Calico Network Policy Engine...")

        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Add Helm repo
        if not add_helm_repo(self.repo_name, self.chart_repo, self.logger):
            self.logger.error("Failed to add Helm repository.")
            return False

        # Install via Helm with policy-only mode
        values = {
            "installation": {
                "enabled": True,
                "kubernetesProvider": "EKS",
                "cni": {
                    "type": "AmazonVPC"
                }
            }
        }

        if not install_helm_chart(
            release_name=self.release_name,
            chart_name=self.chart_name,
            namespace=self.namespace,
            create_namespace=True,
            values=values,
            logger=self.logger
        ):
            self.logger.error("Failed to install Calico via Helm.")
            return False

        self.logger.info("Calico installed successfully in policy-only mode.")
        return True

    def validate_installation(self) -> bool:
        """Validate that Calico is installed and running."""
        try:
            self.logger.info("Validating Calico installation...")

            # Check tigera-operator deployment
            cmd = [
                "get", "deployment", "tigera-operator",
                "-n", self.namespace,
                "-o", "jsonpath={.status.readyReplicas}"
            ]

            result = run_kubectl_command(cmd, self.logger)
            ready_replicas = int(result.stdout.strip() or 0)

            if ready_replicas > 0:
                self.logger.info("Calico operator is running.")

                # Check that AWS CNI is still present
                if self._check_aws_cni():
                    self.logger.info("AWS VPC CNI is still in place as expected.")
                else:
                    self.logger.warning("AWS VPC CNI appears to have been affected.")

                # Check calico-node daemonset
                node_cmd = [
                    "get", "daemonset", "calico-node",
                    "-n", "calico-system",
                    "-o", "jsonpath={.status.numberReady}"
                ]
                node_result = run_kubectl_command(node_cmd, self.logger)
                ready_nodes = int(node_result.stdout.strip() or 0)

                if ready_nodes > 0:
                    self.logger.info("Calico policy engine is running on %d nodes.", ready_nodes)
                    return True
                else:
                    self.logger.warning("Calico policy engine is not ready yet.")
                    return False
            else:
                self.logger.warning("Calico operator is not ready yet.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to validate installation: {str(e)}")
            return False
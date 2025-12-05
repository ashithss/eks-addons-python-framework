import logging
import os
from utils.helm import check_helm_installed, add_helm_repo, install_helm_chart
from utils.kubectl import run_kubectl_command, check_cluster_connection
from jinja2 import Environment, FileSystemLoader

class KarpenterInstaller:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.chart_name = "oci://public.ecr.aws/karpenter/karpenter"
        self.namespace = "karpenter"
        self.release_name = "karpenter"

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met."""
        self.logger.info("Checking prerequisites for Karpenter...")

        # Check cluster connection
        if not check_cluster_connection(self.logger):
            self.logger.error("Cannot connect to Kubernetes cluster. Please ensure kubectl is configured.")
            return False

        # Check Helm installation
        if not check_helm_installed(self.logger):
            self.logger.error("Helm is not installed or not accessible.")
            return False

        return True

    def install_crds(self) -> bool:
        """Install Karpenter CRDs."""
        try:
            self.logger.info("Installing Karpenter CRDs...")

            # Install CRDs using kubectl
            crd_url = "https://raw.githubusercontent.com/aws/karpenter-provider-aws/v0.37.0/pkg/apis/crds/karpenter.sh_provisioners.yaml"
            cmd = ["apply", "-f", crd_url]

            result = run_kubectl_command(cmd, self.logger)
            self.logger.info("Karpenter CRDs installed successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to install Karpenter CRDs: {str(e)}")
            return False

    def install(self, cluster_name: str, region: str, cluster_endpoint: str) -> bool:
        """Install Karpenter controller."""
        self.logger.info("Installing Karpenter...")

        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Install CRDs
        if not self.install_crds():
            self.logger.error("Failed to install Karpenter CRDs.")
            return False

        # Prepare IAM role (simplified - in practice this would involve creating an IAM role)
        account_id = self._get_account_id()
        if not account_id:
            self.logger.error("Failed to get AWS account ID.")
            return False

        # Install via Helm
        values = {
            "settings": {
                "clusterName": cluster_name,
                "region": region,
                "clusterEndpoint": cluster_endpoint
            },
            "serviceAccount": {
                "annotations": {
                    "eks.amazonaws.com/role-arn": f"arn:aws:iam::{account_id}:role/KarpenterControllerRole-{cluster_name}"
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
            self.logger.error("Failed to install Karpenter via Helm.")
            return False

        self.logger.info("Karpenter installed successfully.")
        return True

    def _get_account_id(self) -> str:
        """Get AWS account ID."""
        try:
            cmd = ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"]
            result = run_kubectl_command(cmd[:3] + cmd[4:], self.logger)
            return result.stdout.strip()
        except Exception as e:
            self.logger.error(f"Failed to get AWS account ID: {str(e)}")
            return ""

    def generate_nodepool_yaml(self, cluster_name: str, output_dir: str = "output/") -> str:
        """Generate NodePool and EC2NodeClass YAML configuration."""
        try:
            self.logger.info("Generating Karpenter NodePool configuration...")

            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, "nodepool.yaml")

            # Set up Jinja2 environment
            template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
            env = Environment(loader=FileSystemLoader(template_dir))
            template = env.get_template("karpenter_nodepool.yaml.j2")

            # Render template with sample data
            rendered = template.render(
                cluster_name=cluster_name,
                nodepool_name=f"{cluster_name}-default-nodepool",
                nodeclass_name=f"{cluster_name}-default-nodeclass"
            )

            # Write to file
            with open(output_file, "w") as f:
                f.write(rendered)

            self.logger.info(f"NodePool configuration saved to {output_file}")
            return output_file
        except Exception as e:
            self.logger.error(f"Failed to generate NodePool YAML: {str(e)}")
            return ""

    def validate_installation(self) -> bool:
        """Validate that Karpenter is installed and running."""
        try:
            self.logger.info("Validating Karpenter installation...")

            # Check deployment
            cmd = [
                "get", "deployment", self.release_name,
                "-n", self.namespace,
                "-o", "jsonpath={.status.readyReplicas}"
            ]

            result = run_kubectl_command(cmd, self.logger)
            ready_replicas = int(result.stdout.strip() or 0)

            if ready_replicas > 0:
                self.logger.info("Karpenter controller is running.")
                return True
            else:
                self.logger.warning("Karpenter controller is not ready yet.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to validate installation: {str(e)}")
            return False
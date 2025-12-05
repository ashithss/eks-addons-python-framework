import logging
from utils.helm import check_helm_installed, add_helm_repo, install_helm_chart
from utils.kubectl import run_kubectl_command, check_cluster_connection

class AWSLoadBalancerControllerInstaller:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.chart_name = "aws-load-balancer-controller"
        self.chart_repo = "https://aws.github.io/eks-charts"
        self.repo_name = "eks"
        self.namespace = "kube-system"
        self.release_name = "aws-load-balancer-controller"

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met."""
        self.logger.info("Checking prerequisites for AWS Load Balancer Controller...")

        # Check cluster connection
        if not check_cluster_connection(self.logger):
            self.logger.error("Cannot connect to Kubernetes cluster. Please ensure kubectl is configured.")
            return False

        # Check Helm installation
        if not check_helm_installed(self.logger):
            self.logger.error("Helm is not installed or not accessible.")
            return False

        return True

    def create_iam_service_account(self, cluster_name: str, region: str) -> bool:
        """Create IAM service account for the controller."""
        try:
            self.logger.info("Creating IAM service account for AWS Load Balancer Controller...")

            # Associate OIDC provider (if needed)
            oidc_cmd = [
                "eksctl", "utils", "associate-iam-oidc-provider",
                "--region", region,
                "--cluster", cluster_name,
                "--approve"
            ]

            result = run_kubectl_command(oidc_cmd[:-3] + ["--dry-run"], self.logger)
            if "already exists" not in result.stdout:
                run_kubectl_command(oidc_cmd, self.logger)

            # Create IAM service account
            sa_cmd = [
                "eksctl", "create", "iamserviceaccount",
                "--region", region,
                "--cluster", cluster_name,
                "--namespace", self.namespace,
                "--name", self.release_name,
                "--attach-policy-arn", "arn:aws:iam::aws:policy/AWSLoadBalancerControllerIAMPolicy",
                "--override-existing-serviceaccounts",
                "--approve"
            ]

            run_kubectl_command(sa_cmd, self.logger)
            self.logger.info("IAM service account created successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create IAM service account: {str(e)}")
            return False

    def install(self, cluster_name: str, region: str) -> bool:
        """Install AWS Load Balancer Controller."""
        self.logger.info("Installing AWS Load Balancer Controller...")

        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Add Helm repo
        if not add_helm_repo(self.repo_name, self.chart_repo, self.logger):
            self.logger.error("Failed to add Helm repository.")
            return False

        # Create IAM service account
        if not self.create_iam_service_account(cluster_name, region):
            self.logger.error("Failed to create IAM service account.")
            return False

        # Install via Helm
        vpc_id = self._get_vpc_id(cluster_name, region)
        if not vpc_id:
            self.logger.error("Failed to get VPC ID for the cluster.")
            return False

        values = {
            "clusterName": cluster_name,
            "serviceAccount": {
                "create": False,
                "name": self.release_name
            },
            "region": region,
            "vpcId": vpc_id
        }

        if not install_helm_chart(
            release_name=self.release_name,
            chart_name=f"{self.repo_name}/{self.chart_name}",
            namespace=self.namespace,
            values=values,
            logger=self.logger
        ):
            self.logger.error("Failed to install AWS Load Balancer Controller via Helm.")
            return False

        self.logger.info("AWS Load Balancer Controller installed successfully.")
        return True

    def _get_vpc_id(self, cluster_name: str, region: str) -> str:
        """Get VPC ID for the EKS cluster."""
        try:
            cmd = [
                "aws", "eks", "describe-cluster",
                "--name", cluster_name,
                "--region", region,
                "--query", "cluster.resourcesVpcConfig.vpcId",
                "--output", "text"
            ]

            result = run_kubectl_command(cmd[:4] + cmd[5:], self.logger)
            return result.stdout.strip()
        except Exception as e:
            self.logger.error(f"Failed to get VPC ID: {str(e)}")
            return ""

    def validate_installation(self) -> bool:
        """Validate that the controller is installed and running."""
        try:
            self.logger.info("Validating AWS Load Balancer Controller installation...")

            # Check deployment
            cmd = [
                "get", "deployment", self.release_name,
                "-n", self.namespace,
                "-o", "jsonpath={.status.readyReplicas}"
            ]

            result = run_kubectl_command(cmd, self.logger)
            ready_replicas = int(result.stdout.strip() or 0)

            if ready_replicas > 0:
                self.logger.info("AWS Load Balancer Controller is running.")
                return True
            else:
                self.logger.warning("AWS Load Balancer Controller is not ready yet.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to validate installation: {str(e)}")
            return False
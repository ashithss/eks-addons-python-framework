import logging
import subprocess
import json
import os
import tempfile
from utils.helm import check_helm_installed, add_helm_repo, install_helm_chart
from utils.kubectl import run_kubectl_command, run_eksctl_command, check_cluster_connection

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

    def create_iam_service_account(self, cluster_name: str, region: str, account_id: str) -> bool:
        """Create IAM service account for the controller following AWS documentation."""
        try:
            self.logger.info("Creating IAM service account for AWS Load Balancer Controller...")

            # Associate OIDC provider (if needed)
            oidc_cmd = [
                "utils", "associate-iam-oidc-provider",
                "--region", region,
                "--cluster", cluster_name,
                "--approve"
            ]

            # Try to associate OIDC provider, it will succeed or indicate it already exists
            try:
                run_eksctl_command(oidc_cmd, self.logger)
                self.logger.info("OIDC provider associated successfully.")
            except subprocess.CalledProcessError as e:
                # If it already exists, that's fine
                if "already exists" in str(e) or "already associated" in str(e):
                    self.logger.info("OIDC provider already exists, continuing...")
                else:
                    # Re-raise if it's a different error
                    raise

            # Download IAM policy
            self.logger.info("Downloading IAM policy for AWS Load Balancer Controller...")
            policy_url = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.14.1/docs/install/iam_policy.json"

            # Create temporary file for policy
            temp_fd, temp_policy_file = tempfile.mkstemp(suffix='.json')
            os.close(temp_fd)  # Close the file descriptor

            try:
                # Download the policy
                curl_cmd = ["curl", "-o", temp_policy_file, policy_url]
                subprocess.run(curl_cmd, check=True, capture_output=True)

                # Create IAM policy
                policy_cmd = [
                    "aws", "iam", "create-policy",
                    "--policy-name", "AWSLoadBalancerControllerIAMPolicy",
                    "--policy-document", f"file://{temp_policy_file}"
                ]

                # Run aws command directly
                result = subprocess.run(policy_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self.logger.info("IAM policy created successfully.")
                else:
                    # If policy already exists, that's fine
                    if "EntityAlreadyExists" in result.stderr:
                        self.logger.info("IAM policy already exists, continuing...")
                    else:
                        self.logger.error(f"Failed to create IAM policy: {result.stderr}")
                        raise subprocess.CalledProcessError(result.returncode, policy_cmd, result.stderr)

            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to create IAM policy: {str(e)}")
                raise
            finally:
                # Clean up temporary file
                if os.path.exists(temp_policy_file):
                    os.unlink(temp_policy_file)

            # Create IAM service account with the proper policy ARN
            policy_arn = f"arn:aws:iam::{account_id}:policy/AWSLoadBalancerControllerIAMPolicy"
            sa_cmd = [
                "create", "iamserviceaccount",
                "--region", region,
                "--cluster", cluster_name,
                "--namespace", self.namespace,
                "--name", self.release_name,
                "--attach-policy-arn", policy_arn,
                "--override-existing-serviceaccounts",
                "--approve"
            ]

            run_eksctl_command(sa_cmd, self.logger)
            self.logger.info("IAM service account created successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create IAM service account: {str(e)}")
            return False

    def install(self, cluster_name: str, region: str, account_id: str = None) -> bool:
        """Install AWS Load Balancer Controller following AWS documentation."""
        self.logger.info("Installing AWS Load Balancer Controller...")

        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Get account ID if not provided
        if not account_id:
            account_id = self._get_account_id()
            if not account_id:
                self.logger.error("Failed to get AWS account ID.")
                return False

        # Add Helm repo
        if not add_helm_repo(self.repo_name, self.chart_repo, self.logger):
            self.logger.error("Failed to add Helm repository.")
            return False

        # Update Helm repo
        try:
            from utils.helm import run_helm_command
            run_helm_command(["repo", "update", self.repo_name], self.logger)
            self.logger.info("Helm repository updated successfully.")
        except Exception as e:
            self.logger.error(f"Failed to update Helm repository: {str(e)}")
            return False

        # Create IAM service account
        if not self.create_iam_service_account(cluster_name, region, account_id):
            self.logger.error("Failed to create IAM service account.")
            return False

        # Install CRDs (only for fresh installation, not upgrades)
        if not self._install_crds():
            self.logger.error("Failed to install CRDs.")
            return False

        # Install via Helm with proper values
        values = {
            "clusterName": cluster_name,
            "serviceAccount": {
                "create": False,
                "name": self.release_name
            }
        }

        # For nodes with restricted IMDS access, Fargate, or Hybrid Nodes, add region and VPC ID
        # We'll add these by default to be safe
        vpc_id = self._get_vpc_id(cluster_name, region)
        if vpc_id:
            values["region"] = region
            values["vpcId"] = vpc_id

        if not install_helm_chart(
            release_name=self.release_name,
            chart_name=f"{self.repo_name}/{self.chart_name}",
            namespace=self.namespace,
            version="1.14.0",  # Specific version as per documentation
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

            # Run aws command directly, not through kubectl
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception as e:
            self.logger.error(f"Failed to get VPC ID: {str(e)}")
            return ""

    def _get_account_id(self) -> str:
        """Get AWS account ID."""
        try:
            cmd = [
                "aws", "sts", "get-caller-identity",
                "--query", "Account",
                "--output", "text"
            ]

            # Run aws command directly
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception as e:
            self.logger.error(f"Failed to get AWS account ID: {str(e)}")
            return ""

    def _install_crds(self) -> bool:
        """Install Custom Resource Definitions for the AWS Load Balancer Controller following AWS documentation."""
        try:
            self.logger.info("Installing CRDs for AWS Load Balancer Controller...")

            # Download and apply CRDs using the official URL from documentation
            crd_url = "https://raw.githubusercontent.com/aws/eks-charts/master/stable/aws-load-balancer-controller/crds/crds.yaml"

            # Create temporary file
            temp_fd, temp_filename = tempfile.mkstemp(suffix='.yaml')
            os.close(temp_fd)  # Close the file descriptor as we'll use the filename

            try:
                # Download the CRDs
                curl_cmd = ["curl", "-o", temp_filename, crd_url]
                subprocess.run(curl_cmd, check=True, capture_output=True)

                # Apply the CRDs
                apply_cmd = ["apply", "-f", temp_filename]
                run_kubectl_command(apply_cmd, self.logger)

                self.logger.info("CRDs installed successfully.")
                return True
            finally:
                # Clean up temporary file
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)

        except Exception as e:
            self.logger.error(f"Failed to install CRDs: {str(e)}")
            return False

    def check_if_installed(self) -> bool:
        """Check if AWS Load Balancer Controller is already installed."""
        try:
            self.logger.info("Checking if AWS Load Balancer Controller is already installed...")

            # Check if the deployment exists
            cmd = [
                "get", "deployment", "-n", self.namespace, self.release_name,
                "--ignore-not-found=true"
            ]

            result = run_kubectl_command(cmd, self.logger)
            # If output is not empty, the deployment exists
            if result.stdout.strip():
                self.logger.info("AWS Load Balancer Controller is already installed.")
                return True
            else:
                self.logger.info("AWS Load Balancer Controller is not installed.")
                return False
        except Exception as e:
            self.logger.debug(f"Error checking installation status: {str(e)}")
            return False

    def validate_installation(self) -> bool:
        """Validate that the controller is installed and running following AWS documentation."""
        try:
            self.logger.info("Validating AWS Load Balancer Controller installation...")

            # Check deployment as per AWS documentation
            cmd = [
                "get", "deployment", "-n", self.namespace, self.release_name,
                "-o", "jsonpath={.status.readyReplicas}"
            ]

            result = run_kubectl_command(cmd, self.logger)
            ready_replicas = int(result.stdout.strip() or 0)

            if ready_replicas > 0:
                self.logger.info("AWS Load Balancer Controller is running.")
                self.logger.info("Expected output: 2/2 for Helm installation or 1/1 for manifest installation.")
                return True
            else:
                self.logger.warning("AWS Load Balancer Controller is not ready yet.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to validate installation: {str(e)}")
            return False
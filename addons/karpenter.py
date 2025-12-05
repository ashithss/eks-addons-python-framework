import logging
import os
import subprocess
import tempfile
from utils.helm import check_helm_installed, add_helm_repo, install_helm_chart, run_helm_command
from utils.kubectl import run_kubectl_command, check_cluster_connection, run_eksctl_command
from jinja2 import Environment, FileSystemLoader

class KarpenterInstaller:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.chart_name = "oci://public.ecr.aws/karpenter/karpenter"
        self.chart_version = "1.8.1"
        self.namespace = "kube-system"  # As per official documentation
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
        """Install Karpenter controller following official documentation."""
        self.logger.info("Installing Karpenter...")

        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Get account ID
        account_id = self._get_account_id()
        if not account_id:
            self.logger.error("Failed to get AWS account ID.")
            return False

        # Create CloudFormation stack as per official documentation
        if not self._create_cloudformation_stack(cluster_name, region, account_id):
            self.logger.error("Failed to create CloudFormation stack.")
            return False

        # Add required IAM identity mapping
        if not self._add_iam_identity_mapping(cluster_name, region, account_id):
            self.logger.error("Failed to add IAM identity mapping.")
            return False

        # Create service linked role for EC2 Spot (if needed)
        self._create_spot_service_linked_role()

        # Logout of helm registry to perform an unauthenticated pull against the public ECR
        try:
            subprocess.run(["helm", "registry", "logout", "public.ecr.aws"],
                         capture_output=True, text=True)
            self.logger.info("Logged out of helm registry.")
        except Exception as e:
            self.logger.warning(f"Failed to logout of helm registry: {str(e)}")

        # Install via Helm with proper settings as per official documentation
        values = {
            "settings": {
                "clusterName": cluster_name,
                "interruptionQueue": cluster_name
            },
            "controller": {
                "resources": {
                    "requests": {
                        "cpu": "1",
                        "memory": "1Gi"
                    },
                    "limits": {
                        "cpu": "1",
                        "memory": "1Gi"
                    }
                }
            }
        }

        if not install_helm_chart(
            release_name=self.release_name,
            chart_name=self.chart_name,
            namespace=self.namespace,
            version=self.chart_version,
            create_namespace=False,  # Already exists in kube-system
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
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception as e:
            self.logger.error(f"Failed to get AWS account ID: {str(e)}")
            return ""

    def _create_cloudformation_stack(self, cluster_name: str, region: str, account_id: str) -> bool:
        """Create CloudFormation stack as per official documentation."""
        try:
            self.logger.info("Creating CloudFormation stack for Karpenter...")

            # Download CloudFormation template
            template_url = f"https://raw.githubusercontent.com/aws/karpenter-provider-aws/v{self.chart_version}/website/content/en/preview/getting-started/getting-started-with-karpenter/cloudformation.yaml"

            temp_fd, temp_template_file = tempfile.mkstemp(suffix='.yaml')
            os.close(temp_fd)

            try:
                # Download the template
                curl_cmd = ["curl", "-fsSL", template_url, "-o", temp_template_file]
                curl_result = subprocess.run(curl_cmd, capture_output=True, text=True)
                if curl_result.returncode != 0:
                    self.logger.error(f"Failed to download CloudFormation template: {curl_result.stderr}")
                    return False

                # Deploy CloudFormation stack
                stack_name = f"Karpenter-{cluster_name}"
                deploy_cmd = [
                    "aws", "cloudformation", "deploy",
                    "--stack-name", stack_name,
                    "--template-file", temp_template_file,
                    "--capabilities", "CAPABILITY_NAMED_IAM",
                    "--parameter-overrides", f"ClusterName={cluster_name}",
                    "--region", region
                ]

                deploy_result = subprocess.run(deploy_cmd, capture_output=True, text=True)
                if deploy_result.returncode == 0:
                    self.logger.info("CloudFormation stack created successfully.")
                    return True
                else:
                    # If stack already exists, that's fine
                    if "already exists" in deploy_result.stderr:
                        self.logger.info("CloudFormation stack already exists, continuing...")
                        return True
                    else:
                        self.logger.error(f"Failed to create CloudFormation stack: {deploy_result.stderr}")
                        return False

            finally:
                # Clean up temporary file
                if os.path.exists(temp_template_file):
                    os.unlink(temp_template_file)

        except Exception as e:
            self.logger.error(f"Failed to create CloudFormation stack: {str(e)}")
            return False

    def _add_iam_identity_mapping(self, cluster_name: str, region: str, account_id: str) -> bool:
        """Add IAM identity mapping for Karpenter node role."""
        try:
            self.logger.info("Adding IAM identity mapping for Karpenter...")

            # Add IAM identity mapping using eksctl
            mapping_cmd = [
                "create", "iamidentitymapping",
                "--cluster", cluster_name,
                "--region", region,
                "--arn", f"arn:aws:iam::{account_id}:role/KarpenterNodeRole-{cluster_name}",
                "--username", "system:node:{{EC2PrivateDNSName}}",
                "--group", "system:bootstrappers",
                "--group", "system:nodes"
            ]

            run_eksctl_command(mapping_cmd, self.logger)
            self.logger.info("IAM identity mapping added successfully.")
            return True

        except subprocess.CalledProcessError as e:
            # If mapping already exists, that's fine
            if "already exists" in str(e) or "already exists" in e.stderr:
                self.logger.info("IAM identity mapping already exists, continuing...")
                return True
            else:
                self.logger.error(f"Failed to add IAM identity mapping: {e.stderr}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to add IAM identity mapping: {str(e)}")
            return False

    def _create_spot_service_linked_role(self) -> bool:
        """Create service linked role for EC2 Spot if needed."""
        try:
            self.logger.info("Creating service linked role for EC2 Spot...")

            cmd = [
                "aws", "iam", "create-service-linked-role",
                "--aws-service-name", "spot.amazonaws.com"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info("Service linked role for EC2 Spot created successfully.")
                return True
            else:
                # If role already exists, that's fine
                if "has been taken" in result.stderr or "InvalidUserType" in result.stderr:
                    self.logger.info("Service linked role for EC2 Spot already exists, continuing...")
                    return True
                else:
                    self.logger.warning(f"Failed to create service linked role: {result.stderr}")
                    # This is not fatal, as the role might already exist or might be created by other means
                    return True

        except Exception as e:
            self.logger.warning(f"Exception while creating service linked role: {str(e)}")
            # This is not fatal, as the role might already exist or might be created by other means
            return True

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

    def check_if_installed(self) -> bool:
        """Check if Karpenter is already installed."""
        try:
            self.logger.info("Checking if Karpenter is already installed...")

            # Check if the deployment exists
            cmd = [
                "get", "deployment", self.release_name,
                "-n", self.namespace,
                "--ignore-not-found=true"
            ]

            result = run_kubectl_command(cmd, self.logger)
            # If output is not empty, the deployment exists
            if result.stdout.strip():
                self.logger.info("Karpenter is already installed.")
                return True
            else:
                self.logger.info("Karpenter is not installed.")
                return False
        except Exception as e:
            self.logger.debug(f"Error checking installation status: {str(e)}")
            return False

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
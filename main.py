#!/usr/bin/env python3

import sys
import argparse
import logging
from utils.logger import setup_logger, log_section
from utils.kubectl import check_cluster_connection, get_cluster_info
from utils.helm import check_helm_installed

# Import addon installers
from addons.aws_lb_controller import AWSLoadBalancerControllerInstaller
from addons.nvidia_plugin import NvidiaDevicePluginInstaller
from addons.karpenter import KarpenterInstaller
from addons.kyverno import KyvernoInstaller
from addons.calico import CalicoInstaller

def display_menu():
    """Display the main menu."""
    print("\n" + "="*60)
    print("EKS Addon Installer")
    print("="*60)
    print("Select addon(s) to install (comma-separated for multiple):")
    print("1. AWS Load Balancer Controller")
    print("2. Karpenter")
    print("3. Kyverno")
    print("4. Calico Network Policy")
    print("5. Nvidia Device Plugin")
    print("6. Future Addons (Placeholder)")
    print("7. Exit")
    print("-"*60)

def get_user_selection():
    """Get user selection from menu."""
    while True:
        try:
            selection = input("Enter your choice (e.g., 1,3,5 or 2): ").strip()
            if selection == "7":
                return []

            choices = [int(x.strip()) for x in selection.split(",") if x.strip()]
            if all(1 <= choice <= 7 for choice in choices):
                return choices
            else:
                print("Invalid choice. Please select numbers between 1-7.")
        except ValueError:
            print("Invalid input. Please enter numbers separated by commas.")

def check_environment(logger):
    """Check if the environment is ready for installation."""
    log_section(logger, "Environment Check")

    # Check cluster connection
    logger.info("Checking Kubernetes cluster connectivity...")
    if not check_cluster_connection(logger):
        logger.error("Cannot connect to Kubernetes cluster. Please ensure kubectl is configured.")
        return False

    # Show cluster info
    cluster_info = get_cluster_info(logger)
    if cluster_info.get("connected"):
        logger.info("Connected to cluster successfully.")

    # Check Helm
    logger.info("Checking Helm installation...")
    if not check_helm_installed(logger):
        logger.error("Helm is not installed or not accessible.")
        return False

    logger.info("Environment check passed.")
    return True

def install_addons(selected_addons, args, logger):
    """Install selected addons."""
    installers = {
        1: ("AWS Load Balancer Controller", AWSLoadBalancerControllerInstaller(logger)),
        2: ("Karpenter", KarpenterInstaller(logger)),
        3: ("Kyverno", KyvernoInstaller(logger)),
        4: ("Calico Network Policy", CalicoInstaller(logger)),
        5: ("Nvidia Device Plugin", NvidiaDevicePluginInstaller(logger)),
    }

    # Install in order
    for choice in selected_addons:
        if choice in installers:
            name, installer = installers[choice]

            # Check if addon is already installed
            if hasattr(installer, 'check_if_installed') and installer.check_if_installed():
                logger.info(f"{name} is already installed. Skipping installation.")
                continue

            log_section(logger, f"Installing {name}")

            try:
                if choice == 1:  # AWS Load Balancer Controller
                    success = installer.install(args.cluster_name, args.region, args.account_id)
                elif choice == 2:  # Karpenter
                    success = installer.install(args.cluster_name, args.region, args.cluster_endpoint)
                    # Generate NodePool YAML after successful installation
                    if success:
                        installer.generate_nodepool_yaml(args.cluster_name)
                elif choice == 3:  # Kyverno
                    success = installer.install()
                elif choice == 4:  # Calico
                    success = installer.install()
                elif choice == 5:  # Nvidia Device Plugin
                    success = installer.install(enable_time_slicing=args.enable_time_slicing)
                else:  # Others
                    success = installer.install()

                if success:
                    logger.info(f"{name} installed successfully.")

                    # Validate installation
                    if hasattr(installer, 'validate_installation'):
                        logger.info(f"Validating {name} installation...")
                        if installer.validate_installation():
                            logger.info(f"{name} validation passed.")
                        else:
                            logger.warning(f"{name} validation failed or incomplete.")
                else:
                    logger.error(f"Failed to install {name}.")
                    return False

            except Exception as e:
                logger.error(f"Error installing {name}: {str(e)}")
                return False

    return True

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="EKS Addon Installer")
    parser.add_argument("--cluster-name", required=True, help="EKS cluster name")
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    parser.add_argument("--account-id", help="AWS account ID (optional, will be auto-detected if not provided)")
    parser.add_argument("--cluster-endpoint", help="EKS cluster endpoint (required for Karpenter)")
    parser.add_argument("--enable-time-slicing", action="store_true",
                        help="Enable time slicing for Nvidia plugin")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Set up logger
    log_level = logging.DEBUG if args.debug else logging.INFO
    logger = setup_logger("eks_addon_installer", log_level)

    # Check environment
    if not check_environment(logger):
        sys.exit(1)

    # Main loop
    while True:
        display_menu()
        selected_addons = get_user_selection()

        if not selected_addons:
            logger.info("Exiting...")
            break

        # Install selected addons
        if install_addons(selected_addons, args, logger):
            logger.info("All selected addons installed successfully!")
        else:
            logger.error("Some addons failed to install.")

        # Ask if user wants to continue
        cont = input("\nDo you want to install more addons? (y/n): ").strip().lower()
        if cont != 'y':
            break

    logger.info("EKS Addon Installer finished.")

if __name__ == "__main__":
    main()
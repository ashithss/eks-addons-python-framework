# EKS Addon Installer

A Python-based framework for managing addon installation for AWS EKS clusters.

## Features

- Modular structure with separate installer modules for each addon
- Menu-driven CLI interface
- Supports installation of popular EKS addons:
  - AWS Load Balancer Controller
  - NVIDIA k8s-device-plugin
  - Karpenter
  - Kyverno
  - Calico Network Policy
- Automatic generation of Karpenter NodePool configuration
- Validation of installations
- Extensible for future addons

## Prerequisites

- Python 3.x
- kubectl configured for your EKS cluster
- Helm 3.x
- AWS CLI configured with appropriate permissions
- eksctl for IAM service account creation

## Installation

1. Clone this repository
2. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the main script with required parameters:

```bash
python main.py --cluster-name YOUR_CLUSTER_NAME --region YOUR_REGION
```

Additional options:
- `--cluster-endpoint`: EKS cluster endpoint (required for Karpenter)
- `--enable-time-slicing`: Enable time slicing for Nvidia plugin
- `--debug`: Enable debug logging

The script will present a menu allowing you to select which addons to install.

## Addons

### 1. AWS Load Balancer Controller
Installs the AWS Load Balancer Controller via Helm with proper IAM service account configuration.

### 2. NVIDIA k8s-device-plugin
Installs the NVIDIA GPU operator with optional time-slicing configuration.

### 3. Karpenter
Installs Karpenter for node provisioning with automatic NodePool configuration generation.

### 4. Kyverno
Installs the Kyverno policy engine for Kubernetes policy management.

### 5. Calico Network Policy
Installs Calico in policy-only mode alongside existing AWS VPC CNI.

## Project Structure

```
eks-addon-installer/
├── main.py                 # Main CLI entry point
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── addons/                 # Addon installer modules
│   ├── __init__.py
│   ├── aws_lb_controller.py
│   ├── nvidia_plugin.py
│   ├── karpenter.py
│   ├── kyverno.py
│   └── calico.py
├── utils/                  # Utility modules
│   ├── helm.py
│   ├── kubectl.py
│   └── logger.py
├── templates/              # Jinja2 templates
│   └── karpenter_nodepool.yaml.j2
├── output/                 # Generated output files
│   └── nodepool.yaml       # Generated Karpenter NodePool config
└── config/
    └── settings.yaml       # Configuration file
```

## Extending for New Addons

To add a new addon:

1. Create a new installer module in the `addons/` directory
2. Implement the required methods (`install()`, `validate_installation()`)
3. Add the addon to the menu in `main.py`
4. Import the module in `main.py`

## License

This project is licensed under the MIT License.
#!/usr/bin/env python3
"""
Test script to validate the EKS Addon Installer framework
"""

import os
import sys
import ast

def test_project_structure():
    """Test that all required files and directories exist."""
    required_paths = [
        "main.py",
        "addons/__init__.py",
        "addons/aws_lb_controller.py",
        "addons/nvidia_plugin.py",
        "addons/karpenter.py",
        "addons/kyverno.py",
        "addons/calico.py",
        "utils/__init__.py",
        "utils/helm.py",
        "utils/kubectl.py",
        "utils/logger.py",
        "templates/karpenter_nodepool.yaml.j2",
        "config/settings.yaml",
        "requirements.txt",
        "README.md"
    ]

    print("Testing project structure...")
    missing_paths = []

    for path in required_paths:
        if not os.path.exists(path):
            missing_paths.append(path)

    if missing_paths:
        print(f"❌ Missing paths: {missing_paths}")
        return False
    else:
        print("✅ All required files and directories exist")
        return True

def test_imports():
    """Test that all modules can be imported."""
    print("\nTesting imports...")

    try:
        # Add current directory to Python path
        sys.path.insert(0, '.')

        # Test utility imports
        from utils.logger import setup_logger
        from utils.helm import check_helm_installed
        from utils.kubectl import check_cluster_connection

        # Test addon imports
        from addons.aws_lb_controller import AWSLoadBalancerControllerInstaller
        from addons.nvidia_plugin import NvidiaDevicePluginInstaller
        from addons.karpenter import KarpenterInstaller
        from addons.kyverno import KyvernoInstaller
        from addons.calico import CalicoInstaller

        print("✅ All modules imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_python_syntax():
    """Test that all Python files have valid syntax."""
    print("\nTesting Python syntax...")

    python_files = [
        "main.py",
        "addons/__init__.py",
        "addons/aws_lb_controller.py",
        "addons/nvidia_plugin.py",
        "addons/karpenter.py",
        "addons/kyverno.py",
        "addons/calico.py",
        "utils/__init__.py",
        "utils/helm.py",
        "utils/kubectl.py",
        "utils/logger.py"
    ]

    for file_path in python_files:
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                ast.parse(content)
        except SyntaxError as e:
            print(f"❌ Syntax error in {file_path}: {e}")
            return False
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
            return False

    print("✅ All Python files have valid syntax")
    return True

def main():
    """Run all tests."""
    print("Running EKS Addon Installer framework tests...\n")

    tests = [
        test_project_structure,
        test_imports,
        test_python_syntax
    ]

    all_passed = True
    for test in tests:
        if not test():
            all_passed = False

    print("\n" + "="*50)
    if all_passed:
        print("🎉 All tests passed! Framework is ready to use.")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
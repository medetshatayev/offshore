#!/usr/bin/env python3
"""
Setup verification script for offshore risk detection system.
Checks all dependencies and configuration.
"""
import sys
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_python_version():
    """Check Python version."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 12):
        print("❌ Python 3.12+ required")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True

def check_dependencies():
    """Check if all dependencies are installed."""
    required = [
        'fastapi', 'uvicorn', 'pandas', 'openpyxl', 'xlsxwriter',
        'pydantic', 'openai', 'Levenshtein', 'tenacity', 'dotenv'
    ]
    
    missing = []
    for pkg in required:
        try:
            if pkg == 'dotenv':
                __import__('dotenv')
            else:
                __import__(pkg)
            print(f"✅ {pkg}")
        except ImportError:
            print(f"❌ {pkg} - NOT INSTALLED")
            missing.append(pkg)
    
    return len(missing) == 0

def check_env_file():
    """Check if .env file exists and has required variables."""
    env_file = project_root / ".env"
    
    if not env_file.exists():
        print("❌ .env file not found")
        print("   Run: cp .env.example .env")
        return False
    
    print("✅ .env file exists")
    
    # Check for OPENAI_API_KEY
    with open(env_file) as f:
        content = f.read()
        if 'OPENAI_API_KEY' in content and 'your-openai-api-key-here' not in content:
            print("✅ OPENAI_API_KEY configured")
            return True
        else:
            print("⚠️  OPENAI_API_KEY not configured")
            print("   Edit .env and add your OpenAI API key")
            return False

def check_data_files():
    """Check if data files exist."""
    data_file = project_root / "data" / "offshore_countries.md"
    
    if not data_file.exists():
        print("❌ offshore_countries.md not found")
        return False
    
    print("✅ offshore_countries.md exists")
    return True

def check_project_structure():
    """Check if project structure is correct."""
    required_dirs = ['app', 'core', 'llm', 'data', 'templates']
    
    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        if not dir_path.exists():
            print(f"❌ {dir_name}/ directory missing")
            return False
        print(f"✅ {dir_name}/ directory")
    
    return True

def main():
    """Run all checks."""
    print("🔍 Verifying Offshore Risk Detection System Setup...\n")
    
    checks = [
        ("Python Version", check_python_version),
        ("Project Structure", check_project_structure),
        ("Dependencies", check_dependencies),
        ("Data Files", check_data_files),
        ("Environment", check_env_file)
    ]
    
    results = []
    
    for name, check_func in checks:
        print(f"\n📋 Checking {name}:")
        results.append(check_func())
    
    print("\n" + "="*50)
    
    if all(results):
        print("✅ All checks passed! System is ready.")
        print("\nTo start the server:")
        print("  python main.py")
        print("\nThen open: http://localhost:8000")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

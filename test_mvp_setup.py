"""
Test script to verify MVP setup
Run this before starting the API to check dependencies
"""

import os
from pathlib import Path


def check_import(module_name, package_name=None):
    """Check if a module can be imported"""
    if package_name is None:
        package_name = module_name

    try:
        __import__(module_name)
        print(f"[OK] {package_name} is installed")
        return True
    except ImportError:
        print(f"[MISSING] {package_name} is NOT installed - run: pip install {package_name}")
        return False


def check_env_file():
    """Check if .env file exists and has required keys"""
    env_path = Path(".env")
    env_example_path = Path(".env.example")

    if not env_path.exists():
        print("[MISSING] .env file not found")
        if env_example_path.exists():
            print("   Copy .env.example to .env and add your API keys")
        return False

    print("[OK] .env file exists")

    # Check for required keys
    from dotenv import load_dotenv

    load_dotenv()

    has_all = True

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key or openai_key == "sk-your-openai-api-key-here":
        print("[WARNING] OPENAI_API_KEY not set (OpenAI features won't work)")
        has_all = False
    else:
        print("[OK] OPENAI_API_KEY is configured")

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key or anthropic_key == "sk-ant-your-anthropic-api-key-here":
        print("[WARNING] ANTHROPIC_API_KEY not set (Claude features won't work)")
        has_all = False
    else:
        print("[OK] ANTHROPIC_API_KEY is configured")

    return has_all


def check_files():
    """Check if required files exist"""
    required_files = ["simple_api.py", "simple_ui.html", "requirements_mvp.txt"]

    all_exist = True
    for file in required_files:
        if Path(file).exists():
            print(f"[OK] {file} exists")
        else:
            print(f"[MISSING] {file} NOT found")
            all_exist = False

    return all_exist


def main():
    print("=" * 50)
    print("Relay MVP Setup Checker")
    print("=" * 50)

    print("\n>> Checking Python packages...")
    packages_ok = all(
        [
            check_import("fastapi"),
            check_import("uvicorn"),
            check_import("pydantic"),
            check_import("openai"),
            check_import("anthropic"),
            check_import("dotenv", "python-dotenv"),
        ]
    )

    print("\n>> Checking required files...")
    files_ok = check_files()

    print("\n>> Checking environment configuration...")
    env_ok = check_env_file()

    print("\n" + "=" * 50)

    if packages_ok and files_ok:
        print("[SUCCESS] All requirements met!")
        print("\nNext steps:")
        if not env_ok:
            print("1. Add your API keys to .env file")
            print("2. Run: python simple_api.py")
            print("3. Open simple_ui.html in your browser")
        else:
            print("1. Run: python simple_api.py")
            print("2. Open simple_ui.html in your browser")
    else:
        print("[ERROR] Setup incomplete")
        print("\nFix the issues above, then run this test again")
        if not packages_ok:
            print("\nQuick fix: pip install -r requirements_mvp.txt")

    print("=" * 50)


if __name__ == "__main__":
    main()

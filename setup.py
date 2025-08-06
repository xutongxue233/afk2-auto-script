"""
剑与远征启程自动化脚本安装配置
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取README文件
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding='utf-8')

# 读取依赖
requirements = (this_directory / "requirements.txt").read_text(encoding='utf-8').splitlines()
requirements = [r.strip() for r in requirements if r.strip() and not r.startswith('#')]

setup(
    name="afk2-auto-script",
    version="0.1.0",
    author="AFK2 Auto Team",
    description="剑与远征启程自动化脚本",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/afk2-auto-script",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "afk2-auto=src.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "src": [
            "resources/templates/*",
            "resources/configs/*",
        ],
    },
)
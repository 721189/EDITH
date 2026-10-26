from setuptools import setup, find_packages

setup(
    name="wind-forecast-dashboard",
    version="1.0.0",
    description="Wind Forecast Intelligence API - Historical wind forecast accuracy analysis",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.100.0",
        "uvicorn[standard]>=0.27.0",
        "httpx>=0.25.0",
        "pydantic>=2.5.0",
    ],
    entry_points={
        "console_scripts": [
            "wind-forecast-dashboard=src.app:main",
        ],
    },
)
from setuptools import setup, find_packages

setup(
    name="cedarfix_shared",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0",
        "sqlalchemy>=2.0",
        "psycopg2-binary",
        "prometheus-client",
    ],
)

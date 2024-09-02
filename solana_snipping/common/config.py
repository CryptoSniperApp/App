import os
from envyaml.envyaml import EnvYAML


def get_config():
    return EnvYAML(
        "config.yml",
        ".env",
        include_environment=False,
        flatten=False,
        strict=False,
        **dict(os.environ),
    ).export()

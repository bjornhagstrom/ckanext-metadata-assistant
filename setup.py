import re
from pathlib import Path

from setuptools import find_namespace_packages, setup


HERE = Path(__file__).parent
REPOSITORY = "https://github.com/bjornhagstrom/ckanext-metadata-assistant/blob/main/"


def long_description():
    """The README for PyPI, with links that work outside the repository."""
    text = (HERE / "README.md").read_text(encoding="utf-8")
    return re.sub(r"\]\((?!https?://|#|mailto:)([^)]+)\)", lambda m: "](" + REPOSITORY + m.group(1) + ")", text)


setup(
    name="ckanext-metadata-assistant",
    version="0.1.0",
    description=(
        "Metadata review in the CKAN dataset form: a rule check, and AI suggestions and translations that an "
        "editor approves"
    ),
    long_description=long_description(),
    long_description_content_type="text/markdown",
    author="Bjorn Hagstrom",
    author_email="bjorn@hagstrom.nu",
    url="https://github.com/bjornhagstrom/ckanext-metadata-assistant",
    project_urls={
        "Source": "https://github.com/bjornhagstrom/ckanext-metadata-assistant",
        "Changelog": "https://github.com/bjornhagstrom/ckanext-metadata-assistant/blob/main/CHANGELOG.md",
        "Issues": "https://github.com/bjornhagstrom/ckanext-metadata-assistant/issues",
    },
    packages=find_namespace_packages(include=["ckanext", "ckanext.*"]),
    # The legacy declaration of the ckanext namespace, as CKAN and most extensions have it: the wheel then installs a
    # -nspkg.pth file that adds this package's directory to ckanext's path. Without it, a CKAN whose ckanext/__init__.py uses
    # pkg_resources.declare_namespace (setuptools before 81) does not see the package unless another extension declares it.
    namespace_packages=["ckanext"],
    include_package_data=True,
    # The AI connection (model, key, the call itself) is ckanext-ai-connector's, shared with other extensions. Its API may
    # still change in 0.x, so the pin stays within 0.1 until it is frozen at 1.0; ai.MIN_API says which API version this needs.
    install_requires=["pydantic>=2,<3", "ckanext-ai-connector>=0.1.0,<0.2"],
    # Kept so that `pip install ckanext-metadata-assistant[ai]` (older instructions) still works; ckanext-ai-connector brings
    # the libraries itself now.
    extras_require={"ai": []},
    license="MIT",
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
    entry_points={
        "ckan.plugins": [
            "metadata_assistant=ckanext.metadata_assistant.plugin:MetadataAssistantPlugin",
        ],
    },
)

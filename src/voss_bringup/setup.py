import os
from glob import glob

from setuptools import find_packages, setup

package_name = "voss_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    extras_require={"test": ["pytest"]},
    zip_safe=True,
    maintainer="김학민",
    maintainer_email="team@example.com",
    description="launch·설정·브링업",
    license="MIT",
    entry_points={
        "console_scripts": [],
    },
)

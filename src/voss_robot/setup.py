import os
from glob import glob

from setuptools import find_packages, setup

package_name = "voss_robot"

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
    description="두산 단일 호출 큐·RG2·구역 이동",
    license="MIT",
    entry_points={
        "console_scripts": [
            "robot_gateway = voss_robot.robot_gateway:main",
        ],
    },
)

import os
from glob import glob

from setuptools import find_packages, setup

package_name = "voss_hmi"

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
    maintainer="정의석",
    maintainer_email="team@example.com",
    description="MQTT 브리지·작업 로그",
    license="MIT",
    entry_points={
        "console_scripts": [
            "hmi_bridge = voss_hmi.hmi_bridge:main",
            "sort_logger = voss_hmi.sort_logger:main",
        ],
    },
)

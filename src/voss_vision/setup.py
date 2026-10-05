import os
from glob import glob

from setuptools import find_packages, setup

package_name = "voss_vision"

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
    maintainer="남현지",
    maintainer_email="team@example.com",
    description="박스 검출·추적, 송장 OCR",
    license="MIT",
    entry_points={
        "console_scripts": [
            "box_tracker = voss_vision.box_tracker:main",
            "label_reader = voss_vision.label_reader:main",
        ],
    },
)

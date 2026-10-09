import os
from glob import glob

from setuptools import find_packages, setup

package_name = "voss_servo"

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
    maintainer="박병후",
    maintainer_email="team@example.com",
    description="컨베이어 추종·파지 서보",
    license="MIT",
    entry_points={
        "console_scripts": [
            "belt_servo = voss_servo.belt_servo:main",
            "fake_box = voss_servo.fake_box:main",  # sim 전용 (U3)
            "sim_check = voss_servo.sim_check:main",  # sim 전용 (U3)
        ],
    },
)

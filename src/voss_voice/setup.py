import os
from glob import glob

from setuptools import find_packages, setup

package_name = "voss_voice"

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
    description="호출어·Whisper STT·intent·TTS",
    license="MIT",
    entry_points={
        "console_scripts": [
            "voice_listener = voss_voice.voice_listener:main",
            "intent_parser = voss_voice.intent_parser:main",
            "speech_out = voss_voice.speech_out:main",
        ],
    },
)

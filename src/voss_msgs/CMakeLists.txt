cmake_minimum_required(VERSION 3.8)
project(voss_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Intent.msg"
  "msg/SortState.msg"
  "msg/SortResult.msg"
  "msg/ZoneMapEntry.msg"
  "msg/ZoneMap.msg"
  "msg/BoxTrack.msg"
  "msg/LabelRead.msg"
  "msg/LabelCrop.msg"
  "srv/Command.srv"
  "srv/UpdateZoneMap.srv"
  "srv/MoveToZone.srv"
  "srv/Gripper.srv"
  "srv/TeachZone.srv"
  "srv/ReadLabel.srv"
  "action/TrackAndGrasp.action"
  DEPENDENCIES builtin_interfaces std_msgs sensor_msgs geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()

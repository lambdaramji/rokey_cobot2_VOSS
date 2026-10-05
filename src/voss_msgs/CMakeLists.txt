cmake_minimum_required(VERSION 3.8)
project(voss_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Intent.msg"
  "msg/SortState.msg"
  "msg/SortResult.msg"
  "msg/ZoneMapEntry.msg"
  "msg/ZoneMap.msg"
  "msg/BoxTrack.msg"
  "msg/LabelRead.msg"
  "srv/Command.srv"
  "srv/UpdateZoneMap.srv"
  "srv/Stats.srv"
  "srv/MoveToZone.srv"
  "srv/Gripper.srv"
  "srv/TeachZone.srv"
  "action/TrackAndGrasp.action"
  DEPENDENCIES builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()

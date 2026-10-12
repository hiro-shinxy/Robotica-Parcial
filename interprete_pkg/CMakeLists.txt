cmake_minimum_required(VERSION 3.8)
project(interprete_pkg)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/InterpretarOrden.srv"
)

install(PROGRAMS
  scripts/interprete_ordenes.py
  scripts/medidor_evaluacion.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY datos informes
  DESTINATION share/${PROJECT_NAME}
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()

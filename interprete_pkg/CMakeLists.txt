cmake_minimum_required(VERSION 3.8)
project(interprete_pkg)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

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

ament_package()

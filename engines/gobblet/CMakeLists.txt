cmake_minimum_required(VERSION 3.20)
project(gobblet_native LANGUAGES CXX)

add_executable(gobblet-native main.cpp)
target_compile_features(gobblet-native PRIVATE cxx_std_20)

if(MSVC)
  target_compile_options(gobblet-native PRIVATE /O2 /GL /W4 /EHsc)
  target_link_options(gobblet-native PRIVATE /LTCG)
else()
  target_compile_options(gobblet-native PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()

cmake_minimum_required(VERSION 3.10)
project(RuntimeStatCollectPass)

# 1. Find the installed LLVM
# If not found, specify with -DLLVM_DIR=/path/to/llvm/lib/cmake/llvm
find_package(LLVM REQUIRED CONFIG)
MESSAGE(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
MESSAGE(STATUS "Using LLVMConfig.cmake in: ${LLVM_CMAKE_DIR}")

# 2. Import LLVM marco and functions
list(APPEND CMAKE_MODULE_PATH "${LLVM_CMAKE_DIR}")
include(AddLLVM)

add_definitions(${LLVM_DEFINITIONS})
include_directories(${LLVM_INCLUDE_DIRS})

# add -fexceptions
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fexceptions")

add_llvm_pass_plugin(RuntimeStatCollectPass RuntimeStatCollect.cpp)

target_compile_options(RuntimeStatCollectPass PRIVATE -fexceptions)

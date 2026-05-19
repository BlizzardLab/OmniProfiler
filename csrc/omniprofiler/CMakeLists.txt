cmake_minimum_required(VERSION 3.10)
project(omniprofiler LANGUAGES C CXX)

find_package(Threads REQUIRED)

add_library(runtime_hook SHARED omniprofiler.cpp)
target_link_libraries(runtime_hook PRIVATE Threads::Threads)
target_compile_definitions(runtime_hook PRIVATE
	RUNTIME_HOOK_ENABLE=1
	NUM_RINGBUFFER=16
	RINGBUFFER_SLOTS=32768
)
target_compile_options(runtime_hook PRIVATE -O2)

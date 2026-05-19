# OmniProfiler

This repository is the artifact of paper *Diagnosing Performance Issues in Application-Defined Resources* (OSDI'26). This artifact includes an implementation of *Finding Application Usage Events* (Section 3.3) and *Validation of Resource Usage Events* (Section 3.4), instrumentation and runtime library in *Dynamic Profiling Phase* (Section 3.5).

## Repo Structure

```
./
 |-entrypoints		(Python scripts to launch different parts of OmniProfiler, and some utilities)
 |-agentic_analyzer	(Preprocessing documents of target systems and feeding data to LLMs)
 |-csrc				(Source code related to validation, instrumentation, and runtime library)
 |  |-omniprofiler	(Runtime library)
 |  |-ResourceAnalysis		(Validation)
 |  |-RuntimeStatCollect	(Instrumentation)
 |--gui-dynamic-profiling	(Web GUI implementation for dyanmic analysis)

```

## How to run OmniProfiler

### 1. Prepare Target System (e.g., MySQL-8.3.0)
`wget https://downloads.mysql.com/archives/get/p/23/file/mysql-boost-8.3.0.tar.gz && tar -zxvf mysql-boost-8.3.0.tar.gz && cd mysql-8.3.0`

### 2. Using Doxygen to generate documents (in .xml)
This part relates to *Finding Application Usage Events* (Section 3.3) in the paper.

Before proceeding to the next step, please follow guidance in [MySQL-8.0-Doxygen](https://dev.mysql.com/doc/mysql-installation-excerpt/8.0/en/source-installation-doxygen.html) to set up Doxygen.


Configure Doxygen through `vim./Doxygen.in`, setting `GENERATE_XML = YES`. Then:
```Bash
mkdir build && cd build
cmake .. && make doxygen
# NOTE: default doxygen output would be in ./doxygen/xml
```
Building the documents might take minutes, so please wait with patience.

### 3. Configure OmniProfiler and run `document tokenizer` 
This part relates to *Finding Application Usage Events* (Section 3.3) in the paper.

Before proceeding, please install all dependencies in `agentic_analyzer/environment.yml` or `agentic_analyzer/requirements.txt`

As demonstration, we provide a ready-to-use configuration file for MySQL-8.3.0 in `agentic_analyzer/configs/global_config.yaml`. So, we can directly run document tokenizer through `python entrypoionts/doc_tokenizer.py`, otherwise modifying `global_config_template.yaml` accordingly.

### 4. Configure OmniProfiler and run `type analyzer`
This part relates to *Finding Application Usage Events* (Section 3.3) in the paper.

Before proceeding, please configure all LLM provider information in `agentic_analyzer/configs/global_config.yaml`. Then, run type analyzer thorugh `python entrypoionts/type_analyzer.py`.

### 5. Build LLVM Passes and OmniProfiler's runtime library
This part relates to *Dynamic Profiling Phase* (Section 3.5) in the paper.

Note: LLVM out-of-tree passes are developed with LLVM-17. Use package manager to install llvm-17 before building LLVM passes.

```Bash
# Starting from project root
cd csrc/omniprofiler && mkdir build && cd build && cmake .. && make
# Starting from project root
cd csrc/ResourceAnalysis && mkdir build && cd build && cmake .. && make
# Starting from project root
cd csrc/RuntimeStatCollect && mkdir build && cd build && cmake .. && make
```

### 6. Validation
This part relates to *Validation of Resource Usage Events* (Section 3.4) in the paper.

```Bash
set -e

### Validation ###

export TYPE_ANALYSIS_DATA=path/to/llm_analysis_result.json  # path to the output of type_analyzer
export ENABLE_RESOURCE_ANALYSIS=1
export VALIDATION_OUTPUT_DIR=validation-outs				# a directory containing each module's results
export VALIDATION_PASS_SO=csrc/ResourceAnalysis/build/ResourceAnalysisPass.so 
rm -rf $VALIDATION_OUTPUT_DIR
mkdir -p $VALIDATION_OUTPUT_DIR

mkdir -p build

cd build

cmake .. \
  -DCMAKE_BUILD_TYPE=Debug \
  -DFORCE_INSOURCE_BUILD=1 \
  -DCMAKE_VERBOSE_MAKEFILE=ON \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_C_FLAGS="-Xclang -fpass-plugin=$VALIDATION_PASS_SO" \
  -DCMAKE_CXX_FLAGS="-Xclang -fpass-plugin=$VALIDATION_PASS_SO" \
  -DDEFAULT_CHARSET=utf8 \
  -DDEFAULT_COLLATION=utf8_general_ci \
  -DWITH_INNOBASE_STORAGE_ENGINE=1 \
  -DWITH_ARCHIVE_STORAGE_ENGINE=1 \
  -DWITH_BLACKHOLE_STORAGE_ENGINE=1 \
  -DMYSQL_TCP_PORT=3306 \
  -DWITH_SSL=system \
  -DWITH_SYSTEMD=1 \
  -DWITH_BOOST="./mysql-8.3.0/boost"

make -j
```

After building, `$VALIDATION_OUTPUT_DIR` contains multiple `.json` file. We run `python entrypoints/collect_results.py` to aggregate them:

```Bash
export VALIDATION_OUTPUT_DIR=validation-outs
export INSTRUMENTATION_DATA=instrumentation-data

python entrypoints/collect_results.py --sanity-check \
									  --input-dir $VALIDATION_OUTPUT_DIR \
									  --output-dir $INSTRUMENTATION_DATA 
```

### 7. Instrumentation and install
This part relates to *Dynamic Profiling Phase* (Section 3.5) in the paper.
```Bash
set -e

### Instrumentation ###
export INSTRUMENTATION_DATA=instrumentation-data

export INSTRUMENTATION_INDEX=$INSTRUMENTATION_DATA/aggregated_results.json
export INSTRUMENTATION_PASS_SO=csrc/RuntimeStatCollect/build/RuntimeStatCollectPass.so
export ENABLE_RESOURCE_TRACING=1
# Dynamic library for runtime tracing
export OMNIPROFILER_FOLDER=csrc/RuntimeStatCollect/gigiprofiler/build
export LD_LIBRARY_PATH=$OMNIPROFILER_FOLDER:$LD_LIBRARY_PATH

mkdir -p build

cd build

cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DFORCE_INSOURCE_BUILD=1 \
  -DCMAKE_VERBOSE_MAKEFILE=ON \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_C_FLAGS="-Xclang -fpass-plugin=$INSTRUMENTATION_PASS_SO" \
  -DCMAKE_CXX_FLAGS="-Xclang -fpass-plugin=$INSTRUMENTATION_PASS_SO" \
  -DCMAKE_C_STANDARD_LIBRARIES="-L$OMNIPROFILER_FOLDER -lruntime_hook" \
  -DCMAKE_CXX_STANDARD_LIBRARIES="-L$OMNIPROFILER_FOLDER -lruntime_hook" \
  -DDEFAULT_CHARSET=utf8 \
  -DDEFAULT_COLLATION=utf8_general_ci \
  -DWITH_INNOBASE_STORAGE_ENGINE=1 \
  -DWITH_ARCHIVE_STORAGE_ENGINE=1 \
  -DWITH_BLACKHOLE_STORAGE_ENGINE=1 \
  -DMYSQL_TCP_PORT=3306 \
  -DWITH_SSL=system \
  -DWITH_SYSTEMD=1 \
  -DWITH_BOOST="./mysql-8.3.0/boost"

make -j

make install
```

### 9. Run buggy cases (e.g., c3 MDL)
All data and outputs gathered are in `demo-case/MDL`

### 10. Dynamic Profiling
This part relates to *Dynamic Profiling Phase* (Section 3.5) in the paper.

All collected data are dumped to a directory and stored in `.json` format, records follow the same format. We can first load all data from different threads for analysis:

```json
{
"resource-index": [
        {
            "event": "ACCESS",
            "function_index": 11,
            "is_exit": false,
            "ptr": "0x7a3850cf159f",
            "ts_ns": "22128849819445"
        }
	]
}
```
**The latest implmentation is a Web GUI with Claude Code assisted, which aims to provide interactive and more straightforward way to present runtime time information:**
```Bash
python gui-dynamic-profiling/app.py 
```


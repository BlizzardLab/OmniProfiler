#ifndef RESOURCE_ANALYSIS_H_
#define RESOURCE_ANALYSIS_H_

#include "llvm/IR/PassManager.h"

namespace llvm {

class ResourceAnalysisModulePass: public PassInfoMixin<ResourceAnalysisModulePass> {
	bool is_enabled;
public:
	ResourceAnalysisModulePass();
	PreservedAnalyses run(Module &M, ModuleAnalysisManager &MAM);
};

} // end namespace llvm

#endif // RESOURCE_ANALYSIS_H_
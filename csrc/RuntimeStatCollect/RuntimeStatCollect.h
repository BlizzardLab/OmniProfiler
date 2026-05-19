#ifndef RESOURCE_ANALYSIS_H_
#define RESOURCE_ANALYSIS_H_

#include "llvm/IR/PassManager.h"

namespace llvm {

class RuntimeStatCollectPass: public PassInfoMixin<RuntimeStatCollectPass> {
	bool is_enabled;
public:
	RuntimeStatCollectPass();
	PreservedAnalyses run(Module &M, ModuleAnalysisManager &MAM);
};

} // end namespace llvm

#endif // RESOURCE_ANALYSIS_H_
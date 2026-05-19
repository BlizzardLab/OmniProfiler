#include <cstdint>
#include <cxxabi.h>
#include <fstream>
#include <iostream>
#include <cstring>
#include <string>
#include <vector>
#include <set>
#include <unordered_map>
#include <nlohmann/json.hpp>

#include "llvm/Pass.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/Type.h"
#include "llvm/IR/DerivedTypes.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/PatternMatch.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/SmallSet.h"
#include "llvm/Support/Casting.h"
#include "llvm/Analysis/LoopInfo.h"

#include "RuntimeStatCollect.h"

using namespace llvm;
using namespace llvm::PatternMatch;

// Other Enums
constexpr unsigned NONE = 1 << 30;
constexpr int RET = -1;

constexpr uint16_t EXIT_BIT = 1 << 15; // Use the highest bit to indicate entry (0) or exit (1)

// Operation Enums
using omni_event_t = uint16_t;
constexpr omni_event_t UNINITIALIZED = 1;
constexpr omni_event_t ACQUIRE = 1 << 1;
constexpr omni_event_t RELEASE = 1 << 2;
constexpr omni_event_t WAIT = 1 << 3;
constexpr omni_event_t USE = 1 << 4;
constexpr omni_event_t ACCESS = 1 << 5;
constexpr omni_event_t GET = 1 << 6;

constexpr omni_event_t DONE = 1 << 13;
constexpr omni_event_t INVALID = 1 << 14;
#define HAS_FLAG(value, flag) ((value & flag) != 0)

/// @brief Parse the operation type string into bitwise flags
/// @param type_string The operation type string (all in uppercase)
/// @return The bitwise flags representing the operation types
omni_event_t parse_operation_type(const ::std::string& type_string) {
	omni_event_t flags = 0;

	if (type_string.find("ACQUIRE") != ::std::string::npos) {
		flags |= ACQUIRE;
	}
	if (type_string.find("RELEASE") != ::std::string::npos) {
		flags |= RELEASE;
	}
	if (type_string.find("WAIT") != ::std::string::npos) {
		flags |= WAIT;
	}
	if (type_string.find("USE") != ::std::string::npos) {
		flags |= USE;
	}
	if (type_string.find("ACCESS") != ::std::string::npos) {
		flags |= ACCESS;
	}
	if (type_string.find("GET") != ::std::string::npos) {
		flags |= GET;
	}

	return flags;
}

/// @brief Print the operation type flags as a string
/// @param flags The bitwise flags representing the operation types
::std::string convert_operation_type_to_string(omni_event_t flags) {
	if (flags == UNINITIALIZED) {
		return "UNINITIALIZED";
	}

	::std::string result;
	bool first = true;
	if (HAS_FLAG(flags, ACQUIRE)) {
		if (!first) result += ", ";
		result += "ACQUIRE";
		first = false;
	}
	if (HAS_FLAG(flags, RELEASE)) {
		if (!first) result += ", ";
		result += "RELEASE";
		first = false;
	}
	if (HAS_FLAG(flags, WAIT)) {
		if (!first) result += ", ";
		result += "WAIT";
		first = false;
	}
	if (HAS_FLAG(flags, USE)) {
		if (!first) result += ", ";
		result += "USE";
		first = false;
	}
	if (HAS_FLAG(flags, ACCESS)) {
		if (!first) result += ", ";
		result += "ACCESS";
		first = false;
	}
	if (HAS_FLAG(flags, GET)) {
		if (!first) result += ", ";
		result += "GET";
		first = false;
	}
	if (HAS_FLAG(flags, DONE)) {
		if (!first) result += ", ";
		result += "DONE";
		first = false;
	}
	if (HAS_FLAG(flags, INVALID)) {
		if (!first) result += ", ";
		result += "INVALID";
		first = false;
	}
	return result;
}

struct EntryMetadata {
	// Beginning index in the function dicts
	size_t begin_index;

	// Number of functions in this entry
	size_t entry_size;

	//// For instrumentation 
	uint16_t function_index;

	// Number of parameters
	size_t num_params;
};

struct Item {
	// The position of the resource type in the function signature (e.g., arg0, arg1, ret, this)
	int position;

	// Bitwise flags representing the characteristics of this entry
	omni_event_t flags;

	// Resource index for instrumentation
	uint32_t resource_index;

	Item(int pos = NONE, omni_event_t fl = UNINITIALIZED, uint32_t res_idx = NONE): position(pos), flags(fl), resource_index(res_idx) {}
};

struct Entry {
	// Type name
	std::string name;

	// It can be multiple entries for the same function (e.g., acquire on arg0 and release on arg1)
	::std::vector<Item> item_list;
};

// Function Dicts
::std::unordered_map<::std::string, EntryMetadata> func_index;
::std::vector<Entry> func_entries;
::std::vector<::std::string> resource_name_list;  // index is the resource name for the resource with index i

/// JSON file structure:
/// {
///   "mangled_fn_name": {
///	  	"__metadata__": {
///	    	"num_params": 3,
///	  		"fn_name": "demangled_fn_name" [TODO]
///	   	},
///    	"ResourceTypeA": [
///		{
///	     	"position": 0,
///	     	"flags": "ACQUIRE,USE"
///	   	},
///		...
///    	]
///   },
///   ...
/// }

// For instrumentation
std::set<std::string> instrument_record;

/// @brief Parse the operation type string into bitwise flags
/// @param M The module to instrument
static llvm::FunctionCallee getOrInsertAddRecord(llvm::Module& M) {
    LLVMContext &C = M.getContext();
    Type *VoidTy = llvm::Type::getVoidTy(C);
    Type *PtrTy  = llvm::PointerType::get(C, 0);
    Type *I32    = llvm::Type::getInt32Ty(C);     // uint32_t

    FunctionType *FT = llvm::FunctionType::get(VoidTy, {PtrTy, I32, I32}, false);
    return M.getOrInsertFunction("add_record", FT);
}

/// @brief Synthesize the event record and call the "add_record" function
/// @param builder The IRBuilder to create instructions
/// @param P The pointer argument for the event record
/// @param info The synthesized info argument for the event record (e.g., event flags, function index, exit bit)
/// @param res_id The resource index for this event record
static void createAddRecordCall(llvm::IRBuilder<> &builder, FunctionCallee& AddRecord, llvm::Value *P,
								omni_event_t res_event_flags, uint16_t function_index, bool exit_bit, uint32_t res_id) {
	llvm::Value *event_flags = builder.getInt32(res_event_flags);
	llvm::Value *fn_index = builder.getInt16(function_index); // Shift function index to the left by 16 bits
	llvm::Value *set_exit_bit = builder.getInt16(exit_bit ? EXIT_BIT : 0);
	
	llvm::Value *fn_flags = builder.CreateZExt(builder.CreateOr(fn_index, set_exit_bit), builder.getInt32Ty()); // Combine function index with exit bit
	llvm::Value *shifted_fn_flags = builder.CreateShl(fn_flags, 16); // Shift left by 16 bits to make room for event flags
	llvm::Value *info = builder.CreateOr(event_flags, shifted_fn_flags); // Combine event flags with function index and exit bit

	builder.CreateCall(AddRecord, {P, info, builder.getInt32(res_id)});
}

/// @brief Instrument a function callee "add_record"
/// @param F The function to instrument
/// @param function_index The index of the function for this event record
/// @param position The position of the resource type in the function signature (e.g., arg0, arg1, ret(-1))
/// @param flags Bitwise flags representing the characteristics of this entry
/// @param resource_index The index of the resource type for this function
void InsertEventDispatch(Function *F, uint16_t function_index, int position, omni_event_t flags, uint32_t resource_index) {
	llvm::Module& M = *F->getParent();
	LLVMContext &C = M.getContext();
	FunctionCallee AddRecord = getOrInsertAddRecord(M);
	errs() << "Instrumenting function: " << F->getName() << ", position: " << position << ", flags: " << convert_operation_type_to_string(flags) << "\n";

	if (position == RET) {
		if (!HAS_FLAG(flags, ACQUIRE))
			return;  // Currently we only support acquire on return value

		// Special handling for acquire on return value: instrument before each return instruction
		for (auto &BB : *F) {
			// NOTE: There may be multiple return instructions
			if (auto *RI = dyn_cast<ReturnInst>(BB.getTerminator())) {
				IRBuilder<> builder(RI); // insertion point is *before* RI

				llvm::Value *RetV = RI->getReturnValue(); // may be null for ret void
				if (RetV && RetV->getType()->isPointerTy()) {
					llvm::Value *P = RetV; // void*
					createAddRecordCall(builder, AddRecord, P, ACQUIRE, function_index, true, resource_index);
				} else {
					errs() << "Warning: Return value is not a pointer or is void in function " << F->getName() << ". Skipping instrumentation for this return instruction.\n";
				}
			}
		}
	} else {
		// Instrument at the beginning of the function and use the argument as the pointer
		llvm::Instruction *IP = F->getEntryBlock().getFirstNonPHIOrDbgOrLifetime();
		if (!IP) IP = &*F->getEntryBlock().begin();
		llvm::IRBuilder<> builder(IP);

		llvm::Argument *A = F->getArg(static_cast<unsigned>(position));
		if (A->getType()->isPointerTy()) {
    		llvm::Value *P = A;
			createAddRecordCall(builder, AddRecord, P, flags, function_index, false, resource_index);

			if (HAS_FLAG(flags, WAIT)) {
				// We need to record the function time for WAIT events
				// So we also add an exit record at the end of the function

				for (auto &BB : *F) {
					// NOTE: There may be multiple return instructions
					if (auto *RI = dyn_cast<ReturnInst>(BB.getTerminator())) {
						IRBuilder<> exit_builder(RI); // insertion point is *before* RI
						createAddRecordCall(exit_builder, AddRecord, P, flags, function_index, true, resource_index);
					}
				}
			}

  		} else {
			errs() << "Warning: Argument " << position << " is not a pointer in function " << F->getName() << ". Skipping instrumentation for this argument.\n";
		}
	}
}

RuntimeStatCollectPass::RuntimeStatCollectPass(): is_enabled(false)
{
	const char *is_enabled_str = std::getenv("ENABLE_RESOURCE_TRACING");
	if (is_enabled_str && std::strcmp(is_enabled_str, "1") == 0) {
		is_enabled = true;
	} else return;

	const char *sa_data_path = std::getenv("INSTRUMENTATION_INDEX");
    if (!sa_data_path) {
        errs() << "no INSTRUMENTATION_INDEX\n";
        return;
    }

    std::ifstream sa_data_file(sa_data_path);
    if (!sa_data_file.is_open()) {
        errs() << "Failed to open file: " << sa_data_path << "\n";
        return;
    }

	nlohmann::json  resource_json;
    sa_data_file >> resource_json;
	sa_data_file.close();

	size_t current_index = 0;
	for (auto const& [mangled_fn_name, op_dict] : resource_json.items()) {
		if (!op_dict.is_object())
			continue;
        
		EntryMetadata metadata;
		metadata.begin_index = current_index;
		metadata.entry_size = op_dict.size() - 1; // Exclude __metadata__
		metadata.num_params = op_dict["__metadata__"]["num_params"];
		metadata.function_index = static_cast<uint16_t>(op_dict["__metadata__"]["function_index"]);
		func_index[mangled_fn_name] = metadata;

		// Debug
		// errs() << "Loaded metadata for function: " << mangled_fn_name << ", num_params: " << metadata.num_params << "\n";

		for (auto const& [resource_name, position_list] : op_dict.items()) {
			if (resource_name == "__metadata__")
				continue; // Skip metadata entry

			// Parse the position list for this resource type
			::std::vector<Item> item_list;
			for (const auto& item : position_list) {
				int position = item["position"];
				omni_event_t flags = parse_operation_type(item["flags"]);
				uint32_t resource_index = static_cast<uint32_t>(item["resource_index"]);
				item_list.push_back(Item(position, flags, resource_index));
				// errs() << "  Resource: " << resource_name << ", position: " << position << ", flags: " << convert_operation_type_to_string(flags) << "\n";
			}

			Entry entry;
			entry.name = resource_name;
			entry.item_list = item_list;
			func_entries.push_back(entry);
			++current_index;
		}
    }
}

PreservedAnalyses RuntimeStatCollectPass::run(Module &M, ModuleAnalysisManager &MAM) {
	if (!is_enabled) 
		return PreservedAnalyses::all();

	if (M.getNamedMetadata("instrumented"))
        return PreservedAnalyses::none();

	bool been_triggered = false;
	for (Function &F : M) {
		if (F.isDeclaration() || F.isIntrinsic())
			continue;

		// Demangle function name
		std::string mangled_fn_name = F.getName().str();

		auto search = func_index.find(mangled_fn_name);

		// If function does not request an analysis
		if (search == func_index.end())
			continue;

		// If function is already instrumented, skip
		if (instrument_record.find(mangled_fn_name) != instrument_record.end())
			continue;

		instrument_record.insert(mangled_fn_name);

		been_triggered = true;

		// TODO: instrumentation
		// Check metadata to see if num_arg matches
		EntryMetadata& metadata = search->second;
		if (metadata.num_params != F.arg_size()) {
			errs() << "Warning: Number of parameters in function " << F.getName() << " does not match the metadata. Skipping instrumentation for this function.\n";
			continue;
		}

		// Iterate over associated entries
		for (size_t i = 0; i < metadata.entry_size; ++i) {
			Entry &entry = func_entries[metadata.begin_index + i];
			for (const auto& item : entry.item_list) InsertEventDispatch(&F, metadata.function_index, item.position, item.flags, item.resource_index);
		}
	}

	if (been_triggered)
		NamedMDNode *InstrumentedMD = M.getOrInsertNamedMetadata("instrumented");

    return been_triggered ? PreservedAnalyses::none(): PreservedAnalyses::all();
}

 
extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo
llvmGetPassPluginInfo() {
    return {
        LLVM_PLUGIN_API_VERSION, "RuntimeStatCollectPass", LLVM_VERSION_STRING,
        [](PassBuilder &PB) {
            // Run this pass as early as possible to avoid inline and other transformations that may change the function signatures
            PB.registerPipelineStartEPCallback(
                [](ModulePassManager &MPM, OptimizationLevel Level) {
                    MPM.addPass(RuntimeStatCollectPass());
                });
        }
    };
}

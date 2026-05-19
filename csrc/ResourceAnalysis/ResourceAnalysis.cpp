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
#include "llvm/IR/Function.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/PatternMatch.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Transforms/Scalar/SROA.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/SmallSet.h"
#include "llvm/Support/Casting.h"
#include "llvm/Analysis/LoopInfo.h"
#include "llvm/IR/DebugInfoMetadata.h"
#include "llvm/IR/DebugProgramInstruction.h"
#include "llvm/BinaryFormat/Dwarf.h"

#include "ResourceAnalysis.h"

using namespace llvm;
using namespace llvm::PatternMatch;

// Other Enums
constexpr unsigned NONE = 1 << 30;
constexpr unsigned RET = 1 << 31;

// Operation Enums
constexpr uint32_t UNINITIALIZED = 1;
constexpr uint32_t ACQUIRE = 1 << 1;
constexpr uint32_t RELEASE = 1 << 2;
constexpr uint32_t WAIT = 1 << 3;
constexpr uint32_t USE = 1 << 4;
constexpr uint32_t ACCESS = 1 << 5;
constexpr uint32_t GET = 1 << 6;

constexpr uint32_t DONE = 1 << 13;
constexpr uint32_t INVALID = 1 << 14;
#define HAS_FLAG(value, flag) ((value & flag) != 0)

/// @brief Parse the operation type string into bitwise flags
/// @param type_string The operation type string (all in uppercase)
/// @return The bitwise flags representing the operation types
uint32_t parse_operation_type(const ::std::string& type_string) {
	uint32_t flags = UNINITIALIZED;

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
::std::string convert_operation_type_to_string(uint32_t flags) {
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

	// Mangled function name
	std::string mangled_name;
	std:: string demangled_name;

	// Number of parameters
	size_t num_params;
};

struct Item {
	// The position of the resource type in the function signature (e.g., arg0, arg1, ret, this)
	unsigned position;

	// Bitwise flags representing the characteristics of this entry
	uint32_t flags;

	Item(unsigned pos = NONE, uint32_t fl = UNINITIALIZED): position(pos), flags(fl) {}
};

struct Entry {
	// Type name
	std::string name;

	// Output of LLM analysis
	uint32_t flags;

	// It can be multiple entries for the same function (e.g., acquire on arg0 and release on arg1)
	::std::vector<Item> item_list;
};

// Function Dicts
::std::unordered_map<::std::string, EntryMetadata> func_index;
::std::vector<Entry> func_entries;
::std::string output_dir;

/// JSON file structure:
/// {
///   "FunctionName": {
///	   "ResourceTypeA": "ACQUIRE,RELEASE",
///    "ResourceTypeB": "USE"
///   },
///   ...
/// }


/// @brief Get the true name of the given string
/// @param mangledName The given alias name
/// @return The final string name of the mangledName
std::string demangleName(const std::string &mangledName)
{
    int status = 0;
    char *demangled = abi::__cxa_demangle(mangledName.c_str(), nullptr, nullptr, &status);
    std::string result;
    if (status == 0 && demangled != nullptr) {
        result = demangled;
        free(demangled);
    } else {
        result = mangledName;
    }

    // Find the function name without arguments
    size_t parenPos = result.find('(');
    if (parenPos != std::string::npos) {
        // Remove the arguments part
        result = result.substr(0, parenPos);
    }

    // Also remove any namespaces if you only want the final part (optional)
    // size_t colonsPos = result.rfind("::");
    // if (colonsPos != std::string::npos) {
    //     result = result.substr(colonsPos + 2);
    // }

    return result;
}

/* Helpers */
/// @brief Return the base name of a type (without pointers/references)
/// @param Ty The input DIType
/// @return The base DIType after stripping pointers/references
static std::string diTypeToString(const DIType *Ty) {
    if (!Ty) return "unknown";

	// Process derived types (e.g., typedefs, pointers, references) recursively
    if (const auto *DT = dyn_cast<DIDerivedType>(Ty)) {
        switch (DT->getTag()) {
            case dwarf::DW_TAG_typedef:
                if (!DT->getName().empty())
                    return DT->getName().str();
				// Continue to handle the base type if typedef is anonymous
                return diTypeToString(DT->getBaseType());

            case dwarf::DW_TAG_const_type:
                return "const " + diTypeToString(DT->getBaseType());
            case dwarf::DW_TAG_volatile_type:
                return "volatile " + diTypeToString(DT->getBaseType());
            case dwarf::DW_TAG_restrict_type:
                return "restrict " + diTypeToString(DT->getBaseType());
            case dwarf::DW_TAG_atomic_type:
                return "_Atomic " + diTypeToString(DT->getBaseType());

            case dwarf::DW_TAG_pointer_type:
                return diTypeToString(DT->getBaseType()) + "*";
            case dwarf::DW_TAG_reference_type:
                return diTypeToString(DT->getBaseType()) + "&";
            case dwarf::DW_TAG_rvalue_reference_type:
                return diTypeToString(DT->getBaseType()) + "&&";

            default:
                break;
        }
    }

	// Basic/Composite types: name may be empty (e.g., anonymous structs)
    if (!Ty->getName().empty())
        return Ty->getName().str();

    std::string S;
    raw_string_ostream OS(S);
    Ty->print(OS);          // Note: DIType::print outputs metadata style, not C type
    OS.flush();
    return S;
}

/// @brief Convert an LLVM IR Type to a string representation
/// @param Ty The LLVM IR Type to convert
/// @return A string representation of the LLVM IR Type
static std::string irTypeToString(const Type *Ty) {
    std::string S;
    raw_string_ostream OS(S);
    Ty->print(OS);
    OS.flush();
    return S;
}


/// @brief generate a mapping from function argument index to its stripped type name (sometimes may be buggy)
/// @param F The function to analyze
/// @param arg_type_map The map to store argument index to type name
void gen_fn_arg_mapping_from_signature(const Function &F,
                                       std::unordered_map<unsigned, std::string> &arg_type_map) {
    const DISubprogram *SP = F.getSubprogram();
    if (!SP) return;

    const DISubroutineType *SubTy = SP->getType();
    if (!SubTy) return;

    DITypeRefArray Tys = SubTy->getTypeArray();
	// Tys[0] is usually the return type; from 1 onwards are the parameters
	// Note: Tys may contain null (e.g., for void or unspecified types)
    unsigned argNo = 0;
    for (unsigned i = 1; i < Tys.size() && argNo < F.arg_size(); ++i, ++argNo) {
        const DIType *DITy = Tys[i];
        if (!DITy) {
            arg_type_map[argNo] = "unknown";
            continue;
        }
        arg_type_map[argNo] = diTypeToString(DITy);
    }
}

/// @brief Check if the argument is read-only within the function
/// @param F The function to analyze
/// @param ptr The argument (pointer) to check
/// @param visited The set of already visited values to avoid cycles
/// @return true if the argument is modified, false if it is read-only
bool is_modified(const Value *ptr, std::set<const Value*> &visited) {
	if (visited.count(ptr)) return false;
	visited.insert(ptr);

	for (const User *U : ptr->users()) {
		if (auto *Store = dyn_cast<StoreInst>(U)) {
			if (Store->getPointerOperand() == ptr)
				return true;
			
			if (Store->getValueOperand() == ptr) {
				const Value *storage_location = Store->getPointerOperand();
				if (auto *AI = dyn_cast<AllocaInst>(storage_location)) {
					if (visited.count(AI)) continue;
					visited.insert(AI);

					for (const User *AIUser : AI->users()) {
                        if (auto *LI = dyn_cast<LoadInst>(AIUser)) {
							// Found a Load that reads our Ptr
							// Recursively check the new value produced by this Load
                            if (is_modified(LI, visited)) return true;
                        }
                        else if (isa<StoreInst>(AIUser)) {
							// Ignore the stores to this Alloca (this is the store we are handling)
                            continue;
                        }
                        else {
							// If Alloca is used in other strange ways (e.g., escaping to outside the function)
                            return true;
                        }
                    }
				}
			}
		}
		else if (auto *MIE = dyn_cast<MemIntrinsic>(U)) {
				// If ptr is the destination of these operations, it is modified
				// MemTransferInst includes MemCpy and MemMove
                if (auto *MTI = dyn_cast<MemTransferInst>(MIE)) {
                    if (MTI->getRawDest() == ptr) return true;
                }
                else if (auto *MSI = dyn_cast<MemSetInst>(MIE)) {
                    if (MSI->getRawDest() == ptr) return true;
                }
        }
		else if (isa<AtomicRMWInst>(U) || isa<AtomicCmpXchgInst>(U)) {
			return true;
		}
		else if (isa<GetElementPtrInst>(U) || isa<BitCastInst>(U) || isa<AddrSpaceCastInst>(U)) { // BUGGY
			if (is_modified(U, visited))
				return true;
		}
		else if (auto *PN = dyn_cast<PHINode>(U)) {
                if (is_modified(PN, visited)) return true;
        }
		else if (auto *SI = dyn_cast<SelectInst>(U)) {
                if (is_modified(SI, visited)) return true;
        } 
		else if (auto *CB = dyn_cast<CallBase>(U)) {
			for (unsigned i = 0; i < CB->arg_size(); ++i) {
				if (CB->getArgOperand(i) != ptr)
					continue;

				Function* callee = CB->getCalledFunction();
				if (callee && !callee->isDeclaration()) {
					Argument *formal_arg = callee->getArg(i);
					
					if (is_modified(formal_arg, visited)) 
						return true;
				} else if (!CB->paramHasAttr(i, Attribute::ReadOnly)) {
					return true;
				}
			}
		}
	}
	return false;
}

/// @brief Check if the instruction is a potential hash operation
/// @param I The instruction to check
/// @return true if the instruction is a potential hash operation, false otherwise
bool is_potential_hash_op(const Instruction *I) {
	// Check bitwise operations: XOR, SHL, LSHR, ASHR, AND, OR
	// Usually these operations are used in hash computations
    switch (I->getOpcode()) {
        case Instruction::Xor:
        case Instruction::Shl:
        case Instruction::LShr:
        case Instruction::AShr:
        case Instruction::And:
        case Instruction::Or:
            return true;
		// Multiply is also commonly used in hashing (e.g., mul 31)
        case Instruction::Mul:
            return true;
        default:
            return false;
    }
}

/// @brief Perform taint analysis to check if the return value depends on the resource
/// @param F The function to analyze
/// @param position The resource type location
/// @param LI LoopInfo for the function (can be nullptr if not available)
/// @return uint32_t flags indicating whether the return value depends on the resource and if resource is read-only and if there are any search patterns
constexpr uint32_t REACH_RETURN = 1 << 0;
constexpr uint32_t HAS_SEARCH_PATTERN = 1 << 1;
constexpr uint32_t READ_ONLY = 1 << 2;
constexpr uint32_t IS_ARG_CONST = 1 << 3;
constexpr uint32_t ALL_SATISFIED = REACH_RETURN | HAS_SEARCH_PATTERN | READ_ONLY;

uint32_t taint_and_readonly_analysis(const Function &F,
								const unsigned position,
								const LoopInfo *LI) { 
	bool reach_return = false;
	bool has_search_pattern = false;
	bool modified = false;
	bool is_arg_const = false;

	// BFS or DFS to propagate taint from arguments to return value
	for (const auto &Arg : F.args()) {
		unsigned ArgNo = Arg.getArgNo();

		if (position != RET && ArgNo != position) continue;
		if (position == RET && Arg.getType()->isPointerTy() && Arg.hasAttribute(Attribute::ReadOnly))
			is_arg_const = true;

		std::set<const Value*> modified_visited;
		modified = is_modified(&Arg, modified_visited);

		// Initialize worklist and visited set
		::std::vector<const Value*> worklist;
		::std::set<const Value*> visited;

		worklist.push_back(&Arg);
		visited.insert(&Arg);


		while (!worklist.empty()) {
			const Value* current = worklist.back();
			worklist.pop_back();

			for (const User* U : current->users()) {
				// If we reach the return instruction
				if (isa<ReturnInst>(U))
					reach_return = true;

				if (const Instruction* inst = dyn_cast<Instruction>(U)) {
					if (isa<GetElementPtrInst>(inst) || is_potential_hash_op(inst) || (LI && LI->getLoopFor(inst->getParent())))
						has_search_pattern = true;

					if (visited.find(inst) == visited.end()) {
						visited.insert(inst);
						worklist.push_back(inst);
                    }
				}
			}
		}

		if (position != RET)
			break; // Only need to check one matching argument
	}

	uint32_t result_flags = reach_return ? REACH_RETURN : 0;
	if (has_search_pattern)		result_flags |= HAS_SEARCH_PATTERN;
	if (!modified)				result_flags |= READ_ONLY;
	if (is_arg_const)			result_flags |= IS_ARG_CONST;

	return result_flags;
}


/// @brief Validate the acquire operation for the given function and resource type
/// @param F The function to analyze
/// @param position The resource type location
/// @param result_flags The result flags to update based on the analysis
void validate_acquire_operation(Function &F, const unsigned position,
								const LoopInfo *LI, uint32_t& result_flags) {
	// Check if the function has a return value
	bool hasReturnValue = F.getReturnType()->isVoidTy() ? false : true;
    if (!hasReturnValue) {
		result_flags &= ~ACQUIRE;
        return;
    }

	// Perform data flow analysis to check if the return value depends on any of the function arguments
	uint32_t tain_result_flags = taint_and_readonly_analysis(F, position, LI);

	if (position == RET) {
		if (HAS_FLAG(tain_result_flags, ALL_SATISFIED)) {
			result_flags |= ACQUIRE;
		} else if (HAS_FLAG(tain_result_flags, IS_ARG_CONST) && HAS_FLAG(tain_result_flags, HAS_SEARCH_PATTERN)) {
			result_flags &= ~ACQUIRE;  // May need to adjust
			result_flags |= GET;
		} else result_flags &= ~ACQUIRE;
	} else {
		// Arguments
		if (HAS_FLAG(tain_result_flags, ALL_SATISFIED)) {
			result_flags |= ACQUIRE;  // Consistent as the previous implementation
		} else result_flags &= ~ACQUIRE;
	}
}

/// @brief Validate the release operation for the given function and resource type
/// @param F The function to analyze
/// @param position The resource type location
/// @param result_flags The result flags to update based on the analysis
void validate_release_operation(const Function &F, const unsigned position, uint32_t& result_flags) {
	// Validation passed, set the RELEASE flag
	result_flags |= RELEASE;
}

/// @brief Validate the wait operation for the given function and resource type
/// @param F The function to analyze
/// @param position The resource type location
/// @param result_flags The result flags to update based on the analysis
void validate_wait_operation(const Function &F, const unsigned position, uint32_t& result_flags) {
	// Just mark WAIT flag for now
	result_flags |= WAIT;
}


/// @brief Validate the use operation for the given function and resource type
/// @param F The function to analyze
/// @param position The resource type location
/// @param result_flags The result flags to update based on the analysis
void validate_use_operation(const Function &F, const unsigned position, uint32_t& result_flags) {
	// Just mark USE flag for now
	result_flags |= USE;
}

/// @brief Validate the access operation for the given function and resource type
/// @param F The function to analyze
/// @param position The resource type location
/// @param result_flags The result flags to update based on the analysis
void validate_access_operation(const Function &F, const unsigned position, uint32_t& result_flags) {
	// Just mark ACCESS flag for now
	result_flags |= ACCESS;
}

/// @brief Validate the get operation for the given function and resource type
/// @param F The function to analyze
/// @param position The resource type location
/// @param result_flags The result flags to update based on the analysis
void validate_get_operation(const Function &F, const unsigned position, uint32_t& result_flags) {
	// Just mark GET flag for now
	result_flags |= GET;
}

ResourceAnalysisModulePass::ResourceAnalysisModulePass(): is_enabled(false)
{
	const char *path_shared = std::getenv("TYPE_ANALYSIS_DATA");
    if (!path_shared) {
        errs() << "no TYPE_ANALYSIS_DATA\n";
        return;
    }

	const char *udf_output_dir = std::getenv("VALIDATION_OUTPUT_DIR");
	if (udf_output_dir)
		output_dir = udf_output_dir;

    std::ifstream shared_file(path_shared);
    if (!shared_file.is_open()) {
        errs() << "Failed to open file: " << path_shared << "\n";
        return;
    }

	const char *is_enabled_str = std::getenv("ENABLE_RESOURCE_ANALYSIS");
	if (is_enabled_str && std::strcmp(is_enabled_str, "1") == 0) {
		is_enabled = true;
	} else {
		return;
	}

    nlohmann::json resource_json;
    shared_file >> resource_json;

	size_t current_index = 0;
	for (auto const& [func_name, op_dict] : resource_json.items()) {
		if (!op_dict.is_object())
			continue;
        
		EntryMetadata metadata;
		metadata.begin_index = current_index;
		metadata.entry_size = op_dict.size();
		func_index[func_name] = metadata;
		for (auto const& [resource_name, optype_str] : op_dict.items()) {
			Entry entry;
			entry.name = resource_name;
			entry.flags = parse_operation_type(optype_str);
			func_entries.push_back(entry);
			++current_index;
		}
    }
	shared_file.close();
}

PreservedAnalyses ResourceAnalysisModulePass::run(Module &M, ModuleAnalysisManager &MAM) {
	if (!is_enabled) {
		return PreservedAnalyses::all();
	}

	FunctionPassManager FPM;
    FPM.addPass(SROAPass(SROAOptions::PreserveCFG));

	FunctionAnalysisManager FAM;
	PassBuilder PB;
    PB.registerFunctionAnalyses(FAM);

	bool been_triggered = false;
	for (Function &F : M) {
		if (F.isDeclaration() || F.isIntrinsic())
			continue;

		// Demangle function name
		std::string funcName = demangleName(F.getName().str());

		// TODO: some functions may be skipped based on naming patterns
		// E.g., function definited within the class will have "::" in the name after demangling
		// where function name in the func_index does not have "::"
		auto search = func_index.find(funcName);

		// If function does not request an analysis
		if (search == func_index.end())
			continue;

		been_triggered = true;

		// mem2reg to convert to SSA form
		FPM.run(F, FAM);

		// Get LoopInfo
		const LoopInfo &LI = FAM.getResult<LoopAnalysis>(F);

		// Retrieve metadata
		EntryMetadata &metadata = search->second;

		// Construct argument type mapping
		std::unordered_map<unsigned, std::string> arg_type_map;
		gen_fn_arg_mapping_from_signature(F, arg_type_map);

		// Get the function returns
		::std::string return_type_str = "";
		DISubprogram *SP = F.getSubprogram();
		if (!SP) {
			errs() << "Function " << F.getName() << " does not have debug information.\n";
			abort();
		}
		DISubroutineType *ST = SP->getType();
		if (ST) {
			const DITypeRefArray Elements = ST->getTypeArray();
			if (Elements.size() > 0) {
				const DIType *return_type = Elements[0]; // Index 0 is Return Type
				return_type_str = diTypeToString(return_type);
			}
	    }

		// Update mangled name in metadata
		metadata.mangled_name = F.getName().str();
		metadata.demangled_name = funcName;
		metadata.num_params = F.arg_size();

		errs() << "Analyzing function: " << funcName << "\n";

		// TODO: handle special cases:
		// Backlog: resource is the return value and also the arguments

		// Iterate over associated entries
		for (size_t i = 0; i < metadata.entry_size; ++i) {
			Entry &entry = func_entries[metadata.begin_index + i];

			// 0 means not found
			// bitwise OR of all matched argument positions if there are multiple matches (e.g., arg0 | arg1)
			::std::vector<Item> item_list;

			// Skip if no argument matches the resource type
			for (const auto &pair : arg_type_map) {
				const std::string& arg_type_str = pair.second;
				if (arg_type_str.find(entry.name) != ::std::string::npos)
					item_list.push_back(Item(pair.first));
			}

			bool if_resource_in_return = return_type_str.find(entry.name) != ::std::string::npos;
			if (item_list.empty()) {
				// Make sure the resource type is not in the return type as well
				if (!if_resource_in_return) {
					continue;  // This should be an error in LLM analysis, but we skip it for now
				} else {
					// Trust the LLM analysis that whether it is a GET or ACQUIRE
					if (HAS_FLAG(entry.flags, GET)) {
						item_list.push_back(Item(RET, GET | DONE));
						entry.item_list = item_list;
					} else if (HAS_FLAG(entry.flags, ACQUIRE)) {
						item_list.push_back(Item(RET, ACQUIRE | DONE));
						entry.item_list = item_list;
					} else {
						// Left as it is
						item_list.push_back(Item(static_cast<unsigned>(RET), entry.flags & ~UNINITIALIZED | DONE));
						entry.item_list = item_list;
					}
					continue;
				}
			}

			for (size_t i = 0; i < item_list.size(); ++i) {
				// Results
				uint32_t result_flags = UNINITIALIZED;
				unsigned current_position = item_list[i].position;

				// Perform analysis based on flags
				if (HAS_FLAG(entry.flags, ACQUIRE)) {
					validate_acquire_operation(F, current_position, &LI, result_flags);
				}
				if (HAS_FLAG(entry.flags, RELEASE) && !HAS_FLAG(result_flags, INVALID)) {
					// Analyze release operation
					validate_release_operation(F, current_position, result_flags);
				}
				if (HAS_FLAG(entry.flags, WAIT) && !HAS_FLAG(result_flags, INVALID)) {
					// Analyze wait operation
					validate_wait_operation(F, current_position, result_flags);
				}
				if (HAS_FLAG(entry.flags, USE) && !HAS_FLAG(result_flags, INVALID)) {
					// Analyze use operation
					validate_use_operation(F, current_position, result_flags);
				}
				if (HAS_FLAG(entry.flags, ACCESS) && !HAS_FLAG(result_flags, INVALID)) {
					// Analyze access operation
					validate_access_operation(F, current_position, result_flags);
				}
				if (HAS_FLAG(entry.flags, GET) && !HAS_FLAG(result_flags, INVALID)) {
					// Analyze get operation
					validate_get_operation(F, current_position, result_flags);
				}

				// Update entry item with analysis results
				result_flags &= ~UNINITIALIZED;
				result_flags |= DONE;
				item_list[i].flags = result_flags;
			}

			entry.item_list = item_list;
		}
	}

	// Dump results to a JSON file (in the same structure as input, but with updated flags)
	if (been_triggered) {
		const ::std::string& module_name = M.getModuleIdentifier();
		// Replace . in module name to _ for better file naming
		std::string sanitized_module_name = module_name;
		std::replace(sanitized_module_name.begin(), sanitized_module_name.end(), '.', '_');
		// Only use the base name of the module (remove directory paths) for the output file
		size_t last_slash_pos = sanitized_module_name.find_last_of("/\\");

		if (last_slash_pos != std::string::npos) {
			sanitized_module_name = sanitized_module_name.substr(last_slash_pos + 1);
		}

		std::string output_path = output_dir + "/" + sanitized_module_name + ".json";
		::std::cout << "Output path: " << output_path << std::endl;

		nlohmann::json output_json;
		for (const auto& [func_name, metadata] : func_index) {
			if (metadata.mangled_name.empty()) {
				// This function is not analyzed (e.g., in another module), skip it in the output
				continue;
			}

			nlohmann::json op_dict;
			bool any_updated = false;
			for (size_t i = 0; i < metadata.entry_size; ++i) {
				const Entry &entry = func_entries[metadata.begin_index + i];

				nlohmann::json entry_list;
				for (const auto& item : entry.item_list) {
					// Only include items that have been analyzed (i.e., DONE flag is set)
					if (!HAS_FLAG(item.flags, DONE)) {
						continue;
					}

					nlohmann::json item_json;
					item_json["flags"] = convert_operation_type_to_string(item.flags);
					item_json["position"] = item.position;
					entry_list.push_back(item_json);
				}

				op_dict[entry.name] = entry_list;  // May be null, we will clean it up in the next step
				any_updated = true;
			}
			if (any_updated) {
				nlohmann::json metadata_json;
				metadata_json["num_params"] = metadata.num_params;
				metadata_json["demangled_name"] = metadata.demangled_name;
				op_dict["__metadata__"] = metadata_json;
				output_json[metadata.mangled_name] = op_dict;
			}
		}

		std::ofstream output_file(output_path);
		if (!output_file.is_open()) {
			errs() << "Failed to open output file: " << output_path << "\n";
			return PreservedAnalyses::none();
		}
		output_file << output_json.dump(4);
	}

    return been_triggered ? PreservedAnalyses::none() : PreservedAnalyses::all();
}

 
extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo
llvmGetPassPluginInfo() {
    return {
        LLVM_PLUGIN_API_VERSION, "ResourceAnalysisModulePass", LLVM_VERSION_STRING,
        [](PassBuilder &PB) {
            // Register at PipelineStart to ensure it runs even at O0
            PB.registerPipelineStartEPCallback(
                [](ModulePassManager &MPM, OptimizationLevel Level) {
                    MPM.addPass(ResourceAnalysisModulePass());
                });
        }
    };
}

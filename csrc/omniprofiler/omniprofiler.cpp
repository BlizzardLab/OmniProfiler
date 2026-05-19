// runtime_hook.cc
// Build: clang++/g++ -O2 -fPIC -c runtime_hook.cc
// Link:  -lpthread
//
// Notes:
// - One TLS allocation per thread: an array of NUM_RINGBUFFER ring buffers.
// - Each ring buffer stores record_t {ptr, ts_ns, event}.
// - Destructor dumps records to per-thread log file if OMNIPROFILER_OUTPUT_PATH is set.

#include <pthread.h>
#include <unistd.h>

#include <atomic>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <ctime>
#include <nlohmann/json.hpp>

#include <string>

/// Monotonic timestamp in nanoseconds
static inline uint64_t now_ns() {
    timespec ts{};
#if defined(CLOCK_MONOTONIC_RAW)
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
#else
    clock_gettime(CLOCK_MONOTONIC, &ts);
#endif
    return static_cast<uint64_t>(ts.tv_sec) * 1000000000ull + static_cast<uint64_t>(ts.tv_nsec);
}

// Other Enums
constexpr uint16_t IS_EXIT = 1 << 15; // Use the highest bit to indicate entry (0) or exit (1)
constexpr uint16_t FUNCTION_INDEX_MASK = static_cast<uint16_t>(~IS_EXIT); // The rest 15 bits for function index

#define GET_FN_IDX(infos) ((infos) & FUNCTION_INDEX_MASK)
#define IS_EXIT_FLAG_SET(infos) ((infos) & IS_EXIT)

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


#ifndef NUM_RINGBUFFER
#define NUM_RINGBUFFER 16       // One ring buffer per resource type
#endif

#ifndef RINGBUFFER_SLOTS
#define RINGBUFFER_SLOTS 32768   // Must be power of two for efficient wrapping (recommended)
#endif

#ifndef RUNTIME_HOOK_ENABLE
#define RUNTIME_HOOK_ENABLE 1
#endif

struct record_t {
    void* ptr;   	 	// pointer value
    uint64_t ts_ns;  	// timestamp ns
    omni_event_t event; // event type (16 bits for flags, can be adjusted as needed)
	uint16_t infos;		// function infor (1 bit (enter/exit) + 15 bits for function index)
};

struct ringbuffer_t {
    record_t* buf = nullptr;
    uint32_t cap = 0;
    uint32_t idx = 0;
	uint32_t cnt = 0;
};

// ----- shutdown & registry -----
static std::atomic<bool> g_shutting_down{false};

// Per-thread state tracked in a global list so we can flush/free on dlclose.
struct thread_state_t {
    pthread_t tid;
    ringbuffer_t* rings;
    pthread_mutex_t mu;      // protects rings during add_record vs dump/free
    std::atomic<bool> freed; // defensive: prevent double free
    thread_state_t* next;
};

// Global list head + lock
static pthread_mutex_t g_registry_mu = PTHREAD_MUTEX_INITIALIZER;
static thread_state_t* g_registry_head = nullptr;

// TLS for thread_state pointer (separate from rings TLS)
static pthread_key_t g_state_key;
static pthread_once_t g_state_once = PTHREAD_ONCE_INIT;

// TLS points to an array [NUM_RINGBUFFER] of ringbuffer_t
static pthread_key_t g_tls_key;
static pthread_once_t g_tls_once = PTHREAD_ONCE_INIT;

// Optional global counter for debugging/health checks
static std::atomic<uint64_t> g_total_records{0};

static void init_state_key() {
    (void)pthread_key_create(&g_state_key, nullptr); // no destructor: we manage centrally
}

static thread_state_t* get_thread_state() {
    pthread_once(&g_state_once, init_state_key);
    return static_cast<thread_state_t*>(pthread_getspecific(g_state_key));
}

static void set_thread_state(thread_state_t* st) {
    pthread_once(&g_state_once, init_state_key);
    (void)pthread_setspecific(g_state_key, st);
}

static thread_state_t* register_thread_state(ringbuffer_t* rings) {
    auto* st = static_cast<thread_state_t*>(std::calloc(1, sizeof(thread_state_t)));
    if (!st) return nullptr;

    st->tid = pthread_self();
    st->rings = rings;
    st->freed.store(false, std::memory_order_relaxed);
    pthread_mutex_init(&st->mu, nullptr);

    pthread_mutex_lock(&g_registry_mu);
    st->next = g_registry_head;
    g_registry_head = st;
    pthread_mutex_unlock(&g_registry_mu);

    set_thread_state(st);
    return st;
}

static std::string make_log_path() {
    const char* output_path = std::getenv("OMNIPROFILER_OUTPUT_PATH");
    if (!output_path || output_path[0] == '\0') return {};

    // NOTE: pthread_t is opaque; printing it portably is tricky.
    // We'll cast to unsigned long long as a pragmatic choice; OK on Linux/glibc.
    const auto pid = static_cast<unsigned long>(::getpid());
    const auto tid = static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(pthread_self()));

    char filename[512];
    std::snprintf(filename, sizeof(filename), "%s/thread_%lu_%llu.json", output_path, pid, tid);
    return std::string(filename);
}

static void dump_thread_log(ringbuffer_t* rings) {
    if (!rings) return;

    const std::string output_path = make_log_path();
    if (output_path.empty()) {
        std::fprintf(stderr, "OMNIPROFILER_OUTPUT_PATH not set; skipping log dump\n");
        return;
    }

	nlohmann::json output_json;
	for (int i = 0; i < NUM_RINGBUFFER; ++i) {
		ringbuffer_t& rb = rings[i];
		if (rb.cnt == 0) continue;  // Skip empty buffers

		uint32_t count = (rb.cnt > rb.cap) ? rb.cap : rb.cnt;  // Handle wrap-around case

		char buf[20];

		// Track the latest timestamp for this resource type to help identify potential incomplete events
		uint64_t latest_ts_ns = 0;
		uint32_t latest_event_idx = 0;

		nlohmann::json event_list;
		for (uint32_t j = 0; j < count; ++j) {
			const record_t& r = rb.buf[j];
			nlohmann::json event_json;
			// as string to avoid JSON issues
			::std::snprintf(buf, sizeof(buf), "%p", (void*)r.ptr);
			event_json["ptr"] = ::std::string(buf);
			event_json["ts_ns"] = std::to_string(r.ts_ns);
			event_json["event"] = convert_operation_type_to_string(r.event);
			event_json["function_index"] = GET_FN_IDX(r.infos);
			event_json["is_exit"] = IS_EXIT_FLAG_SET(r.infos) ? true : false;
			event_list.push_back(event_json);

			if (r.ts_ns > latest_ts_ns) {
				latest_ts_ns = r.ts_ns;
				latest_event_idx = j;
			}
		}

		// Add an extra record to avoid orphaned entry events without corresponding exit events
		nlohmann::json end_event_json;
		const record_t& last_record = rb.buf[latest_event_idx];
		::std::snprintf(buf, sizeof(buf), "%p", (void*)last_record.ptr);
		end_event_json["ptr"] = ::std::string(buf);
		end_event_json["ts_ns"] = std::to_string(now_ns()); // Ensure it comes after the last event
		end_event_json["event"] = "END";
		end_event_json["function_index"] = GET_FN_IDX(last_record.infos);
		end_event_json["is_exit"] = true; // Mark as exit to indicate it's closing the event
		event_list.push_back(end_event_json);

		output_json[std::to_string(i)] = event_list;
	}

	std::ofstream output_file(output_path);
	if (!output_file.is_open()) {
		std::fprintf(stderr, "Failed to open log file for writing: %s\n", output_path.c_str());
		return;
	}
	output_file << output_json.dump(4);
}

static void thread_log_destructor(void* p) {
    auto* rings = static_cast<ringbuffer_t*>(p);
    if (!rings) return;

	thread_state_t* st = get_thread_state();

	if (!st) {
        // Fallback: no state tracked; best-effort dump/free
        dump_thread_log(rings);
        for (int i = 0; i < NUM_RINGBUFFER; ++i) std::free(rings[i].buf);
        std::free(rings);
        return;
    }

	// If global unload already freed, do nothing.
    bool expected = false;
    if (!st->freed.compare_exchange_strong(expected, true, std::memory_order_acq_rel))
        return;

    // pthread_mutex_lock(&st->mu);
    dump_thread_log(rings);
    for (int i = 0; i < NUM_RINGBUFFER; ++i) {
        std::free(rings[i].buf);
        rings[i].buf = nullptr;
        rings[i].cap = 0;
        rings[i].idx = 0;
        rings[i].cnt = 0;
    }
    std::free(rings);
    st->rings = nullptr;
    // pthread_mutex_unlock(&st->mu);
}

static void init_tls_key() {
    (void)pthread_key_create(&g_tls_key, thread_log_destructor);
}

static ringbuffer_t* get_thread_rings() {
    pthread_once(&g_tls_once, init_tls_key);

    ringbuffer_t* rings = static_cast<ringbuffer_t*>(pthread_getspecific(g_tls_key));
    if (rings) return rings;

    // Allocate ring metadata array
    rings = static_cast<ringbuffer_t*>(std::calloc(NUM_RINGBUFFER, sizeof(ringbuffer_t)));
    if (!rings) return nullptr;

    // Allocate each ring buffer
    for (int i = 0; i < NUM_RINGBUFFER; ++i) {
        rings[i].idx = 0;
        rings[i].cap = static_cast<uint32_t>(RINGBUFFER_SLOTS);
        rings[i].buf = static_cast<record_t*>(std::calloc(rings[i].cap, sizeof(record_t)));
        if (!rings[i].buf) {
            // cleanup
            for (int j = 0; j < i; ++j) {
                std::free(rings[j].buf);
            }
            std::free(rings);
            std::fprintf(stderr, "Failed to allocate thread log buffer\n");
            return nullptr;
        }
    }

    (void)pthread_setspecific(g_tls_key, rings);

	// Register this thread so we can flush/free on dlclose.
    // If registration fails, we still return rings, but unload flushing won't see it.
    (void)register_thread_state(rings);
    return rings;
}

// Exported symbol. MUST match the name used by your LLVM pass.
extern "C" void add_record(void* p, uint32_t info, uint32_t res_id) {
#if !RUNTIME_HOOK_ENABLE
    (void)p; (void)info; (void)res_id;
    return;
#else
	const char* is_enabled = ::getenv("OMNIPROFILER_ENABLE"); // touch env to potentially trigger dynamic loader to keep this symbol
	if (!is_enabled || std::strcmp(is_enabled, "1") != 0) return; // double-check at runtime

	// When shutting down, skip recording
	if (g_shutting_down.load(std::memory_order_acquire)) return;

	// Defensive: ignore out-of-range resource IDs
    if (res_id >= NUM_RINGBUFFER) return;

    ringbuffer_t* rings = get_thread_rings();
    if (!rings) return;

	uint16_t event_infos = static_cast<uint16_t>(info >> 16); // upper 16 bits for event info (e.g., flags)
	omni_event_t event = static_cast<omni_event_t>(info & 0xFFFF); // lower 16 bits for event flags

	auto now = now_ns();
	// std::fprintf(stderr, "Adding record: ptr=%p event=%s res_id=%u\n", p, convert_operation_type_to_string(event).c_str(), res_id);

	// thread_state_t* st = get_thread_state();
    // If state is missing (shouldn't), still attempt write without mutex (best-effort).
    // if (st) pthread_mutex_lock(&st->mu);

	/// START add_record
    ringbuffer_t& rb = rings[res_id];
    uint32_t i = rb.idx;
    if (i >= rb.cap) {
        // wrap (cheap)
        i &= (rb.cap - 1);  // assumes power-of-two cap; if not, use modulo
        rb.idx = i;
    }

	// May cause segmentation fault when shutdown with no lock protection
    record_t& r = rb.buf[i];
    r.ts_ns = now;
    r.event = event;
	r.infos = event_infos;
    r.ptr   = p;

    rb.idx = i + 1;
    rb.cnt = rb.cnt + 1;
    g_total_records.fetch_add(1, std::memory_order_relaxed);
	/// END add_record

	// if (st) pthread_mutex_unlock(&st->mu);
#endif
}

extern "C" uint64_t runtime_hook_total_records() {
    return g_total_records.load(std::memory_order_relaxed);
}

// Cleanup on library unload.
static void free_rings_locked(thread_state_t* st) {
    ringbuffer_t* rings = st->rings;
    if (!rings) return;

    dump_thread_log(rings);

    for (int i = 0; i < NUM_RINGBUFFER; ++i) {
        std::free(rings[i].buf);
        rings[i].buf = nullptr;
        rings[i].cap = 0;
        rings[i].idx = 0;
        rings[i].cnt = 0;
    }
    std::free(rings);
    st->rings = nullptr;
}

__attribute__((destructor))
static void runtime_hook_library_fini() {
    // Drop new records immediately
    g_shutting_down.store(true, std::memory_order_release);

    // Flush/free all threads we've seen.
    pthread_mutex_lock(&g_registry_mu);
    for (thread_state_t* st = g_registry_head; st; st = st->next) {
        // Mark freed once to avoid double-free if thread exits concurrently.
        bool expected = false;
        if (!st->freed.compare_exchange_strong(expected, true, std::memory_order_acq_rel))
            continue;

        pthread_mutex_lock(&st->mu);
        free_rings_locked(st);
        pthread_mutex_unlock(&st->mu);
    }
    pthread_mutex_unlock(&g_registry_mu);

    // Best-effort cleanup of pthread keys (does NOT run destructors)
    pthread_key_delete(g_tls_key);
    pthread_key_delete(g_state_key);
}
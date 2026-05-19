#include <cstdint>
#include <ctime>
#include <iostream>`

static inline uint64_t now_ns() {
    timespec ts{};
#if defined(CLOCK_MONOTONIC_RAW)
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
#else
    clock_gettime(CLOCK_MONOTONIC, &ts);
#endif
    return static_cast<uint64_t>(ts.tv_sec) * 1000000000ull + static_cast<uint64_t>(ts.tv_nsec);
}

int main() {
	uint64_t timestamp = now_ns();
	::std::cout << "Current timestamp (ns): " << timestamp << std::endl;
	return 0;
}
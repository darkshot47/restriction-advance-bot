/*
 * native_bench.cpp — tiny benchmark used to document the C++ engine's numbers.
 *
 * ``make bench`` prints the cost of one million escapes on 1 thread and on the
 * full pool.  The Python bridge exposes the same numbers through
 * ``native_engine.benchmark()`` so the bot can show them on the /engine page.
 */

#include "../restriction_engine.hpp"

#include <cstdio>

int main() {
    const long long iterations = 500000;
    long long serial = re_bench_escape(iterations, 1);
    long long parallel = re_bench_escape(iterations, 4);
    std::printf("restriction_engine %s\n", re_version());
    std::printf("threads             : %d\n", re_pool_threads());
    std::printf("escape 1 thread     : %.2f ms (%lld ops)\n", serial / 1e6, iterations);
    std::printf("escape 4 threads    : %.2f ms (%lld ops)\n", parallel / 1e6, iterations);
    return 0;
}

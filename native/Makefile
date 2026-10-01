# Makefile — builds the native engine without any third-party dependency.
#
#   make            -> build/librestriction_engine.so
#   make test       -> build the self-test binary and run it
#   make bench      -> print a Python-vs-C++ comparison helper
#   make clean      -> remove build/
#
# The Python bridge (native_engine.py) calls exactly these targets, so a deploy
# host only needs a C++17 compiler; when none is present the bridge falls back
# to the pure-Python implementation and the bot keeps working.

CXX      ?= g++
CXXFLAGS ?= -O3 -std=c++17 -fPIC -Wall -Wextra -fvisibility=hidden
LDFLAGS  ?= -shared
PTHREAD  ?= -pthread

BUILD    := build
LIB      := $(BUILD)/librestriction_engine.so
SRC      := restriction_engine.cpp
HDR      := restriction_engine.hpp

UNAME_S := $(shell uname -s 2>/dev/null || echo unknown)
ifeq ($(UNAME_S),Darwin)
	LIB := $(BUILD)/librestriction_engine.dylib
	LDFLAGS := -dynamiclib
endif

.PHONY: all test bench clean info

all: $(LIB)

$(LIB): $(SRC) $(HDR)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $(SRC) $(PTHREAD)
	@echo "built $@"

test: $(BUILD)/native_selftest
	@$(BUILD)/native_selftest

$(BUILD)/native_selftest: tests/native_selftest.cpp $(SRC) $(HDR)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) -I. -o $@ tests/native_selftest.cpp $(SRC) $(PTHREAD)

bench: $(BUILD)/native_bench
	@$(BUILD)/native_bench

$(BUILD)/native_bench: tests/native_bench.cpp $(SRC) $(HDR)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) -I. -o $@ tests/native_bench.cpp $(SRC) $(PTHREAD)

info:
	@echo "compiler: $(CXX)"
	@echo "flags:    $(CXXFLAGS)"
	@echo "library:  $(LIB)"

clean:
	rm -rf $(BUILD)

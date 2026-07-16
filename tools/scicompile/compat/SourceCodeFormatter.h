#pragma once
// The real header uses bare `endl` in inline members; make it resolvable (MSVC had
// `using namespace std` in effect at the include site).
#include <ostream>
using std::endl;
#include_next "SourceCodeFormatter.h"

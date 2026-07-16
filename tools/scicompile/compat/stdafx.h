// Linux compatibility PCH for building SCICompanion's SCI compiler headless.
// Shadows the real (MFC) stdafx.h via include-path precedence. Provides the
// Windows/MFC typedefs and macros the *compiler* subsystem uses -- GUI, editor,
// and threading are stubbed elsewhere. Semantics-preserving: CString is a real
// std::string wrapper; nothing here changes bytecode/selector resolution.
#pragma once

// std::stack / std::queue expose their underlying container only through the
// protected member `c`. The vendor code reads it via MSVC's non-standard
// stack::_Get_container(); we map that to `.c` (macro at the bottom of this
// file) and open up `c` here by making protected members public JUST while these
// two headers are FIRST parsed. This must precede every other include so that
// <stack>/<queue> (and their transitive deps) are not already guarded-in.
#define protected public
#include <stack>
#include <queue>
#undef protected

// NOTE: This header defines a handful of MSVC-compatibility MACROS at the very
// END (min/max, exception(->runtime_error), _Get_container). For that reason it
// pulls in a broad set of standard headers up front, so they are fully parsed
// BEFORE those macros become active (mirroring how <windows.h> min/max sit after
// the STL on MSVC). Keep the std includes here comprehensive.
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cstdarg>
#include <cassert>
#include <cctype>
#include <cmath>
#include <ctime>
#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#include <unordered_set>
#include <set>
#include <memory>
#include <algorithm>
#include <functional>
#include <stdexcept>
#include <exception>
#include <cstddef>
#include <sstream>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <list>
#include <deque>
#include <array>
#include <mutex>
#include <thread>
#include <future>
#include <chrono>
#include <condition_variable>
#include <typeinfo>
#include <typeindex>
#include <iterator>
#include <numeric>
#include <limits>
#include <random>
#include <regex>
#include <bitset>
#include <utility>
#include <tuple>
#include <initializer_list>

// ---- Windows integral typedefs ------------------------------------------
typedef uint8_t   BYTE;
typedef uint16_t  WORD;
typedef uint32_t  DWORD;
typedef int32_t   LONG;
typedef uint32_t  ULONG;
typedef uint16_t  USHORT;
typedef int16_t   SHORT;
typedef unsigned int UINT;
typedef int       BOOL;
typedef int       INT;
typedef char      TCHAR;
typedef wchar_t   WCHAR;
typedef intptr_t  INT_PTR;
typedef uintptr_t UINT_PTR;
typedef uintptr_t DWORD_PTR;
typedef long      HRESULT;

typedef const char* PCTSTR;
typedef const char* LPCTSTR;
typedef const char* PCSTR;
typedef const char* LPCSTR;
typedef char*       PSTR;
typedef char*       PTSTR;
typedef char*       LPSTR;
typedef char*       LPTSTR;
typedef wchar_t*    LPWSTR;
typedef char*       LPTCH;
typedef const wchar_t* PCWSTR;
typedef const wchar_t* LPCWSTR;

#ifndef TRUE
#define TRUE  1
#define FALSE 0
#endif
#define S_OK      ((HRESULT)0)
#define S_FALSE   ((HRESULT)1)
#define E_FAIL    ((HRESULT)0x80004005L)
#define SUCCEEDED(hr) (((HRESULT)(hr)) >= 0)
#define FAILED(hr)    (((HRESULT)(hr)) < 0)

// ---- narrow-string text macros (SCI uses char throughout) ---------------
#define _T(x)   x
#define TEXT(x) x
#define _TEXT(x) x

// ---- misc Windows macros ------------------------------------------------
#define ZeroMemory(p, n) memset((p), 0, (n))
#define ASSERT(x)  assert(x)
#define VERIFY(x)  ((void)(x))
#define _ASSERTE(x) assert(x)
#ifndef MAX_PATH
#define MAX_PATH 260
#endif
#ifndef __noop
#define __noop(...) ((void)0)
#endif
#define OutputDebugString(x) ((void)0)
#define stricmp  strcasecmp
#define _stricmp strcasecmp
#define strnicmp strncasecmp

// ---- CPoint / CRect / CSize (used by the text-buffer stream) -------------
struct CPoint {
    LONG x, y;
    CPoint() : x(0), y(0) {}
    CPoint(LONG x_, LONG y_) : x(x_), y(y_) {}
    bool operator==(const CPoint& o) const { return x == o.x && y == o.y; }
    bool operator!=(const CPoint& o) const { return !(*this == o); }
};
struct CSize {
    LONG cx, cy;
    CSize() : cx(0), cy(0) {}
    CSize(LONG a, LONG b) : cx(a), cy(b) {}
};
struct CRect {
    LONG left, top, right, bottom;
    CRect() : left(0), top(0), right(0), bottom(0) {}
    CRect(LONG l, LONG t, LONG r, LONG b) : left(l), top(t), right(r), bottom(b) {}
    LONG Width() const { return right - left; }
    LONG Height() const { return bottom - top; }
};

// ---- minimal CString (semantics-preserving std::string wrapper) ----------
class CString {
public:
    CString() {}
    CString(const char* s) : _s(s ? s : "") {}
    CString(const std::string& s) : _s(s) {}
    const char* GetString() const { return _s.c_str(); }
    operator const char*() const { return _s.c_str(); }
    int GetLength() const { return (int)_s.size(); }
    bool IsEmpty() const { return _s.empty(); }
    CString& operator=(const char* s) { _s = s ? s : ""; return *this; }
    CString& operator+=(const char* s) { _s += s ? s : ""; return *this; }
    CString& operator+=(char c) { _s += c; return *this; }
    char operator[](int i) const { return _s[(size_t)i]; }
    // MFC substring/search helpers (avoid std::min/max here -- macros defined later).
    CString Left(int n) const { if (n < 0) n = 0; if ((size_t)n > _s.size()) n = (int)_s.size(); return CString(_s.substr(0, n)); }
    CString Right(int n) const { int len = (int)_s.size(); if (n < 0) n = 0; if (n > len) n = len; return CString(_s.substr(len - n)); }
    CString Mid(int start) const { if (start < 0) start = 0; if ((size_t)start > _s.size()) start = (int)_s.size(); return CString(_s.substr(start)); }
    CString Mid(int start, int count) const { if (start < 0) start = 0; if ((size_t)start > _s.size()) start = (int)_s.size(); if (count < 0) count = 0; return CString(_s.substr(start, count)); }
    int Find(char c) const { size_t p = _s.find(c); return p == std::string::npos ? -1 : (int)p; }
    int ReverseFind(char c) const { size_t p = _s.rfind(c); return p == std::string::npos ? -1 : (int)p; }
    int CompareNoCase(const char* s) const { return strcasecmp(_s.c_str(), s ? s : ""); }
    int Compare(const char* s) const { return strcmp(_s.c_str(), s ? s : ""); }
    std::string _s;
};

// for deleting values in a map (from the real stdafx.h).
struct delete_map_value
{
    template<typename TKEY, typename TVALUE>
    void operator()(const std::pair<TKEY, TVALUE> &ptr) const { delete ptr.second; }
};

// ---- GUI/threading forward stubs (Task.h references CWnd) ----------------
class CWnd;   // never dereferenced in the compile path

// ---- Win32 API/GDI shims (handles, structs, stub functions) --------------
// Must come after the integral typedefs above (BYTE/WORD/DWORD/UINT/...) so
// the shim can build on them; must come before sci.h below, which references
// RGBQUAD/HANDLE/LARGE_INTEGER/etc in inline methods & struct definitions.
#include "winshim.h"
// Minimal MFC/legacy-namespace shims (CWnd, std::tr2::sys, stdext, ...).
#include "mfc_stubs.h"

// ---- Foundational SCI headers (mirrors the tail of the real stdafx.h) ----
// These provide ResourceType, LangSyntax, ScriptId, LineCol, SCIVersion, the
// sci::istream/ostream helpers, and assorted STL utilities that essentially
// every compiler translation unit depends on. We deliberately DO NOT pull in
// sciwin.h / CObjectWrap.h (pure GUI) -- those are stubbed only if referenced.
#include "sci.h"
#include "Version.h"
#include "Stream.h"
#include "StlUtil.h"

// bundled fmtlib lives in Src/CppFormat; angle-include <format.h> resolves via -I

// ==========================================================================
// MSVC-compatibility macros. Defined LAST, after every standard and
// foundational SCI header has been fully parsed, so they only affect the
// vendor translation-unit bodies that are compiled after this header. Each is
// a faithful, semantics-preserving translation of an MSVC extension the code
// relies on -- none change compiler/bytecode behavior.
// ==========================================================================

// MSVC's std::exception has a non-standard `const char*` constructor. libstdc++
// does not; std::runtime_error has the identical "message + what()" behavior and
// derives from std::exception (so catch/inheritance by std::exception is intact).
// Function-like so bare `std::exception` (catch clauses, base lists) is untouched.
#define exception(msg) runtime_error(msg)

// MSVC's min/max are mixed-type-friendly macros from <windows.h>. The vendor
// code uses bare min()/max() with mixed integer types (std::min/std::max and
// numeric_limits::max() are unused across the compile path -- verified). Defined
// after <algorithm>/<limits> so their std definitions are already in place.
#ifndef max
#define max(a, b) (((a) > (b)) ? (a) : (b))
#endif
#ifndef min
#define min(a, b) (((a) < (b)) ? (a) : (b))
#endif

// MSVC's std::stack/std::queue expose the underlying container via
// _Get_container(); libstdc++ uses the protected member `c` (made accessible
// above). `_Get_container()` -> `c`.
#define _Get_container() c

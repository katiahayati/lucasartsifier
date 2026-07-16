// Windows/Win32 API shim for building SCICompanion's SCI compiler on Linux.
// Provides the Win32 handle types, GDI structs, and API-function stubs that the
// *foundational* headers (sci.h in particular) reference in inline methods and
// struct definitions. None of these functions are exercised by the compile path
// -- they exist only so the widely-included headers parse and link. If any is
// ever actually called at runtime it is a no-op / benign default; the semantic
// compiler logic (selectors, classes, bytecode) never touches them.
#pragma once

#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <climits>
#include <string>
#include <stdexcept>
#include <unordered_map>

// MSVC's std::unordered_map exposed a non-standard lower_bound() that behaved
// like find() (used by the compiler for duplicate-key existence checks). This
// drop-in adds that method so the two `defines_map` typedefs in the shadowed
// CompileContext.h keep compiling with the identical (find-based) semantics.
namespace scicompat
{
    template <class K, class V>
    struct hash_map_lb : std::unordered_map<K, V>
    {
        typename std::unordered_map<K, V>::iterator lower_bound(const K &k) { return this->find(k); }
        typename std::unordered_map<K, V>::const_iterator lower_bound(const K &k) const { return this->find(k); }
    };
}

// ---- extra integral typedefs (beyond stdafx.h) --------------------------
typedef int64_t          LONGLONG;
typedef uint64_t         ULONGLONG;
typedef uintptr_t        ULONG_PTR;
typedef intptr_t         LONG_PTR;
typedef size_t           SIZE_T;
typedef int16_t          __int16_t_compat;
#ifndef __int8
#define __int8 int8_t
#endif
#ifndef __int16
#define __int16 int16_t
#endif
#ifndef __int32
#define __int32 int32_t
#endif
#ifndef __int64
#define __int64 int64_t
#endif
#ifndef __unaligned
#define __unaligned
#endif

// MSVC SAL annotations -> no-ops.
#define _Check_return_
#define _In_
#define _In_opt_
#define _Out_
#define _Out_opt_
#define _Inout_
#define _Inout_opt_
#define _In_z_
#define _In_reads_(x)
#define _Out_writes_(x)
#define _Ret_maybenull_
#define _Success_(x)
#define _Printf_format_string_
#define _Post_z_
#define _Deref_out_

// ---- MSVC declaration keywords -> no-ops on GCC/Linux -------------------
#define __declspec(x)
#ifndef _cdecl
#define _cdecl
#endif
#ifndef __cdecl
#define __cdecl
#endif
#ifndef __stdcall
#define __stdcall
#endif
#ifndef __fastcall
#define __fastcall
#endif
#ifndef __forceinline
#define __forceinline inline
#endif
#ifndef CALLBACK
#define CALLBACK
#endif
#ifndef WINAPI
#define WINAPI
#endif
#ifndef APIENTRY
#define APIENTRY
#endif
#ifndef PASCAL
#define PASCAL
#endif
#ifndef WINAPIV
#define WINAPIV
#endif

// ---- opaque Win32 handle types ------------------------------------------
typedef void*  HANDLE;
typedef void*  HGLOBAL;
typedef void*  HLOCAL;
typedef void*  HWND;
typedef void*  HDC;
typedef void*  HBITMAP;
typedef void*  HGDIOBJ;
typedef void*  HMENU;
typedef void*  HICON;
typedef void*  HCURSOR;
typedef void*  HINSTANCE;
typedef void*  HFONT;
typedef void*  HPALETTE;
typedef void*  HBRUSH;
typedef void*  HRGN;
typedef void*  HMODULE;
typedef void*  LPVOID;
typedef const void* LPCVOID;
typedef HANDLE HKEY;

#ifndef INVALID_HANDLE_VALUE
#define INVALID_HANDLE_VALUE ((HANDLE)(intptr_t)-1)
#endif
#ifndef NULL
#define NULL 0
#endif

// ---- word/long assembly macros ------------------------------------------
#ifndef MAKELONG
#define MAKELONG(a, b) ((LONG)(((WORD)(((DWORD_PTR)(a)) & 0xffff)) | ((DWORD)((WORD)(((DWORD_PTR)(b)) & 0xffff))) << 16))
#endif
#ifndef MAKEWORD
#define MAKEWORD(a, b) ((WORD)(((BYTE)(((DWORD_PTR)(a)) & 0xff)) | ((WORD)((BYTE)(((DWORD_PTR)(b)) & 0xff))) << 8))
#endif
#ifndef LOWORD
#define LOWORD(l) ((WORD)(((DWORD_PTR)(l)) & 0xffff))
#endif
#ifndef HIWORD
#define HIWORD(l) ((WORD)((((DWORD_PTR)(l)) >> 16) & 0xffff))
#endif
#ifndef LOBYTE
#define LOBYTE(w) ((BYTE)(((DWORD_PTR)(w)) & 0xff))
#endif
#ifndef HIBYTE
#define HIBYTE(w) ((BYTE)((((DWORD_PTR)(w)) >> 8) & 0xff))
#endif
#ifndef _countof
#define _countof(a) (sizeof(a) / sizeof((a)[0]))
#endif

// ---- GDI structs --------------------------------------------------------
typedef DWORD COLORREF;
#ifndef RGB
#define RGB(r, g, b) ((COLORREF)(((BYTE)(r)) | (((WORD)((BYTE)(g))) << 8) | (((DWORD)((BYTE)(b))) << 16)))
#endif

typedef struct tagRGBQUAD {
    BYTE rgbBlue;
    BYTE rgbGreen;
    BYTE rgbRed;
    BYTE rgbReserved;
} RGBQUAD;

typedef struct tagBITMAPINFOHEADER {
    DWORD biSize;
    LONG  biWidth;
    LONG  biHeight;
    WORD  biPlanes;
    WORD  biBitCount;
    DWORD biCompression;
    DWORD biSizeImage;
    LONG  biXPelsPerMeter;
    LONG  biYPelsPerMeter;
    DWORD biClrUsed;
    DWORD biClrImportant;
} BITMAPINFOHEADER;

typedef struct tagBITMAPINFO {
    BITMAPINFOHEADER bmiHeader;
    RGBQUAD          bmiColors[1];
} BITMAPINFO;

typedef struct tagBITMAPFILEHEADER {
    WORD  bfType;
    DWORD bfSize;
    WORD  bfReserved1;
    WORD  bfReserved2;
    DWORD bfOffBits;
} BITMAPFILEHEADER;

typedef union _LARGE_INTEGER {
    struct { DWORD LowPart; LONG HighPart; };
    LONGLONG QuadPart;
} LARGE_INTEGER;

typedef struct _FILETIME {
    DWORD dwLowDateTime;
    DWORD dwHighDateTime;
} FILETIME;

typedef struct tagPOINT { LONG x; LONG y; } POINT;
typedef struct tagSIZE  { LONG cx; LONG cy; } SIZE;
typedef struct tagRECT  { LONG left; LONG top; LONG right; LONG bottom; } RECT;
typedef RECT* LPRECT;
typedef RECT* PRECT;

typedef struct _WIN32_FIND_DATAA
{
    DWORD    dwFileAttributes;
    FILETIME ftCreationTime;
    FILETIME ftLastAccessTime;
    FILETIME ftLastWriteTime;
    DWORD    nFileSizeHigh;
    DWORD    nFileSizeLow;
    DWORD    dwReserved0;
    DWORD    dwReserved1;
    char     cFileName[260];
    char     cAlternateFileName[14];
} WIN32_FIND_DATA;

// ---- MessageBox flags ---------------------------------------------------
#define MB_OK               0x00000000
#define MB_OKCANCEL         0x00000001
#define MB_YESNO            0x00000004
#define MB_YESNOCANCEL      0x00000003
#define MB_ICONHAND         0x00000010
#define MB_ICONERROR        0x00000010
#define MB_ICONQUESTION     0x00000020
#define MB_ICONEXCLAMATION  0x00000030
#define MB_ICONWARNING      0x00000030
#define MB_ICONASTERISK     0x00000040
#define MB_ICONINFORMATION  0x00000040
#define MB_APPLMODAL        0x00000000
#define MB_DEFBUTTON2       0x00000100
#define IDOK     1
#define IDCANCEL 2
#define IDYES    6
#define IDNO     7

// ---- HRESULT helpers ----------------------------------------------------
#ifndef HRESULT_FROM_WIN32
#define HRESULT_FROM_WIN32(x) ((HRESULT)(x) <= 0 ? (HRESULT)(x) : (HRESULT)(((x) & 0x0000FFFF) | (7 << 16) | 0x80000000))
#endif
#define E_OUTOFMEMORY   ((HRESULT)0x8007000EL)
#define E_INVALIDARG    ((HRESULT)0x80070057L)
#define E_NOTIMPL       ((HRESULT)0x80004001L)
#define E_ACCESSDENIED  ((HRESULT)0x80070005L)

// Win32 error codes.
#define ERROR_SUCCESS            0L
#define ERROR_FILE_NOT_FOUND     2L
#define ERROR_OUTOFMEMORY        14L
#define ERROR_INVALID_DATA       13L
#define ERROR_INVALID_PARAMETER  87L
#define ERROR_FILE_READ_ONLY     6009L
#define ERROR_ALREADY_EXISTS     183L

// File-attribute constants / access rights.
#define INVALID_FILE_ATTRIBUTES   0xFFFFFFFFu
#define FILE_ATTRIBUTE_READONLY   0x00000001u
#define FILE_ATTRIBUTE_DIRECTORY  0x00000010u
#define DELETE                    0x00010000u

// ---- File I/O constants (real, POSIX-backed impl in winfile.cpp) --------
#define GENERIC_READ      0x80000000u
#define GENERIC_WRITE     0x40000000u
#define FILE_SHARE_READ   0x00000001u
#define FILE_SHARE_WRITE  0x00000002u
#define FILE_SHARE_DELETE 0x00000004u
#define CREATE_NEW        1
#define CREATE_ALWAYS     2
#define OPEN_EXISTING     3
#define OPEN_ALWAYS       4
#define TRUNCATE_EXISTING 5
#define FILE_ATTRIBUTE_NORMAL 0x80u
#define FILE_BEGIN        0
#define FILE_CURRENT      1
#define FILE_END          2
#define INVALID_FILE_SIZE 0xFFFFFFFFu
#define INVALID_SET_FILE_POINTER 0xFFFFFFFFu
#define PAGE_READONLY     0x02u
#define PAGE_READWRITE    0x04u
#define FILE_MAP_READ     0x0004u
#define FILE_MAP_WRITE    0x0002u
#define FORMAT_MESSAGE_FROM_SYSTEM     0x00001000u
#define FORMAT_MESSAGE_IGNORE_INSERTS  0x00000200u
#define FORMAT_MESSAGE_ALLOCATE_BUFFER 0x00000100u
#ifndef ARRAYSIZE
#define ARRAYSIZE(a) (sizeof(a) / sizeof((a)[0]))
#endif

// Real, POSIX-backed Win32 file I/O (defined in compat/winfile.cpp). These make
// the resource-map / SCO / stream code actually read files; a missing file
// yields INVALID_HANDLE_VALUE exactly like the Win32 originals, so absent
// resources (source-only projects) degrade gracefully instead of crashing.
HANDLE CreateFileA(const char *fileName, DWORD desiredAccess, DWORD shareMode,
                   void *securityAttributes, DWORD creationDisposition,
                   DWORD flagsAndAttributes, HANDLE templateFile);
#ifndef CreateFile
#define CreateFile CreateFileA
#endif
int    CloseHandle(HANDLE hObject);
int    ReadFile(HANDLE hFile, void *buffer, DWORD numberOfBytesToRead,
                DWORD *numberOfBytesRead, void *overlapped);
int    WriteFile(HANDLE hFile, const void *buffer, DWORD numberOfBytesToWrite,
                 DWORD *numberOfBytesWritten, void *overlapped);
DWORD  GetFileSize(HANDLE hFile, DWORD *fileSizeHigh);
DWORD  SetFilePointer(HANDLE hFile, LONG distanceToMove, LONG *distanceToMoveHigh,
                      DWORD moveMethod);
HANDLE CreateFileMappingA(HANDLE hFile, void *attrs, DWORD protect,
                          DWORD maxSizeHigh, DWORD maxSizeLow, const char *name);
#ifndef CreateFileMapping
#define CreateFileMapping CreateFileMappingA
#endif
void  *MapViewOfFile(HANDLE hFileMappingObject, DWORD desiredAccess,
                     DWORD fileOffsetHigh, DWORD fileOffsetLow, SIZE_T numberOfBytesToMap);
int    UnmapViewOfFile(const void *baseAddress);

// Misc MSVC/Win32 helpers used by the compiler subsystem.
int    StrToInt(const char *psz);
// Normalize '\'->'/' and resolve real case of an existing path (Linux case-sensitivity).
std::string ResolveCasePath(const char *p);
int    PathFileExistsA(const char *path);
#ifndef PathFileExists
#define PathFileExists PathFileExistsA
#endif

// shlwapi path/string helpers (real, POSIX-backed).
const char *StrRStrIA(const char *pszSource, const char *pszLast, const char *pszSrch);
const char *PathFindFileNameA(const char *path);
const char *PathFindExtensionA(const char *path);
const char *StrChrA(const char *psz, char ch);
#ifndef PathFindExtension
#define PathFindExtension PathFindExtensionA
#endif

// MSVC bounded string ops (array-size template form: dst[], src, count).
inline int strncat_s(char *dst, const char *src, size_t size)
{
    if (!dst || !src || size == 0) return 22;
    size_t dl = strnlen(dst, size);
    if (dl >= size) return 22;
    strncat(dst, src, size - dl - 1);
    return 0;
}
inline int strncpy_s(char *dst, const char *src, size_t size)
{
    if (!dst || !src || size == 0) return 22;
    strncpy(dst, src, size);
    dst[size - 1] = 0;
    return 0;
}

// COLORREF component extraction (Win32 macros).
#ifndef GetRValue
#define GetRValue(rgb) ((BYTE)((rgb) & 0xff))
#define GetGValue(rgb) ((BYTE)(((rgb) >> 8) & 0xff))
#define GetBValue(rgb) ((BYTE)(((rgb) >> 16) & 0xff))
#endif

// Windows 'byte' alias (util.cpp uses a bare `byte`).
typedef unsigned char byte;

// Module/version stubs (util.cpp GetDllVersion -- never meaningfully used).
typedef struct _DLLVERSIONINFO
{
    DWORD cbSize, dwMajorVersion, dwMinorVersion, dwBuildNumber, dwPlatformID;
} DLLVERSIONINFO;
typedef HRESULT (*DLLGETVERSIONPROC)(DLLVERSIONINFO *);
typedef void (*FARPROC)();
inline HMODULE LoadLibraryA(const char *) { return nullptr; }
#ifndef LoadLibrary
#define LoadLibrary LoadLibraryA
#endif
inline int    FreeLibrary(HMODULE) { return 1; }
inline FARPROC GetProcAddress(HMODULE, const char *) { return nullptr; }

// Shell file-operation stub (util.cpp CopyFilesOver/DeleteDirectory -- headless no-op).
#define FO_MOVE   1
#define FO_COPY   2
#define FO_DELETE 3
#define FO_RENAME 4
#define FOF_NOCONFIRMMKDIR        0x0200u
#define FOF_NOCOPYSECURITYATTRIBS 0x0800u
#define FOF_NOCONFIRMATION        0x0010u
#define FOF_SILENT                0x0004u
typedef struct _SHFILEOPSTRUCTA
{
    HWND        hwnd;
    UINT        wFunc;
    const char *pFrom;
    const char *pTo;
    WORD        fFlags;
    int         fAnyOperationsAborted;
    void       *hNameMappings;
    const char *lpszProgressTitle;
} SHFILEOPSTRUCT;
inline int SHFileOperationA(SHFILEOPSTRUCT *) { return 1; /* non-zero = not performed */ }
#ifndef SHFileOperation
#define SHFileOperation SHFileOperationA
#endif
#define FOF_NOERRORUI 0x0400u

// Local heap (util.cpp error-formatting) -- map onto malloc/free.
#define LMEM_ZEROINIT 0x0040u
inline void  *LocalAlloc(UINT flags, SIZE_T bytes) { void *p = malloc(bytes ? bytes : 1); if (p && (flags & LMEM_ZEROINIT)) memset(p, 0, bytes); return p; }
inline void  *LocalFree(void *p) { free(p); return nullptr; }
inline SIZE_T LocalSize(void *) { return 0; }

// Language-id macros for FormatMessage.
#define LANG_NEUTRAL     0x00
#define SUBLANG_DEFAULT  0x01
#define MAKELANGID(p, s) ((WORD)(((WORD)(s) << 10) | (WORD)(p)))
#define FORMAT_MESSAGE_ARGUMENT_ARRAY 0x00002000u

#define BI_RGB 0

// Copy/move/fill memory (Win32 macros).
#ifndef CopyMemory
#define CopyMemory(d, s, n) memcpy((d), (s), (n))
#endif
#ifndef MoveMemory
#define MoveMemory(d, s, n) memmove((d), (s), (n))
#endif
#ifndef FillMemory
#define FillMemory(d, n, v) memset((d), (v), (n))
#endif

inline short GetKeyState(int) { return 0; }

// shlwapi PathIsRelative.
inline int PathIsRelativeA(const char *p) { return (p && p[0] == '/') ? 0 : 1; }
#ifndef PathIsRelative
#define PathIsRelative PathIsRelativeA
#endif
// shlwapi PathMatchSpec (wildcard match).
int PathMatchSpecA(const char *file, const char *spec);
#ifndef PathMatchSpec
#define PathMatchSpec PathMatchSpecA
#endif

// GetTempFileName / .ini read+write (real; game.ini IS read by the compile path).
UINT  GetTempFileNameA(const char *pathName, const char *prefix, UINT unique, char *tempFileName);
DWORD GetFileAttributesA(const char *fileName);
DWORD GetPrivateProfileSectionA(const char *section, char *buffer, DWORD size, const char *fileName);
#ifndef GetFileAttributes
#define GetFileAttributes GetFileAttributesA
#endif
#ifndef GetPrivateProfileSection
#define GetPrivateProfileSection GetPrivateProfileSectionA
#endif
// File enumeration -- source-only projects have no compiled resources, so the
// stub reports "no matches" (INVALID_HANDLE_VALUE), which is the correct result.
inline HANDLE FindFirstFileA(const char *, WIN32_FIND_DATA *) { return INVALID_HANDLE_VALUE; }
inline int    FindNextFileA(HANDLE, WIN32_FIND_DATA *) { return 0; }
inline int    FindClose(HANDLE) { return 1; }
#ifndef FindFirstFile
#define FindFirstFile FindFirstFileA
#endif
#ifndef FindNextFile
#define FindNextFile FindNextFileA
#endif
DWORD GetPrivateProfileStringA(const char *section, const char *key, const char *def,
                               char *buffer, DWORD size, const char *fileName);
UINT  GetPrivateProfileIntA(const char *section, const char *key, int def, const char *fileName);
int   WritePrivateProfileStringA(const char *section, const char *key, const char *value, const char *fileName);
#ifndef GetTempFileName
#define GetTempFileName GetTempFileNameA
#endif
#ifndef GetPrivateProfileString
#define GetPrivateProfileString GetPrivateProfileStringA
#endif
#ifndef GetPrivateProfileInt
#define GetPrivateProfileInt GetPrivateProfileIntA
#endif
#ifndef WritePrivateProfileString
#define WritePrivateProfileString WritePrivateProfileStringA
#endif

// ShellExecuteEx (RunLogic 'run game' path -- headless no-op).
#define SEE_MASK_NOCLOSEPROCESS 0x00000040u
typedef struct _SHELLEXECUTEINFOA
{
    DWORD       cbSize;
    ULONG       fMask;
    HWND        hwnd;
    const char *lpVerb;
    const char *lpFile;
    const char *lpParameters;
    const char *lpDirectory;
    int         nShow;
    HINSTANCE   hInstApp;
    void       *lpIDList;
    const char *lpClass;
    HKEY        hkeyClass;
    DWORD       dwHotKey;
    HANDLE      hIcon;
    HANDLE      hProcess;
} SHELLEXECUTEINFO;
inline int ShellExecuteExA(SHELLEXECUTEINFO *p) { if (p) p->hProcess = nullptr; return 0; }
#ifndef ShellExecuteEx
#define ShellExecuteEx ShellExecuteExA
#endif
#define SEE_MASK_DEFAULT 0x00000000u

// Expand %VAR% environment references (RunLogic 'run game' path -- not compiled logic).
inline DWORD ExpandEnvironmentStringsA(const char *src, char *dst, DWORD size)
{
    if (!dst || size == 0) return 0;
    std::string out;
    for (const char *p = src ? src : ""; *p;)
    {
        if (*p == '%')
        {
            const char *e = strchr(p + 1, '%');
            if (e)
            {
                std::string var(p + 1, (size_t)(e - (p + 1)));
                const char *v = getenv(var.c_str());
                if (v) out += v;
                p = e + 1;
                continue;
            }
        }
        out += *p++;
    }
    size_t n = out.size();
    if (n >= size) n = size - 1;
    memcpy(dst, out.data(), n);
    dst[n] = 0;
    return (DWORD)(n + 1);
}
#ifndef ExpandEnvironmentStrings
#define ExpandEnvironmentStrings ExpandEnvironmentStringsA
#endif
#ifndef StrRStrI
#define StrRStrI StrRStrIA
#endif
#ifndef PathFindFileName
#define PathFindFileName PathFindFileNameA
#endif
#ifndef StrChr
#define StrChr StrChrA
#endif

// File-time helpers (real: derived from st_mtime).
int  GetFileTime(HANDLE hFile, FILETIME *creation, FILETIME *lastAccess, FILETIME *lastWrite);
LONG CompareFileTime(const FILETIME *a, const FILETIME *b);

// File/dir operations (real, POSIX-backed).
int  CreateDirectoryA(const char *path, void *securityAttributes);
int  DeleteFileA(const char *path);
int  MoveFileA(const char *from, const char *to);
int  CopyFileA(const char *from, const char *to, int failIfExists);
DWORD GetTempPathA(DWORD bufferLength, char *buffer);
DWORD GetModuleFileNameA(HMODULE module, char *buffer, DWORD size);
#ifndef CreateDirectory
#define CreateDirectory CreateDirectoryA
#endif
#ifndef DeleteFile
#define DeleteFile DeleteFileA
#endif
#ifndef MoveFile
#define MoveFile MoveFileA
#endif
#ifndef CopyFile
#define CopyFile CopyFileA
#endif
#ifndef GetTempPath
#define GetTempPath GetTempPathA
#endif
#ifndef GetModuleFileName
#define GetModuleFileName GetModuleFileNameA
#endif

// Process/shell operations -- NOT part of the compile path; benign stubs so the
// GUI/debug helper functions in util.cpp compile & link (never invoked headless).
#define PROCESS_TERMINATE 0x0001u
#define SW_SHOWNORMAL     1
#define TH32CS_SNAPPROCESS 0x00000002u
#define INFINITE          0xFFFFFFFFu
inline DWORD  GetProcessId(HANDLE) { return 0; }
inline HANDLE OpenProcess(DWORD, int, DWORD) { return nullptr; }
inline int    TerminateProcess(HANDLE, UINT) { return 0; }
inline int    GetExitCodeProcess(HANDLE, DWORD *code) { if (code) *code = 0; return 1; }
inline DWORD  WaitForSingleObject(HANDLE, DWORD) { return 0; }
typedef void* HINSTANCE_RET;
inline void*  ShellExecuteA(HWND, const char *, const char *, const char *, const char *, int) { return (void *)(intptr_t)42; }
#ifndef ShellExecute
#define ShellExecute ShellExecuteA
#endif
DWORD  FormatMessageA(DWORD flags, const void *source, DWORD messageId,
                      DWORD languageId, char *buffer, DWORD size, void *args);
#ifndef FormatMessage
#define FormatMessage FormatMessageA
#endif
int    StringCchPrintfA(char *dest, size_t destSize, const char *format, ...);
int    StringCchVPrintfA(char *dest, size_t destSize, const char *format, va_list args);
int    StringCchCopyA(char *dest, size_t destSize, const char *src);
int    StringCchCatA(char *dest, size_t destSize, const char *src);
#ifndef StringCchPrintf
#define StringCchPrintf StringCchPrintfA
#endif
#ifndef StringCchVPrintf
#define StringCchVPrintf StringCchVPrintfA
#endif
#ifndef StringCchCopy
#define StringCchCopy StringCchCopyA
#endif
#ifndef StringCchCat
#define StringCchCat StringCchCatA
#endif

// ---- Win32 API stubs (declared inline; benign no-ops) -------------------
inline DWORD  GetLastError() { return 0; }
inline void   SetLastError(DWORD) {}
inline HGLOBAL GlobalAlloc(UINT, SIZE_T bytes) { return calloc(1, bytes ? bytes : 1); }
inline HGLOBAL GlobalFree(HGLOBAL h) { free(h); return nullptr; }
inline void*  GlobalLock(HGLOBAL h) { return h; }
inline int    GlobalUnlock(HGLOBAL) { return 0; }
inline SIZE_T GlobalSize(HGLOBAL) { return 0; }
inline int    QueryPerformanceFrequency(LARGE_INTEGER* p) { if (p) p->QuadPart = 1000000; return 1; }
inline int    QueryPerformanceCounter(LARGE_INTEGER* p) { if (p) p->QuadPart = 0; return 1; }
inline int    PostMessage(HWND, UINT, UINT_PTR, LONG_PTR) { return 1; }
inline int    SendMessage(HWND, UINT, UINT_PTR, LONG_PTR) { return 0; }
inline DWORD  GetTickCount() { return 0; }
inline HANDLE GetCurrentThread() { return nullptr; }
inline HANDLE GetCurrentProcess() { return nullptr; }

// ---- string helpers -----------------------------------------------------
#ifndef lstrlen
inline int lstrlen(const char* s) { return s ? (int)strlen(s) : 0; }
#endif
#ifndef lstrcmp
inline int lstrcmp(const char* a, const char* b) { return strcmp(a, b); }
#endif
#ifndef lstrcmpi
inline int lstrcmpi(const char* a, const char* b) { return strcasecmp(a, b); }
#endif

// sprintf_s / vsprintf_s / _snprintf variants used across the codebase.
#ifndef sprintf_s
#define sprintf_s(buf, size, ...) snprintf((buf), (size), __VA_ARGS__)
#endif
#ifndef _snprintf_s
#define _snprintf_s(buf, size, count, ...) snprintf((buf), (size), __VA_ARGS__)
#endif
#ifndef vsprintf_s
#define vsprintf_s(buf, size, fmt, args) vsnprintf((buf), (size), (fmt), (args))
#endif
#ifndef strcpy_s
inline int strcpy_s(char* d, size_t n, const char* s) { if (!d || !s) return 22; strncpy(d, s, n); d[n ? n - 1 : 0] = 0; return 0; }
#endif
#ifndef strcat_s
inline int strcat_s(char* d, size_t n, const char* s) { if (!d || !s) return 22; strncat(d, s, n - strlen(d) - 1); return 0; }
#endif

// ---- MFC "Afx" throw/messagebox helpers (used in a few resource files) --
inline int AfxMessageBox(const char* msg, UINT = MB_OK, UINT = 0)
{
    if (msg) { fprintf(stderr, "[AfxMessageBox] %s\n", msg); }
    return IDOK;
}
[[noreturn]] inline void AfxThrowUserException() { throw std::runtime_error("AfxUserException"); }
[[noreturn]] inline void AfxThrowMemoryException() { throw std::bad_alloc(); }
[[noreturn]] inline void AfxThrowNotSupportedException() { throw std::runtime_error("NotSupported"); }

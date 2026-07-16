// POSIX-backed implementation of the small set of Win32 file/message APIs that
// SCICompanion's resource, stream, and SCO code calls. These are REAL: they open
// and read actual files, so resource enumeration and SCO loading work when the
// files exist, and fail cleanly (INVALID_HANDLE_VALUE) when they don't -- exactly
// the Win32 contract the code relies on.
#include "stdafx.h"

#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <fnmatch.h>
#include <dirent.h>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <unordered_map>

namespace
{
    // Case-insensitive lookup of `name` within directory `dir`. Returns the actual
    // on-disk name, or "" if none. SCICompanion (Windows) assumes a case-insensitive
    // filesystem; on Linux we resolve the real case here.
    std::string ciFind(const std::string &dir, const std::string &name)
    {
        DIR *d = ::opendir(dir.empty() ? "." : dir.c_str());
        if (!d) return "";
        std::string found;
        struct dirent *e;
        while ((e = ::readdir(d)) != nullptr)
        {
            if (strcasecmp(e->d_name, name.c_str()) == 0) { found = e->d_name; break; }
        }
        ::closedir(d);
        return found;
    }

    // SCICompanion builds paths with Windows '\' separators (ScriptId::GetFullPath,
    // GetScriptFileName, GetSrcFolder, ...) and assumes case-insensitivity. Normalize
    // '\'->'/' and, if the exact path is missing, resolve each component's real case.
    std::string normPath(const char *p)
    {
        std::string s(p ? p : "");
        for (char &c : s) { if (c == '\\') c = '/'; }
        if (s.empty() || ::access(s.c_str(), F_OK) == 0) return s;   // fast path

        // Walk components, matching each case-insensitively against the real FS.
        std::string resolved;
        size_t i = 0;
        if (!s.empty() && s[0] == '/') { resolved = ""; i = 1; }     // absolute
        bool leadingSlash = (!s.empty() && s[0] == '/');
        while (i <= s.size())
        {
            size_t slash = s.find('/', i);
            std::string comp = s.substr(i, (slash == std::string::npos ? s.size() : slash) - i);
            if (!comp.empty() && comp != ".")
            {
                std::string base = resolved.empty() ? (leadingSlash ? "/" : "") : resolved + "/";
                std::string candidate = base + comp;
                if (::access(candidate.c_str(), F_OK) == 0)
                {
                    resolved = candidate;
                }
                else
                {
                    std::string real = ciFind(base.empty() ? "." : base, comp);
                    resolved = real.empty() ? candidate : base + real;   // give up -> original (open will fail)
                }
            }
            if (slash == std::string::npos) break;
            i = slash + 1;
        }
        return resolved.empty() ? s : resolved;
    }

    struct WinHandle { int fd; };

    // base address -> mapped length, so UnmapViewOfFile can munmap correctly.
    std::mutex g_mapMutex;
    std::unordered_map<const void *, size_t> g_mappings;
}

HANDLE CreateFileA(const char *fileName, DWORD desiredAccess, DWORD /*shareMode*/,
                   void * /*securityAttributes*/, DWORD creationDisposition,
                   DWORD /*flagsAndAttributes*/, HANDLE /*templateFile*/)
{
    int oflag;
    const bool wantWrite = (desiredAccess & GENERIC_WRITE) != 0;
    oflag = wantWrite ? O_RDWR : O_RDONLY;

    switch (creationDisposition)
    {
    case CREATE_NEW:      oflag |= O_CREAT | O_EXCL; break;
    case CREATE_ALWAYS:   oflag |= O_CREAT | O_TRUNC; if (!wantWrite) oflag = (oflag & ~O_RDONLY) | O_RDWR; break;
    case OPEN_ALWAYS:     oflag |= O_CREAT; break;
    case TRUNCATE_EXISTING: oflag |= O_TRUNC; break;
    case OPEN_EXISTING:
    default: break;
    }

    std::string __fn = normPath(fileName);
    int fd = ::open(__fn.c_str(), oflag, 0644);
    if (fd < 0)
    {
        return INVALID_HANDLE_VALUE;
    }
    WinHandle *h = new WinHandle();
    h->fd = fd;
    return reinterpret_cast<HANDLE>(h);
}

int CloseHandle(HANDLE hObject)
{
    if (hObject == INVALID_HANDLE_VALUE || hObject == nullptr)
    {
        return 1;
    }
    WinHandle *h = reinterpret_cast<WinHandle *>(hObject);
    if (h->fd >= 0)
    {
        ::close(h->fd);
    }
    delete h;
    return 1;
}

int ReadFile(HANDLE hFile, void *buffer, DWORD numberOfBytesToRead,
             DWORD *numberOfBytesRead, void * /*overlapped*/)
{
    if (hFile == INVALID_HANDLE_VALUE || hFile == nullptr) return 0;
    WinHandle *h = reinterpret_cast<WinHandle *>(hFile);
    ssize_t r = ::read(h->fd, buffer, numberOfBytesToRead);
    if (r < 0)
    {
        if (numberOfBytesRead) *numberOfBytesRead = 0;
        return 0;
    }
    if (numberOfBytesRead) *numberOfBytesRead = (DWORD)r;
    return 1;
}

int WriteFile(HANDLE hFile, const void *buffer, DWORD numberOfBytesToWrite,
              DWORD *numberOfBytesWritten, void * /*overlapped*/)
{
    if (hFile == INVALID_HANDLE_VALUE || hFile == nullptr) return 0;
    WinHandle *h = reinterpret_cast<WinHandle *>(hFile);
    ssize_t w = ::write(h->fd, buffer, numberOfBytesToWrite);
    if (w < 0)
    {
        if (numberOfBytesWritten) *numberOfBytesWritten = 0;
        return 0;
    }
    if (numberOfBytesWritten) *numberOfBytesWritten = (DWORD)w;
    return 1;
}

DWORD GetFileSize(HANDLE hFile, DWORD *fileSizeHigh)
{
    if (hFile == INVALID_HANDLE_VALUE || hFile == nullptr) return INVALID_FILE_SIZE;
    WinHandle *h = reinterpret_cast<WinHandle *>(hFile);
    struct stat st;
    if (::fstat(h->fd, &st) != 0) return INVALID_FILE_SIZE;
    if (fileSizeHigh) *fileSizeHigh = (DWORD)((uint64_t)st.st_size >> 32);
    return (DWORD)((uint64_t)st.st_size & 0xffffffffu);
}

DWORD SetFilePointer(HANDLE hFile, LONG distanceToMove, LONG *distanceToMoveHigh,
                     DWORD moveMethod)
{
    if (hFile == INVALID_HANDLE_VALUE || hFile == nullptr) return INVALID_SET_FILE_POINTER;
    WinHandle *h = reinterpret_cast<WinHandle *>(hFile);
    int whence = SEEK_SET;
    switch (moveMethod)
    {
    case FILE_BEGIN:   whence = SEEK_SET; break;
    case FILE_CURRENT: whence = SEEK_CUR; break;
    case FILE_END:     whence = SEEK_END; break;
    }
    int64_t dist = distanceToMove;
    if (distanceToMoveHigh) dist |= ((int64_t)(*distanceToMoveHigh) << 32);
    off_t pos = ::lseek(h->fd, dist, whence);
    if (pos == (off_t)-1) return INVALID_SET_FILE_POINTER;
    if (distanceToMoveHigh) *distanceToMoveHigh = (LONG)((uint64_t)pos >> 32);
    return (DWORD)((uint64_t)pos & 0xffffffffu);
}

HANDLE CreateFileMappingA(HANDLE hFile, void * /*attrs*/, DWORD /*protect*/,
                          DWORD /*maxSizeHigh*/, DWORD /*maxSizeLow*/, const char * /*name*/)
{
    if (hFile == INVALID_HANDLE_VALUE || hFile == nullptr) return nullptr;
    WinHandle *src = reinterpret_cast<WinHandle *>(hFile);
    int dup = ::dup(src->fd);
    if (dup < 0) return nullptr;
    WinHandle *h = new WinHandle();
    h->fd = dup;
    return reinterpret_cast<HANDLE>(h);
}

void *MapViewOfFile(HANDLE hFileMappingObject, DWORD /*desiredAccess*/,
                    DWORD /*fileOffsetHigh*/, DWORD /*fileOffsetLow*/, SIZE_T numberOfBytesToMap)
{
    if (hFileMappingObject == INVALID_HANDLE_VALUE || hFileMappingObject == nullptr) return nullptr;
    WinHandle *h = reinterpret_cast<WinHandle *>(hFileMappingObject);
    size_t length = numberOfBytesToMap;
    if (length == 0)
    {
        struct stat st;
        if (::fstat(h->fd, &st) != 0) return nullptr;
        length = (size_t)st.st_size;
    }
    if (length == 0) return nullptr;
    void *p = ::mmap(nullptr, length, PROT_READ, MAP_PRIVATE, h->fd, 0);
    if (p == MAP_FAILED) return nullptr;
    std::lock_guard<std::mutex> lock(g_mapMutex);
    g_mappings[p] = length;
    return p;
}

int UnmapViewOfFile(const void *baseAddress)
{
    if (!baseAddress) return 0;
    size_t length = 0;
    {
        std::lock_guard<std::mutex> lock(g_mapMutex);
        auto it = g_mappings.find(baseAddress);
        if (it == g_mappings.end()) return 0;
        length = it->second;
        g_mappings.erase(it);
    }
    ::munmap(const_cast<void *>(baseAddress), length);
    return 1;
}

int StrToInt(const char *psz)
{
    if (!psz) return 0;
    return (int)strtol(psz, nullptr, 10);
}

// Public wrapper so header-only code (CCrystalTextBuffer) can resolve paths too.
std::string ResolveCasePath(const char *p) { return normPath(p); }

int PathFileExistsA(const char *path)
{
    if (!path) return 0;
    std::string __p = normPath(path);
    return ::access(__p.c_str(), F_OK) == 0 ? 1 : 0;
}

const char *StrChrA(const char *psz, char ch)
{
    return psz ? strchr(psz, (unsigned char)ch) : nullptr;
}

const char *PathFindFileNameA(const char *path)
{
    if (!path) return path;
    const char *last = path;
    for (const char *p = path; *p; ++p)
    {
        if (*p == '/' || *p == '\\') last = p + 1;
    }
    return last;
}

int PathMatchSpecA(const char *file, const char *spec)
{
    if (!file || !spec) return 0;
    return fnmatch(spec, file, FNM_CASEFOLD) == 0 ? 1 : 0;
}

const char *PathFindExtensionA(const char *path)
{
    if (!path) return path;
    const char *name = PathFindFileNameA(path);
    const char *dot = nullptr;
    for (const char *p = name; *p; ++p)
    {
        if (*p == '.') dot = p;
    }
    // Win32 returns a pointer to the terminating NUL when there is no extension.
    if (dot) return dot;
    while (*name) ++name;
    return name;
}

// Reverse, case-insensitive substring search (shlwapi StrRStrI). pszLast bounds
// the search (nullptr => whole string). Returns the last match, or nullptr.
const char *StrRStrIA(const char *pszSource, const char *pszLast, const char *pszSrch)
{
    if (!pszSource || !pszSrch || !*pszSrch) return nullptr;
    size_t end = pszLast ? (size_t)(pszLast - pszSource) : strlen(pszSource);
    size_t sl = strlen(pszSrch);
    if (sl > end) return nullptr;
    for (size_t i = end - sl + 1; i-- > 0;)
    {
        if (strncasecmp(pszSource + i, pszSrch, sl) == 0)
        {
            return pszSource + i;
        }
        if (i == 0) break;
    }
    return nullptr;
}

static void UnixTimeToFileTime(time_t t, FILETIME *ft)
{
    // FILETIME: 100ns intervals since 1601-01-01. Offset to Unix epoch (1970).
    uint64_t v = ((uint64_t)t * 10000000ull) + 116444736000000000ull;
    ft->dwLowDateTime = (DWORD)(v & 0xffffffffu);
    ft->dwHighDateTime = (DWORD)(v >> 32);
}

int GetFileTime(HANDLE hFile, FILETIME *creation, FILETIME *lastAccess, FILETIME *lastWrite)
{
    if (hFile == INVALID_HANDLE_VALUE || hFile == nullptr) return 0;
    WinHandle *h = reinterpret_cast<WinHandle *>(hFile);
    struct stat st;
    if (::fstat(h->fd, &st) != 0) return 0;
    if (creation)   UnixTimeToFileTime(st.st_ctime, creation);
    if (lastAccess) UnixTimeToFileTime(st.st_atime, lastAccess);
    if (lastWrite)  UnixTimeToFileTime(st.st_mtime, lastWrite);
    return 1;
}

LONG CompareFileTime(const FILETIME *a, const FILETIME *b)
{
    uint64_t va = a ? (((uint64_t)a->dwHighDateTime << 32) | a->dwLowDateTime) : 0;
    uint64_t vb = b ? (((uint64_t)b->dwHighDateTime << 32) | b->dwLowDateTime) : 0;
    return (va < vb) ? -1 : (va > vb) ? 1 : 0;
}

int CreateDirectoryA(const char *path, void *)
{
    if (!path) return 0;
    std::string __p = normPath(path);
    return ::mkdir(__p.c_str(), 0755) == 0 ? 1 : 0;   // 0 (with errno==EEXIST) mirrors Win32 failure-if-exists
}

int DeleteFileA(const char *path)
{
    if (!path) return 0;
    std::string __p = normPath(path);
    return ::unlink(__p.c_str()) == 0 ? 1 : 0;
}

int MoveFileA(const char *from, const char *to)
{
    if (!from || !to) return 0;
    std::string __f = normPath(from), __t = normPath(to);
    return ::rename(__f.c_str(), __t.c_str()) == 0 ? 1 : 0;
}

int CopyFileA(const char *from, const char *to, int failIfExists)
{
    if (!from || !to) return 0;
    int in = ::open(from, O_RDONLY);
    if (in < 0) return 0;
    int flags = O_WRONLY | O_CREAT | O_TRUNC | (failIfExists ? O_EXCL : 0);
    int out = ::open(to, flags, 0644);
    if (out < 0) { ::close(in); return 0; }
    char buf[65536];
    ssize_t r;
    int ok = 1;
    while ((r = ::read(in, buf, sizeof(buf))) > 0)
    {
        if (::write(out, buf, r) != r) { ok = 0; break; }
    }
    if (r < 0) ok = 0;
    ::close(in);
    ::close(out);
    return ok;
}

DWORD GetTempPathA(DWORD bufferLength, char *buffer)
{
    const char *tmp = getenv("TMPDIR");
    if (!tmp || !*tmp) tmp = "/tmp/";
    size_t n = strlen(tmp);
    bool needSlash = (n == 0 || tmp[n - 1] != '/');
    size_t total = n + (needSlash ? 1 : 0);
    if (buffer && bufferLength > total)
    {
        memcpy(buffer, tmp, n);
        if (needSlash) buffer[n] = '/';
        buffer[total] = 0;
    }
    return (DWORD)total;
}

DWORD GetModuleFileNameA(HMODULE, char *buffer, DWORD size)
{
    if (!buffer || size == 0) return 0;
    ssize_t n = ::readlink("/proc/self/exe", buffer, size - 1);
    if (n < 0) { buffer[0] = 0; return 0; }
    buffer[n] = 0;
    return (DWORD)n;
}

DWORD FormatMessageA(DWORD flags, const void * /*source*/, DWORD messageId,
                     DWORD /*languageId*/, char *buffer, DWORD size, void * /*args*/)
{
    char msg[128];
    int n = snprintf(msg, sizeof(msg), "system error %u", (unsigned)messageId);
    if (n < 0) { n = 0; msg[0] = 0; }
    if (flags & FORMAT_MESSAGE_ALLOCATE_BUFFER)
    {
        // buffer is really char** -- allocate and store the pointer.
        char **out = reinterpret_cast<char **>(buffer);
        char *p = (char *)malloc(n + 1);
        if (!p) { if (out) *out = nullptr; return 0; }
        memcpy(p, msg, n + 1);
        if (out) *out = p;
        return (DWORD)n;
    }
    if (!buffer || size == 0) return 0;
    strncpy(buffer, msg, size);
    buffer[size - 1] = 0;
    return (DWORD)((size_t)n < size ? n : size - 1);
}

UINT GetTempFileNameA(const char *pathName, const char *prefix, UINT unique, char *tempFileName)
{
    if (!tempFileName) return 0;
    std::string dir = pathName ? pathName : "/tmp";
    if (!dir.empty() && dir.back() != '/') dir += '/';
    std::string pfx = prefix ? prefix : "tmp";
    UINT u = unique ? unique : (UINT)(::getpid());
    snprintf(tempFileName, MAX_PATH, "%s%.3s%04x.tmp", dir.c_str(), pfx.c_str(), u & 0xffff);
    return u;
}

namespace
{
    std::string ini_trim(const std::string &s)
    {
        size_t a = s.find_first_not_of(" \t\r\n");
        size_t b = s.find_last_not_of(" \t\r\n");
        return (a == std::string::npos) ? std::string() : s.substr(a, b - a + 1);
    }
}

DWORD GetPrivateProfileStringA(const char *section, const char *key, const char *def,
                               char *buffer, DWORD size, const char *fileName)
{
    std::string result = def ? def : "";
    if (section && key && fileName)
    {
        std::ifstream f(normPath(fileName));
        std::string line, cur;
        bool inSection = false, found = false;
        while (!found && std::getline(f, line))
        {
            std::string t = ini_trim(line);
            if (t.empty() || t[0] == ';' || t[0] == '#') continue;
            if (t.front() == '[' && t.back() == ']')
            {
                cur = ini_trim(t.substr(1, t.size() - 2));
                inSection = (strcasecmp(cur.c_str(), section) == 0);
                continue;
            }
            if (!inSection) continue;
            size_t eq = t.find('=');
            if (eq == std::string::npos) continue;
            std::string k = ini_trim(t.substr(0, eq));
            if (strcasecmp(k.c_str(), key) == 0)
            {
                result = ini_trim(t.substr(eq + 1));
                found = true;
            }
        }
    }
    if (!buffer || size == 0) return 0;
    size_t n = result.size();
    if (n >= size) n = size - 1;
    memcpy(buffer, result.data(), n);
    buffer[n] = 0;
    return (DWORD)n;
}

DWORD GetFileAttributesA(const char *fileName)
{
    if (!fileName) return INVALID_FILE_ATTRIBUTES;
    struct stat st;
    std::string __fn = normPath(fileName);
    if (::stat(__fn.c_str(), &st) != 0) return INVALID_FILE_ATTRIBUTES;
    DWORD attrs = 0;
    if (S_ISDIR(st.st_mode)) attrs |= FILE_ATTRIBUTE_DIRECTORY;
    if ((st.st_mode & S_IWUSR) == 0) attrs |= FILE_ATTRIBUTE_READONLY;
    return attrs ? attrs : 0x80u /* FILE_ATTRIBUTE_NORMAL */;
}

DWORD GetPrivateProfileSectionA(const char *section, char *buffer, DWORD size, const char *fileName)
{
    // Returns key=value\0key=value\0\0 for the section (used to test existence).
    std::string out;
    if (section && fileName)
    {
        std::ifstream f(normPath(fileName));
        std::string line, cur;
        bool inSection = false;
        while (std::getline(f, line))
        {
            std::string t = ini_trim(line);
            if (t.empty() || t[0] == ';' || t[0] == '#') continue;
            if (t.front() == '[' && t.back() == ']')
            {
                cur = ini_trim(t.substr(1, t.size() - 2));
                inSection = (strcasecmp(cur.c_str(), section) == 0);
                continue;
            }
            if (inSection && t.find('=') != std::string::npos)
            {
                out += t;
                out.push_back('\0');
            }
        }
    }
    out.push_back('\0');
    if (!buffer || size == 0) return 0;
    size_t n = out.size();
    if (n > size) n = size;
    memcpy(buffer, out.data(), n);
    return (DWORD)(n > 0 ? n - 1 : 0);
}

UINT GetPrivateProfileIntA(const char *section, const char *key, int def, const char *fileName)
{
    char buf[64];
    if (GetPrivateProfileStringA(section, key, "", buf, sizeof(buf), fileName) > 0)
    {
        return (UINT)strtol(buf, nullptr, 10);
    }
    return (UINT)def;
}

int WritePrivateProfileStringA(const char * /*section*/, const char * /*key*/,
                               const char * /*value*/, const char * /*fileName*/)
{
    // Writing game settings is not part of the headless compile path.
    return 1;
}

int StringCchPrintfA(char *dest, size_t destSize, const char *format, ...)
{
    if (!dest || destSize == 0) return (int)E_INVALIDARG;
    va_list args;
    va_start(args, format);
    vsnprintf(dest, destSize, format, args);
    va_end(args);
    return (int)S_OK;
}

int StringCchVPrintfA(char *dest, size_t destSize, const char *format, va_list args)
{
    if (!dest || destSize == 0) return (int)E_INVALIDARG;
    vsnprintf(dest, destSize, format, args);
    return (int)S_OK;
}

int StringCchCopyA(char *dest, size_t destSize, const char *src)
{
    if (!dest || destSize == 0) return (int)E_INVALIDARG;
    if (!src) src = "";
    strncpy(dest, src, destSize);
    dest[destSize - 1] = 0;
    return (int)S_OK;
}

int StringCchCatA(char *dest, size_t destSize, const char *src)
{
    if (!dest || destSize == 0) return (int)E_INVALIDARG;
    if (!src) src = "";
    size_t dl = strnlen(dest, destSize);
    if (dl >= destSize) return (int)E_INVALIDARG;
    strncat(dest, src, destSize - dl - 1);
    return (int)S_OK;
}

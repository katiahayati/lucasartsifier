// Minimal MFC / pre-standard-namespace shims. These satisfy the handful of GUI /
// legacy-namespace references that live inside otherwise-core Util files
// (e.g. util.cpp's ShowFile). NONE of these are exercised on the compile path.
#pragma once
#include "winshim.h"

// Pre-standard MSVC filesystem TS namespace. util.cpp only names it; the audio
// cache source uses path/exists, so provide minimal POSIX-backed equivalents.
namespace std { namespace tr2 { namespace sys {
    class path
    {
    public:
        path() {}
        path(const std::string &s) : _p(s) {}
        path(const char *s) : _p(s ? s : "") {}
        const std::string &string() const { return _p; }
        const char *c_str() const { return _p.c_str(); }
        std::string _p;
    };
    inline bool exists(const path &p) { return PathFileExistsA(p.c_str()) != 0; }
} } }

// MSVC hash-container namespace: `using namespace stdext;` with no qualified use.
namespace stdext {}

class CDC;
class CBitmap;
class CMenu;

// Window-message constants + MSG/CEdit used by util.cpp's HandleEditBoxCommands
// (a GUI helper -- compiled but never called headless).
#define WM_KEYFIRST 0x0100
#define WM_KEYDOWN  0x0100
#define WM_KEYUP    0x0101
#define WM_CHAR     0x0102
#define WM_KEYLAST  0x0109
#define VK_DELETE   0x2E
#define VK_C        0x43
#define VK_V        0x56
#define VK_X        0x58
#define VK_INSERT   0x2D
#define VK_CONTROL  0x11
#define VK_SHIFT    0x10

struct MSG
{
    HWND     hwnd;
    UINT     message;
    UINT_PTR wParam;
    LONG_PTR lParam;
    DWORD    time;
    POINT    pt;
};

// Just enough CWnd for `AfxGetMainWnd()->GetSafeHwnd()` to compile & no-op.
class CWnd
{
public:
    HWND GetSafeHwnd() const { return nullptr; }
    HWND m_hWnd = nullptr;
};
inline CWnd *AfxGetMainWnd() { static CWnd w; return &w; }

class CEdit : public CWnd
{
public:
    void Copy() {}
    void Paste() {}
    void Cut() {}
    void Clear() {}
    void Undo() {}
    void SetSel(DWORD) {}
    void SetSel(int, int) {}
};

// Minimal stand-in for the Crystal Edit text buffer (a GUI editor component in
// the real SCICompanion). The compiler only needs to read a source file line by
// line; ReadOnlyTextBuffer (Src/Util/CrystalScriptStream.cpp) consumes exactly
// GetLineCount / GetLineLength / GetLineChars, and the compile driver calls
// LoadFromFile / FreeAll. Backed by a std::vector<std::string> of lines.
#pragma once

#include <string>
#include <vector>
#include <fstream>
#include <sys/stat.h>

class CCrystalTextBuffer
{
public:
    CCrystalTextBuffer() = default;

    // Loads the whole file, splitting on '\n' and stripping a trailing '\r'.
    // The stored lines do NOT include the newline terminator, matching how the
    // real editor buffer exposes line content (GetMoreData synthesizes '\n').
    bool LoadFromFile(const char* pszPath)
    {
        FreeAll();
        // Normalize '\'->'/' and resolve real case (Linux case-sensitivity).
        std::string __path = ResolveCasePath(pszPath);
        // Only open regular files. An unresolved include yields "" -> "\" -> "/",
        // which on Linux would open a directory and throw from filebuf::underflow.
        struct stat __st;
        if (__path.empty() || ::stat(__path.c_str(), &__st) != 0 || !S_ISREG(__st.st_mode))
        {
            return false;
        }
        std::ifstream file(__path.c_str(), std::ios::in | std::ios::binary);
        if (!file.is_open())
        {
            return false;
        }
        std::string content((std::istreambuf_iterator<char>(file)),
                            std::istreambuf_iterator<char>());
        file.close();

        size_t start = 0;
        while (start <= content.size())
        {
            size_t nl = content.find('\n', start);
            if (nl == std::string::npos)
            {
                std::string line = content.substr(start);
                if (!line.empty() && line.back() == '\r') line.pop_back();
                // Only push a trailing empty line if the file did not end in '\n'.
                if (!(line.empty() && start == content.size() && !content.empty()))
                {
                    _lines.push_back(std::move(line));
                }
                break;
            }
            std::string line = content.substr(start, nl - start);
            if (!line.empty() && line.back() == '\r') line.pop_back();
            _lines.push_back(std::move(line));
            start = nl + 1;
        }
        if (_lines.empty())
        {
            _lines.emplace_back();
        }
        return true;
    }

    void FreeAll() { _lines.clear(); }

    int GetLineCount() const { return (int)_lines.size(); }

    int GetLineLength(int nLine) const
    {
        if (nLine < 0 || nLine >= (int)_lines.size()) return 0;
        return (int)_lines[nLine].size();
    }

    // Returns a NUL-terminated pointer into the stored line. The parser reads
    // GetLineLength() chars, but we keep it NUL-terminated to be safe.
    PCTSTR GetLineChars(int nLine) const
    {
        if (nLine < 0 || nLine >= (int)_lines.size()) return "";
        return _lines[nLine].c_str();
    }

    // {lastLineLength, lineCount - 1}; matches GetNaturalLimit() usage.
    CPoint GetLimit() const
    {
        CPoint limit;
        limit.y = GetLineCount() - 1;
        if (limit.y >= 0)
        {
            limit.x = GetLineLength(limit.y);
        }
        return limit;
    }

    // Referenced by CScriptStreamLimiter::Extend only in the autocomplete path;
    // never exercised during batch compilation. No-op.
    void Extend(const std::string&) {}

    // Extract text between two points (used only by CodeAutoComplete; not on the
    // compile path). Faithful line/char extraction over the stored lines.
    void GetText(int nStartLine, int nStartChar, int nEndLine, int nEndChar, CString& text)
    {
        text._s.clear();
        for (int line = nStartLine; line <= nEndLine && line < (int)_lines.size(); ++line)
        {
            if (line < 0) continue;
            const std::string& s = _lines[line];
            int from = (line == nStartLine) ? nStartChar : 0;
            int to = (line == nEndLine) ? nEndChar : (int)s.size();
            if (from < 0) from = 0;
            if (to > (int)s.size()) to = (int)s.size();
            if (to > from) text._s.append(s, from, to - from);
            if (line != nEndLine) text._s.push_back('\n');
        }
    }

private:
    std::vector<std::string> _lines;
};

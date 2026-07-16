#pragma once
// Headless stub: ResourceMap.cpp's AppendResourceAskForNumber uses this dialog,
// but the headless compiler only calls AppendResource(...) directly. DoModal()
// returns IDCANCEL so that code path is inert.
#include <string>
enum class ResourceType;
class CWnd;
class SaveResourceDialog
{
public:
    SaveResourceDialog(bool /*warnOnOverwrite*/, ResourceType /*type*/, CWnd * /*parent*/ = nullptr) {}
    void Init(int, int, const std::string & = std::string()) {}
    int  DoModal() { return 2; /* IDCANCEL */ }
    int  GetResourceNumber() { return 0; }
    int  GetPackageNumber() { return 0; }
    std::string GetName() { return std::string(); }
};

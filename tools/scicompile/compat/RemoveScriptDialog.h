#pragma once
// Headless stub (ResourceMapOperations.cpp DeleteResource path; not compile-path).
class CRemoveScriptDialog
{
public:
    CRemoveScriptDialog(unsigned short = 0) {}
    int  DoModal() { return 2; /* IDCANCEL */ }
    bool AlsoDelete() { return false; }
};

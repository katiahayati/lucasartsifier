// Headless stand-in for SCICompanion's AppState (the real one drags in the whole
// MFC GUI: document templates, intellisense list box, tool tips, run/debug logic).
// The compiler subsystem only reaches AppState through the global `appState`
// pointer for six things: the resource map, the SCI version, the class browser,
// the dependency tracker, info logging, and the "browse info enabled" flag.
//
// This class is backed by REAL CResourceMap + SCIClassBrowser + DependencyTracker
// objects -- nothing about selector/class/bytecode resolution is faked here.
#pragma once

#include "ResourceMap.h"        // CResourceMap, ISCIAppServices
#include "ResourceRecency.h"    // ResourceRecency
#include "ClassBrowser.h"       // SCIClassBrowser
#include "DependencyTracker.h"  // DependencyTracker
#include "Version.h"            // SCIVersion
#include <memory>
#include <cstdarg>
#include <cstdio>

class AppState : public ISCIAppServices
{
public:
    AppState();
    ~AppState();

    CResourceMap &GetResourceMap() { return *_resourceMap; }
    const SCIVersion &GetVersion() const { return _resourceMap->GetSCIVersion(); }
    SCIClassBrowser &GetClassBrowser() { return *_classBrowser; }
    DependencyTracker &GetDependencyTracker() { return *_dependencyTracker; }

    // MUST be true: SCIClassBrowser::ReLoadFromSources() and OnOpenGame() no-op
    // when this is false, which would leave classes/selectors/globals unresolved
    // and produce incorrect bytecode. This is the headless equivalent of the GUI
    // option "Enable browse info", which the compile path depends on.
    bool IsBrowseInfoEnabled() { return true; }

    void LogInfo(const TCHAR *pszFormat, ...);

    // ISCIAppServices -- headless: nothing to notify.
    void OnGameFolderUpdate() override {}
    void SetRecentlyInteractedView(int) override {}

private:
    ResourceRecency _resourceRecency;
    std::unique_ptr<DependencyTracker> _dependencyTracker;
    std::unique_ptr<CResourceMap> _resourceMap;
    std::unique_ptr<SCIClassBrowser> _classBrowser;
};

extern AppState *appState;

#include "stdafx.h"
#include "AppState.h"

// The single global instance the entire compiler subsystem talks to.
AppState *appState = nullptr;

AppState::AppState()
{
    // Order matters: the class browser needs the dependency tracker; the resource
    // map needs this object (as ISCIAppServices) and the recency tracker.
    _dependencyTracker = std::make_unique<DependencyTracker>(FALSE /*fTrackHeaderFiles*/);
    _resourceMap = std::make_unique<CResourceMap>(this, &_resourceRecency);
    _classBrowser = std::make_unique<SCIClassBrowser>(*_dependencyTracker);
}

AppState::~AppState()
{
    // Tear down the class browser first: it owns a background scheduler thread
    // that must be joined before the objects it references disappear.
    if (_classBrowser)
    {
        _classBrowser->ExitSchedulerAndReset();
    }
    _classBrowser.reset();
    _resourceMap.reset();
    _dependencyTracker.reset();
}

void AppState::LogInfo(const TCHAR *pszFormat, ...)
{
    va_list args;
    va_start(args, pszFormat);
    vfprintf(stderr, pszFormat, args);
    va_end(args);
    fputc('\n', stderr);
}

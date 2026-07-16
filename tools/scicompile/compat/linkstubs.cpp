// Link stubs for symbols whose defining vendor file is NOT compiled headless.
// SniffSCIVersion lives in VersionDetectionHelper.cpp (heavy resource enumeration,
// many MSVC rvalue-binding sites). The headless driver skips version sniffing and
// pins the SCI version explicitly (SkipNextVersionSniff + SetVersion), so this is
// never actually invoked.
#include "stdafx.h"
#include "GameFolderHelper.h"

void SniffSCIVersion(GameFolderHelper &helper)
{
    // No-op: version is set explicitly by the compile driver.
    (void)helper;
}

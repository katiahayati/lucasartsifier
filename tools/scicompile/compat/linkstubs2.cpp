// Link stubs for resource-type creators, audio/wave helpers, palette/raster ops,
// and debug/post-build threads. NONE of these are exercised when compiling a
// script: only the Script bytecode (generated directly) and the Text resource
// (real, from Text.cpp) are produced. They are referenced by the resource-entity
// factory switch and resource-map bookkeeping, so the symbols must exist to link.
// Each returns an empty/nullptr result; the corresponding vendor files pull in the
// heavy GDI+/graphics/audio-processing machinery we intentionally do not compile.
#include "stdafx.h"
#include "ResourceEntity.h"
#include "Audio.h"
#include "AudioMap.h"
#include "AudioProcessingSettings.h"
#include "PaletteOperations.h"
#include "ResourceSources.h"
#include "PatchResourceSource.h"
#include "GameFolderHelper.h"
#include "DebuggerThread.h"
#include "PostBuildThread.h"
#include "SCO.h"
#include "ScriptOM.h"
#include "ScriptOMAll.h"
#include "CompileInterfaces.h"
#include "CompileContext.h"
#include <memory>
#include <string>
#include <vector>

// ---- Resource-type entity creators (return nullptr; not created during compile) ----
ResourceEntity *CreateViewResource(SCIVersion) { return nullptr; }
ResourceEntity *CreatePicResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateFontResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateSoundResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateCursorResource(SCIVersion) { return nullptr; }
ResourceEntity *CreatePaletteResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateMessageResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateAudioResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateMapResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateWaveAudioResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateDefaultViewResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateDefaultPicResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateDefaultFontResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateDefaultSoundResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateDefaultCursorResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateDefaultMessageResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateDefaultAudioResource(SCIVersion) { return nullptr; }
ResourceEntity *CreateDefaultMapResource(SCIVersion, int) { return nullptr; }

// ---- Global tables declared extern in sci.h; defined in graphics/GUI .cpp we
// don't compile. Not used to generate bytecode -- benign defaults. ----
RGBQUAD  g_egaColors[16] = {};
COLORREF g_egaColorsCR[16] = {};
const TCHAR *g_szResourceSpecByType[(int)ResourceType::Max] =
{ "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "" };

// startsWith: declared (non-inline) in StringUtil.h, defined in a GUI .cpp.
bool startsWith(const std::string &text, const std::string &prefix)
{
    return text.size() >= prefix.size() && text.compare(0, prefix.size(), prefix) == 0;
}

// ---- Audio / wave helpers (audio never touched during script compile) ----
extern const int MaxSierraSampleRate = 44100;
AudioVolumeName GetVolumeToUse(SCIVersion, uint32_t) { return AudioVolumeName::None; }
bool IsMainAudioMap(AudioMapVersion) { return false; }
std::string GetAudioVolumePath(const std::string &, bool, AudioVolumeName, ResourceSourceFlags *) { return std::string(); }
uint32_t GetWaveFileSizeIncludingHeader(sci::istream &) { return 0; }
void AudioComponentFromWaveFile(sci::istream &, AudioComponent &, AudioProcessingSettings *, int, bool) {}
void WriteWaveFile(const std::string &, const AudioComponent &, const AudioProcessingSettings *) {}

// ---- Message helpers (faithful; message resources absent in source-only projects) ----
bool IsLineEmpty(const std::string &line)
{
    return line.find_first_not_of(" \t\r\n") == std::string::npos;
}
std::vector<std::string> Lineify(const std::string &in)
{
    std::vector<std::string> lines;
    size_t start = 0;
    while (start <= in.size())
    {
        size_t nl = in.find('\n', start);
        if (nl == std::string::npos) { lines.push_back(in.substr(start)); break; }
        std::string line = in.substr(start, nl - start);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        lines.push_back(line);
        start = nl + 1;
    }
    return lines;
}

// ---- Palette / raster ops (graphics; not used to generate bytecode) ----
RGBQUAD _Combine(RGBQUAD color1, RGBQUAD) { return color1; }
void CreateDegenerate(Cel &, uint8_t) {}
PaletteComponent::PaletteComponent() {}
void PaletteComponent::MergeFromOther(const PaletteComponent *) {}

// ---- Debug / post-build threads (headless: never launched) ----
void DebuggerThread::Abort() {}
void PostBuildThread::Abort() {}
std::shared_ptr<DebuggerThread> CreateDebuggerThread(const std::string &, int) { return nullptr; }
std::shared_ptr<PostBuildThread> CreatePostBuildThread(const std::string &) { return nullptr; }

// ---- Misc symbols defined only in MFC/GUI files ----
// ResourceNumberFromFileName: extract the trailing decimal from a resource file name.
int ResourceNumberFromFileName(const char *pszFileName)
{
    if (!pszFileName) return -1;
    const char *p = pszFileName;
    // Skip to the last run of digits.
    int result = -1;
    for (const char *c = pszFileName; *c; ++c)
    {
        if (*c >= '0' && *c <= '9')
        {
            result = 0;
            const char *d = c;
            while (*d >= '0' && *d <= '9') { result = result * 10 + (*d - '0'); ++d; }
            c = d - 1;
        }
    }
    (void)p;
    return result;
}
// SimpleCompile: a GUI convenience wrapper (compile + report) -- not used headless.
std::unique_ptr<sci::Script> SimpleCompile(CompileLog &, ScriptId &, bool) { return nullptr; }

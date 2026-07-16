// scicompile -- a headless, Linux command-line front-end to SCICompanion's SCI
// script compiler. Replicates NewCompileScript() from
// vendor/.../Src/MFCDocuments/ScriptDocument.cpp using the real compiler,
// class browser, resource map, and SCO subsystems (no GUI, no MFC).
//
//   scicompile <gameProjectDir> <input.sc> <output.bin>   # compile one script
//   scicompile --all <gameProjectDir>                      # Compile All (write .sco)
//
// "Compile All" mirrors CNewCompileDialog::CompileAll: it enumerates every
// script in game.ini's [Script] section (GetAllScripts), compiles each with the
// real GenerateScriptResource, and writes the resulting .sco object file so that
// `(use X)` statements in other scripts resolve (CompileContext::_LoadSCO reads
// X.sco from disk). Because SCI scripts have `use` cycles (e.g. Main<->System),
// a from-empty single pass cannot bootstrap; we iterate to a fixed point, the
// same way SCICompanion always has pre-existing .sco files (the decompiler writes
// them) before a rebuild. Every final .sco is produced by this compiler.
#include "stdafx.h"

#include "AppState.h"
#include "CCrystalTextBuffer.h"
#include "CrystalScriptStream.h"
#include "SyntaxParser.h"
#include "ScriptOM.h"
#include "CompileContext.h"
#include "ClassBrowser.h"
#include "SCO.h"
#include "Version.h"

#include <cstdio>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

namespace
{
    // Synchronous task status: we never run the class-browser reload on a
    // background thread, so it is never aborted.
    struct SyncTaskStatus : ITaskStatus
    {
        bool IsAborted() override { return false; }
    };

    void PrintLog(CompileLog &log)
    {
        for (const CompileResult &r : log.Results())
        {
            const char *kind = r.IsError() ? "error" : (r.IsWarning() ? "warning" : "message");
            if (r.GetLineNumber() > 0)
            {
                fprintf(stderr, "  [%s] line %d: %s\n", kind, r.GetLineNumber(), r.GetMessage().c_str());
            }
            else
            {
                fprintf(stderr, "  [%s] %s\n", kind, r.GetMessage().c_str());
            }
        }
    }

    // First error string in a log, for terse per-script diagnostics.
    std::string FirstError(CompileLog &log)
    {
        for (const CompileResult &r : log.Results())
        {
            if (r.IsError())
            {
                if (r.GetLineNumber() > 0)
                {
                    return "line " + std::to_string(r.GetLineNumber()) + ": " + r.GetMessage();
                }
                return r.GetMessage();
            }
        }
        return "(no error text)";
    }

    // Bring up the headless application state, point the resource map at the
    // game project, and load the class browser from the game's sources. Returns
    // false (and prints a reason) on failure.
    bool BringUpApp(const std::string &gameDir)
    {
        // Build the SCI/Studio parser grammars (g_sci.Load() / g_studio.Load()).
        // Without this, the grammar's match-function pointers are null and any
        // parse dereferences a null callback.
        InitializeSyntaxParsers();

        appState = new AppState();
        CResourceMap &resourceMap = appState->GetResourceMap();

        // Point the resource map at the game project. We skip the version sniff
        // (which relies on compiled resource.map/volume files) and pin version 0.
        resourceMap.SkipNextVersionSniff();
        try
        {
            resourceMap.SetGameFolder(gameDir);
        }
        catch (const std::exception &e)
        {
            fprintf(stderr, "Failed to open game folder '%s': %s\n", gameDir.c_str(), e.what());
            return false;
        }
        resourceMap.SetVersion(sciVersion0);

        SyncTaskStatus status;
        {
            std::vector<ScriptId> diagScripts;
            resourceMap.GetAllScripts(diagScripts);
            fprintf(stderr, "[diag] GetAllScripts -> %zu scripts\n", diagScripts.size());
        }
        bool relSrc = appState->GetClassBrowser().ReLoadFromSources(status);
        fprintf(stderr, "[diag] ReLoadFromSources -> %s; classes known: %zu\n",
                relSrc ? "true" : "false",
                appState->GetClassBrowser().GetAllClasses().size());
        if (!relSrc)
        {
            fprintf(stderr, "Note: ReLoadFromSources reported an issue; trying compiled resources.\n");
            appState->GetClassBrowser().ReLoadFromCompiled(status);
        }
        return true;
    }

    // Read a whole file into a byte vector. Returns false if the file is absent.
    bool ReadFileBytes(const std::string &path, std::vector<BYTE> &out)
    {
        std::ifstream in(path.c_str(), std::ios::in | std::ios::binary);
        if (!in.is_open())
        {
            return false;
        }
        in.seekg(0, std::ios::end);
        std::streamoff len = in.tellg();
        in.seekg(0, std::ios::beg);
        out.resize(len > 0 ? (size_t)len : 0);
        if (len > 0)
        {
            in.read(reinterpret_cast<char *>(out.data()), len);
        }
        return true;
    }

    // Set the script language from its first source line (ScriptId's own
    // detection opens a Windows-'\'-path via a raw ifstream that fails on Linux
    // and defaults to SCI, mis-parsing Studio-syntax scripts).
    void SetLanguageFromBuffer(ScriptId &scriptId, CCrystalTextBuffer &buffer)
    {
        if (buffer.GetLineCount() > 0)
        {
            std::string firstLine(buffer.GetLineChars(0), (size_t)buffer.GetLineLength(0));
            scriptId.SetLanguage(_DetermineLanguage(firstLine));
        }
    }

    // Parse + GenerateScriptResource for one script. Mirrors NewCompileScript,
    // minus the AppendResource step (we never mutate the game's resource.map /
    // volumes; the compiled bytes are consumed by the caller). Returns true iff
    // the script compiled without errors, in which case `results` holds the
    // script resource and the SCO.
    bool CompileScript(ScriptId &scriptId, CompileTables &tables, PrecompiledHeaders &headers,
                       CompileResults &results, CompileLog &log)
    {
        ClassBrowserLock lock(appState->GetClassBrowser());
        lock.Lock();

        CCrystalTextBuffer buffer;
        if (!buffer.LoadFromFile(scriptId.GetFullPath().c_str()))
        {
            log.ReportResult(CompileResult("Unable to load source file: " + scriptId.GetFullPath()));
            log.CalculateErrors();
            return false;
        }
        SetLanguageFromBuffer(scriptId, buffer);

        CScriptStreamLimiter limiter(&buffer);
        CCrystalScriptStream stream(&limiter);
        auto pScript = std::make_unique<sci::Script>(scriptId);

        bool ok = false;
        if (SyntaxParser_Parse(*pScript, stream,
                               PreProcessorDefinesFromSCIVersion(appState->GetVersion()), &log))
        {
            if (GenerateScriptResource(appState->GetVersion(), *pScript, headers, tables, results, false))
            {
                ok = true;
            }
        }
        log.CalculateErrors();
        buffer.FreeAll();
        // Even if GenerateScriptResource returned true, a reported error (e.g. a
        // missing `use` .sco) means the output is not trustworthy.
        return ok && !log.HasErrors();
    }

    // Save a compiled script's SCO to <gamefolder>/src/<title>.sco, returning
    // whether the on-disk bytes changed (for fixed-point detection).
    bool SaveSCOWithDiff(const GameFolderHelper &helper, ScriptId &scriptId, CompileResults &results)
    {
        std::vector<BYTE> newBytes;
        results.GetSCO().Save(newBytes);
        std::string scoPath = helper.GetScriptObjectFileName(scriptId.GetTitle());

        std::vector<BYTE> oldBytes;
        bool existed = ReadFileBytes(scoPath, oldBytes);
        bool changed = !existed || (oldBytes != newBytes);
        if (changed)
        {
            std::ofstream out(scoPath.c_str(), std::ios::out | std::ios::binary);
            if (!newBytes.empty())
            {
                out.write(reinterpret_cast<const char *>(newBytes.data()), (std::streamsize)newBytes.size());
            }
        }
        return changed;
    }

    int RunCompileAll(const std::string &gameDir)
    {
        if (!BringUpApp(gameDir))
        {
            return 1;
        }

        CResourceMap &resourceMap = appState->GetResourceMap();
        const GameFolderHelper &helper = resourceMap.Helper();

        // Shared across all scripts and passes, exactly as CNewCompileDialog does.
        CompileTables tables;
        tables.Load(appState->GetVersion());
        PrecompiledHeaders headers(resourceMap);

        std::vector<ScriptId> scripts;
        resourceMap.GetAllScripts(scripts);
        fprintf(stderr, "Compile All: %zu script entries in game.ini [Script]\n", scripts.size());

        // Filter out entries whose source file is absent (stale game.ini entries
        // like vAuthors/vBEChagrin that name non-script resources).
        std::vector<ScriptId> haveSource;
        std::vector<std::string> missingSource;
        for (ScriptId &s : scripts)
        {
            std::ifstream probe(s.GetFullPath().c_str());
            if (probe.is_open())
            {
                haveSource.push_back(s);
            }
            else
            {
                missingSource.push_back(s.GetTitle());
            }
        }
        fprintf(stderr, "  %zu have source, %zu game.ini entries without a .sc file\n",
                haveSource.size(), missingSource.size());

        const int kMaxPasses = 16;
        std::vector<std::string> lastErrors(haveSource.size());
        std::vector<bool> compiled(haveSource.size(), false);
        int pass = 0;
        for (; pass < kMaxPasses; ++pass)
        {
            int changedCount = 0;
            int okCount = 0;
            int failCount = 0;
            for (size_t i = 0; i < haveSource.size(); ++i)
            {
                CompileLog log;
                CompileResults results(log);
                bool ok = false;
                try
                {
                    ok = CompileScript(haveSource[i], tables, headers, results, log);
                }
                catch (const std::exception &e)
                {
                    lastErrors[i] = std::string("exception: ") + e.what();
                    compiled[i] = false;
                    failCount++;
                    continue;
                }
                if (ok)
                {
                    if (SaveSCOWithDiff(helper, haveSource[i], results))
                    {
                        changedCount++;
                    }
                    compiled[i] = true;
                    lastErrors[i].clear();
                    okCount++;
                }
                else
                {
                    compiled[i] = false;
                    lastErrors[i] = FirstError(log);
                    failCount++;
                }
            }
            fprintf(stderr, "  pass %d: ok=%d fail=%d sco-changed=%d\n",
                    pass + 1, okCount, failCount, changedCount);
            // Fixed point: a full pass where nothing changed and nothing failed.
            if (changedCount == 0 && failCount == 0)
            {
                pass++;
                break;
            }
            // No progress and still failing => give up (report the failures).
            if (changedCount == 0)
            {
                pass++;
                break;
            }
        }

        int okTotal = 0, failTotal = 0;
        for (size_t i = 0; i < haveSource.size(); ++i)
        {
            if (compiled[i]) okTotal++; else failTotal++;
        }
        fprintf(stderr, "\n==== Compile All result: %d/%zu scripts compiled (converged after %d pass(es)) ====\n",
                okTotal, haveSource.size(), pass);
        if (failTotal > 0)
        {
            fprintf(stderr, "Scripts that did NOT compile:\n");
            for (size_t i = 0; i < haveSource.size(); ++i)
            {
                if (!compiled[i])
                {
                    fprintf(stderr, "  %-14s %s\n", haveSource[i].GetTitle().c_str(), lastErrors[i].c_str());
                }
            }
        }
        if (!missingSource.empty())
        {
            fprintf(stderr, "game.ini [Script] entries with no source file (skipped): ");
            for (const std::string &m : missingSource) fprintf(stderr, "%s ", m.c_str());
            fprintf(stderr, "\n");
        }

        delete appState;
        appState = nullptr;
        return failTotal == 0 ? 0 : 1;
    }

    int RunSingle(const std::string &gameDir, const std::string &inputPath, const std::string &outputPath)
    {
        if (!BringUpApp(gameDir))
        {
            return 1;
        }

        bool wroteOutput = false;
        try
        {
            CResourceMap &resourceMap = appState->GetResourceMap();
            const GameFolderHelper &helper = resourceMap.Helper();

            CompileTables tables;
            tables.Load(appState->GetVersion());
            PrecompiledHeaders headers(resourceMap);

            // Use the raw input path (ScriptId::GetFullPath reconstructs a
            // Windows-'\'-separated path from a possibly-'/'-separated argument).
            ScriptId scriptId(inputPath);

            CompileLog log;
            CompileResults results(log);
            bool ok = false;
            {
                ClassBrowserLock lock(appState->GetClassBrowser());
                lock.Lock();

                CCrystalTextBuffer buffer;
                if (!buffer.LoadFromFile(inputPath.c_str()))
                {
                    fprintf(stderr, "Failed to load input script '%s'\n", inputPath.c_str());
                    delete appState; appState = nullptr;
                    return 1;
                }
                SetLanguageFromBuffer(scriptId, buffer);

                CScriptStreamLimiter limiter(&buffer);
                CCrystalScriptStream stream(&limiter);
                auto pScript = std::make_unique<sci::Script>(scriptId);

                if (SyntaxParser_Parse(*pScript, stream,
                                       PreProcessorDefinesFromSCIVersion(appState->GetVersion()), &log))
                {
                    if (GenerateScriptResource(appState->GetVersion(), *pScript, headers, tables, results, false))
                    {
                        std::vector<BYTE> &output = results.GetScriptResource();
                        std::ofstream out(outputPath.c_str(), std::ios::out | std::ios::binary);
                        if (!out.is_open())
                        {
                            fprintf(stderr, "Failed to open output file '%s'\n", outputPath.c_str());
                            delete appState; appState = nullptr;
                            return 1;
                        }
                        if (!output.empty())
                        {
                            out.write(reinterpret_cast<const char *>(output.data()), (std::streamsize)output.size());
                        }
                        out.close();
                        ok = true;
                        wroteOutput = true;
                        fprintf(stderr, "Wrote script resource %d: %zu bytes -> %s\n",
                                (int)results.GetScriptNumber(), output.size(), outputPath.c_str());

                        // Also refresh this script's .sco so a subsequent compile
                        // of a dependent script sees the up-to-date interface.
                        SaveSCOWithDiff(helper, scriptId, results);
                    }
                    else
                    {
                        fprintf(stderr, "Compilation (GenerateScriptResource) failed.\n");
                    }
                }
                else
                {
                    fprintf(stderr, "Parse failed.\n");
                }
            }
            log.CalculateErrors();
            if (log.HasErrors())
            {
                fprintf(stderr, "Compile log (%zu entries):\n", log.Results().size());
                PrintLog(log);
                wroteOutput = ok && wroteOutput;
            }
        }
        catch (const std::exception &e)
        {
            fprintf(stderr, "scicompile: aborted by exception: %s\n", e.what());
            delete appState;
            appState = nullptr;
            return 1;
        }

        delete appState;
        appState = nullptr;
        return wroteOutput ? 0 : 1;
    }
}

int main(int argc, char **argv)
{
    if (argc == 3 && std::string(argv[1]) == "--all")
    {
        return RunCompileAll(argv[2]);
    }
    if (argc == 4)
    {
        return RunSingle(argv[1], argv[2], argv[3]);
    }
    fprintf(stderr,
            "usage:\n"
            "  %s <gameProjectDir> <input.sc> <output.bin>   compile one script\n"
            "  %s --all <gameProjectDir>                      Compile All (write .sco files)\n",
            argv[0], argv[0]);
    return 2;
}

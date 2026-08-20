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
#include "CompiledScript.h"
#include "Version.h"

#include <cstdio>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

// The SCI version to compile for, set by --version on the command line. The caller DERIVES it
// (from the shape of the game's own resource map) and tells us; sniffing it here would be a second
// oracle for something the analysis already knows. Pinning sciVersion0 unconditionally, as this
// tool used to, means an SCI1.1 game's map never parses and every selector comes out unknown.
SCIVersion g_targetVersion = sciVersion0;

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
        // (which relies on compiled resource.map/volume files) and pin the version the caller
        // derived from the map's own shape -- see --version.
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
        resourceMap.SetVersion(g_targetVersion);

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

    // Generate the .sco interface files the way SCICompanion's DECOMPILER does
    // (DecompileScript.cpp: SCOFromScriptAndCompiledScript + SaveSCOFile), pairing each
    // parsed source with the game's compiled script resource.
    //
    // Why this mode has to exist: `(use X)` is resolved by reading X.sco from disk, and
    // every LSL2 script has at least one `use`, so no script compiles standalone and
    // Compile-All cannot bootstrap from an empty project. SCICompanion never notices
    // because its decompiler always wrote the .sco set first. Our decompiler is
    // sci-tools, which does not, so we derive the same files from THE GAME plus OUR
    // decompilation -- no borrowed artifacts from anyone else's source tree.
    int RunGenerateSCO(const std::string &gameDir)
    {
        if (!BringUpApp(gameDir))
        {
            return 1;
        }

        CResourceMap &resourceMap = appState->GetResourceMap();
        const GameFolderHelper &helper = resourceMap.Helper();

        std::vector<ScriptId> scripts;
        resourceMap.GetAllScripts(scripts);
        fprintf(stderr, "Generate SCO: %zu script entries in game.ini [Script]\n", scripts.size());

        int written = 0, noSource = 0, noResource = 0, parseFail = 0;
        for (ScriptId &scriptId : scripts)
        {
            std::ifstream probe(scriptId.GetFullPath().c_str());
            if (!probe.is_open())
            {
                noSource++;                       // stale game.ini row naming a non-script
                continue;
            }
            probe.close();

            // The compiled script for this number, straight from the game's resources.
            // Exports must be loaded: the SCO records them.
            const uint16_t scriptNum = (uint16_t)scriptId.GetResourceNumber();
            CompiledScript compiled(scriptNum, CompiledScriptFlags::None);
            if (!compiled.Load(helper, appState->GetVersion(), scriptNum))
            {
                noResource++;
                continue;
            }

            CompileLog log;
            ClassBrowserLock lock(appState->GetClassBrowser());
            lock.Lock();

            CCrystalTextBuffer buffer;
            if (!buffer.LoadFromFile(scriptId.GetFullPath().c_str()))
            {
                noSource++;
                continue;
            }
            SetLanguageFromBuffer(scriptId, buffer);   // picks SCI vs Studio syntax

            CScriptStreamLimiter limiter(&buffer);
            CCrystalScriptStream stream(&limiter);
            auto pScript = std::make_unique<sci::Script>(scriptId);

            bool parsed = SyntaxParser_Parse(
                *pScript, stream, PreProcessorDefinesFromSCIVersion(appState->GetVersion()), &log);
            log.CalculateErrors();
            if (!parsed)
            {
                parseFail++;
                fprintf(stderr, "  %-14s parse failed: %s\n",
                        scriptId.GetTitle().c_str(), FirstError(log).c_str());
                buffer.FreeAll();
                continue;
            }

            std::unique_ptr<CSCOFile> sco = SCOFromScriptAndCompiledScript(*pScript, compiled);
            SaveSCOFile(helper, *sco);
            written++;
            buffer.FreeAll();
        }

        fprintf(stderr,
                "\n==== Generate SCO: %d written, %d without source, %d without a compiled "
                "resource, %d parse failures ====\n", written, noSource, noResource, parseFail);
        return (written > 0) ? 0 : 1;
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

                        // SCI1.1 splits a script into a SCRIPT and a HEAP resource, and the
                        // interpreter reads objects out of the heap at offsets the new code
                        // assumes. A script patch shipped without its heap is not a partial
                        // patch, it is a crash -- so write both, next to each other.
                        if (appState->GetVersion().SeparateHeapResources)
                        {
                            std::vector<BYTE> &heap = results.GetHeapResource();
                            std::string heapPath = outputPath + ".hep";
                            std::ofstream hout(heapPath.c_str(), std::ios::out | std::ios::binary);
                            if (!hout.is_open())
                            {
                                fprintf(stderr, "Failed to open heap output '%s'\n", heapPath.c_str());
                                delete appState; appState = nullptr;
                                return 1;
                            }
                            if (!heap.empty())
                            {
                                hout.write(reinterpret_cast<const char *>(heap.data()),
                                           (std::streamsize)heap.size());
                            }
                            hout.close();
                            fprintf(stderr, "Wrote heap resource %d: %zu bytes -> %s\n",
                                    (int)results.GetScriptNumber(), heap.size(), heapPath.c_str());
                        }

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
    // --version {sci0|sci1|sci11} anywhere in argv, stripped before the mode dispatch below so
    // every mode accepts it. Default sci0 keeps every existing caller byte-identical.
    //
    // --wide-exports: emit the export table as 32-bit entries (offset word + zero word).
    // SCI1-middle interpreters (lofs-absolute era: KQ5 CD among them) DOUBLE the export index
    // when reading the table -- ScummVM validateExportFunc: `if (exportsAreWide) pubfunct *= 2`
    // -- so a script compiled with a 16-bit table sends every cross-script call to export N
    // through word 2N: garbage. The vendor emitter already supports both widths
    // (GenerateScriptResource.cpp: `IsExportWide ? 4 : 2`); this flag only reaches it. The
    // caller DERIVES it from the stock game's own script 0 (patcher._version_args), same
    // policy as --version.
    bool wideExports = false;
    std::vector<char *> args;
    for (int i = 0; i < argc; ++i)
    {
        std::string a(argv[i]);
        if (a.rfind("--version", 0) == 0)
        {
            std::string v = (a.size() > 9 && a[9] == '=') ? a.substr(10)
                            : (i + 1 < argc ? argv[++i] : std::string());
            if (v == "sci0")        { g_targetVersion = sciVersion0; }
            else if (v == "sci1")   { g_targetVersion = sciVersion1_Late; }
            else if (v == "sci11")  { g_targetVersion = sciVersion1_1; }
            else
            {
                fprintf(stderr, "unknown --version '%s' (want sci0|sci1|sci11)\n", v.c_str());
                return 2;
            }
            continue;
        }
        if (a == "--wide-exports")
        {
            wideExports = true;
            continue;
        }
        args.push_back(argv[i]);
    }
    if (wideExports)
    {
        g_targetVersion.IsExportWide = true;
    }
    argc = (int)args.size();
    argv = args.data();

    if (argc == 3 && std::string(argv[1]) == "--sco")
    {
        return RunGenerateSCO(argv[2]);
    }
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
            "  %s --sco <gameProjectDir>                      Generate .sco from source + game resources\n"
            "  %s --all <gameProjectDir>                      Compile All (write .sco files)\n"
            "\n"
            "  --version {sci0|sci1|sci11}  (default sci0) may precede any of the above; sci11\n"
            "                               also writes <output.bin>.hep, the heap resource\n"
            "  --wide-exports               emit 32-bit export entries (SCI1-middle interpreters\n"
            "                               double the export index; derived from stock script 0)\n",
            argv[0], argv[0], argv[0]);
    return 2;
}

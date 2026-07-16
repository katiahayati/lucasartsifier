cmake_minimum_required(VERSION 3.16)
project(scicompile CXX)

# NOTE on the C++ standard: the vendor code uses std::bind2nd / std::mem_fun /
# std::unary_function (removed in C++17) in several *compiler* translation units
# (CompileContext, GenerateScriptResource, SCO, Compile, Vocab99x, ...). We build
# with gnu++14, which keeps those available and matches the era the code targets.
# No C++17-only features are used by the compile path.
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(V ${CMAKE_CURRENT_SOURCE_DIR}/../../vendor/SCICompanion/SCICompanionLib)

# -fpermissive downgrades the vendor's MSVC-isms (missing 'typename' on dependent
# names, extra qualification on member decls, etc.) to warnings. -w silences the
# large volume of benign warnings during the build. -pthread for the class
# browser's background scheduler (std::thread).
add_compile_options(-fpermissive -w -pthread -O2 -DNDEBUG)

# Include-path ordering. The vendor code uses quote-includes ("foo.h") for its
# own headers, and the compiler normally searches the *current file's* directory
# first -- which would make vendor files pick up the real headers instead of our
# compat shadows (sci.h, Stream.h, ScriptOM.h, CompileContext.h, ParserActions.h,
# CCrystalTextBuffer.h, AppState.h, stdafx.h). The obsolete-but-supported "-I-"
# flag removes the current-directory-first rule and splits the search: dirs
# BEFORE -I- serve quote-includes (compat wins), dirs AFTER serve both quote and
# angle includes (the real vendor tree + bundled libs). This is what lets the
# shadows apply uniformly across every translation unit.
add_compile_options(
    -I${CMAKE_CURRENT_SOURCE_DIR}/compat
    -I-
    -I${V}/Src/Compile
    -I${V}/Src/Util
    -I${V}/Src/Resources
    -I${V}/Src/Dialogs   # SCIProps.h only (property-name #defines; no GUI deps)
    -I${V}/Src/CRC32     # crc.h (resource checksums)
    -I${V}/Src/FrameComponents  # MessageHeaderFile.h / MessageSource.h
    -I${V}/Src/CppFormat
    -I${V}/Src/cpptoml
    # After -I- so ANGLE includes (<pshpack1.h>, <poppack.h>) find our stubs
    # without exposing the quote-include shadows to angle lookups.
    -I${CMAKE_CURRENT_SOURCE_DIR}/compat/sys
)

set(COMPAT_SRC
    ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/compat/AppState.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/compat/winfile.cpp
    # Symbols defined only in MFC .cpp files (ScriptView.cpp / ScriptDocument.cpp),
    # reproduced here (keyword tables copied verbatim; CompileLog re-implemented).
    ${CMAKE_CURRENT_SOURCE_DIR}/compat/keywords_compat.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/compat/compilelog_compat.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/compat/linkstubs.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/compat/linkstubs2.cpp
)

# Four vendor .cpp files use MSVC-only extensions (rvalue bound to non-const ref;
# an ambiguous WORD/SpeciesIndex ?:) that cannot be fixed from a header shadow
# because both caller and callee live in the .cpp. We compile build-time PATCHED
# COPIES (under patched/, minimal mechanical edits) instead. The vendor files are
# never modified. See BUILD_NOTES.md for the exact diffs.
set(PATCHED ${CMAKE_CURRENT_SOURCE_DIR}/patched)

# --- Compiler subsystem (source -> bytecode) -----------------------------
set(COMPILE_SRC
    ${PATCHED}/Compile.cpp            # was Src/Compile/Compile.cpp
    ${PATCHED}/CompileContext.cpp     # was Src/Compile/CompileContext.cpp
    ${V}/Src/Compile/GenerateScriptResource.cpp
    ${PATCHED}/ScriptOM.cpp           # was Src/Compile/ScriptOM.cpp
    ${V}/Src/Compile/ScriptOMTraverse.cpp
    ${PATCHED}/SyntaxParser.cpp       # was Src/Compile/SyntaxParser.cpp
    ${V}/Src/Compile/SCISyntaxParser.cpp
    ${V}/Src/Compile/StudioSyntaxParser.cpp
    ${V}/Src/Compile/ParserCommon.cpp
    ${V}/Src/Compile/ParseAutoCompleteContext.cpp
    ${V}/Src/Compile/OperatorTables.cpp
    ${V}/Src/Compile/OutputCodeHelper.cpp
    ${V}/Src/Compile/OutputScriptStrings.cpp
    ${V}/Src/Compile/Evaluate.cpp
    ${PATCHED}/SCO.cpp                # was Src/Compile/SCO.cpp
    ${V}/Src/Compile/Types.cpp
    ${V}/Src/Compile/ValidateSaid.cpp
    ${PATCHED}/scii.cpp               # was Src/Compile/scii.cpp
    ${V}/Src/Compile/PMachine.cpp
    # --- added to satisfy the linker (compiled-script disassembly + source formatting) ---
    ${PATCHED}/CompiledScript.cpp     # was Src/Compile/CompiledScript.cpp
    ${V}/Src/Compile/SourceCodeFormatter.cpp
    ${PATCHED}/SCISourceCodeFormatter.cpp
    ${V}/Src/Compile/StudioSourceCodeFormatter.cpp
    ${V}/Src/Compile/DisassembleHelper.cpp
    ${V}/Src/Compile/Disassembler.cpp
)

# --- Supporting Util subsystems (compiled for real) ----------------------
set(UTIL_SRC
    ${PATCHED}/ClassBrowser.cpp       # was Src/Util/ClassBrowser.cpp
    ${V}/Src/Util/ClassBrowserInfo.cpp
    ${V}/Src/Util/CrystalScriptStream.cpp
    ${V}/Src/Util/TokenDatabase.cpp
    ${V}/Src/Util/DependencyTracker.cpp
    ${V}/Src/Util/Version.cpp
    ${PATCHED}/util.cpp               # was Src/Util/util.cpp (GetFullPath -> '/')
    ${V}/Src/Util/RunLogic.cpp
    ${V}/Src/Util/TalkerToViewMap.cpp
    ${PATCHED}/Stream.cpp             # was Src/Util/Stream.cpp (empty stream on INVALID handle)
    # --- added to satisfy the linker (autocomplete + resource codecs) ---
    ${V}/Src/Util/CodeAutoComplete.cpp
    ${V}/Src/Util/Codec.cpp
    ${V}/Src/Util/CodecAlt.cpp
    ${V}/Src/Util/CodecDCL.cpp
    ${V}/Src/Util/CodecDecompressor.cpp
    ${V}/Src/Util/CodecSTAC.cpp
)

# --- Resource subsystems (compiled for real) -----------------------------
set(RES_SRC
    ${PATCHED}/ResourceMap.cpp        # was Src/Resources/ResourceMap.cpp
    ${PATCHED}/ResourceBlob.cpp       # was Src/Resources/ResourceBlob.cpp
    ${V}/Src/Resources/ResourceEntity.cpp
    ${V}/Src/Resources/ResourceContainer.cpp
    ${V}/Src/Resources/Components.cpp
    ${PATCHED}/GameFolderHelper.cpp   # was Src/Resources/GameFolderHelper.cpp
    ${PATCHED}/Vocab000.cpp           # was Src/Resources/Vocab000.cpp
    ${PATCHED}/Vocab99x.cpp           # was Src/Resources/Vocab99x.cpp
    ${V}/Src/CRC32/crc.cpp
    ${V}/Src/FrameComponents/MessageHeaderFile.cpp
    ${V}/Src/FrameComponents/MessageSource.cpp
    # --- added to satisfy the linker (resource registry, text resource, enumeration) ---
    ${V}/Src/Resources/ResourceUtil.cpp
    # Real resource-map reader: CreateResourceSource / DeleteResource. Needed to
    # read compiled resources (vocab.997 selectors, vocab.000 parser words, ...)
    # from a game that has a resource.map. ResourceSources.h is shadowed with
    # this-> qualifiers (dependent-base two-phase lookup); the delete-dialog is a stub.
    ${V}/Src/Resources/ResourceMapOperations.cpp
    ${V}/Src/Dialogs/SCIProps.cpp            # IsPseudoProp (pseudo-property resolution)
    ${V}/Src/Resources/Text.cpp
    ${V}/Src/Resources/ResourceRecency.cpp
    # VersionDetectionHelper.cpp dropped -- SniffSCIVersion stubbed in linkstubs.cpp
    # (headless pins the version; the sniff is skipped).
    ${V}/Src/Resources/ResourceSources.cpp
    ${V}/Src/Resources/PatchResourceSource.cpp
    ${PATCHED}/AudioResourceSource.cpp        # was Src/Resources/AudioResourceSource.cpp
    ${PATCHED}/AudioCacheResourceSource.cpp   # was Src/Resources/AudioCacheResourceSource.cpp
)

# --- Bundled fmtlib ------------------------------------------------------
set(FMT_SRC
    ${V}/Src/CppFormat/format.cc
)

add_executable(scicompile
    ${COMPAT_SRC}
    ${COMPILE_SRC}
    ${UTIL_SRC}
    ${RES_SRC}
    ${FMT_SRC}
)

# MSVC's __super keyword names the immediate base class. It is used in exactly
# three compiled translation units, each in one class, so we alias it per-file
# to that class's base (verified from ScriptOM.h / Vocab99x.h).
set_source_files_properties(${PATCHED}/Compile.cpp         PROPERTIES COMPILE_DEFINITIONS "__super=FunctionBase")
set_source_files_properties(${V}/Src/Compile/Evaluate.cpp  PROPERTIES COMPILE_DEFINITIONS "__super=PropertyValueBase")
set_source_files_properties(${PATCHED}/Vocab99x.cpp        PROPERTIES COMPILE_DEFINITIONS "__super=CVocabWithNames")

find_package(Threads REQUIRED)
target_link_libraries(scicompile Threads::Threads)

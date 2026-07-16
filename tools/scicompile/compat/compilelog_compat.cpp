// CompileLog::{HasErrors,CalculateErrors,SummarizeAndReportErrors} are defined in
// the MFC document file (ScriptDocument.cpp) which we do not compile. Faithful
// re-implementations (identical logic; the GUI error-sound is dropped).
#include "stdafx.h"
#include "SCO.h"
#include "ScriptOM.h"
#include "ScriptOMAll.h"
#include "CompileInterfaces.h"
#include "CompileContext.h"
#include <algorithm>
#include <sstream>

bool CompileLog::HasErrors()
{
    return _cErrors > 0;
}

void CompileLog::CalculateErrors()
{
    _cErrors += (int)std::count_if(_compileResults.begin(), _compileResults.end(),
                                   [](const CompileResult &r) { return r.IsError(); });
    _cWarnings += (int)std::count_if(_compileResults.begin(), _compileResults.end(),
                                     [](const CompileResult &r) { return r.IsWarning(); });
}

void CompileLog::SummarizeAndReportErrors()
{
    std::stringstream summaryMessage;
    summaryMessage << _cErrors << " errors, " << _cWarnings << " warnings.";
    ReportResult(CompileResult(summaryMessage.str()));
}

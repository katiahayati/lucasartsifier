// Keyword tables + query functions copied verbatim from Src/MFCViews/ScriptView.cpp
// (lines 353-581). The vendor definitions live in an MFC .cpp we cannot compile;
// these functions (IsSCIKeyword et al, declared in sci.h) are used by the parser.
#include "stdafx.h"
#include <algorithm>
using namespace std;

std::vector<std::string> emptyList;

std::vector<std::string> topLevelKeywordsSCI =
{
    // Keep this alphabetically sorted.
    _T("class"),
    _T("define"),
    _T("enum"),
    _T("extern"),
    _T("include"),
    _T("instance"),
    _T("local"),
    _T("procedure"),
    _T("public"),
    _T("script#"),
    _T("string"),
    _T("synonyms"),
    _T("text#"),
    _T("use"),
};

std::vector<std::string> topLevelKeywordsStudio =
{
    // Keep this alphabetically sorted.
    _T("class"),
    _T("define"),
    _T("exports"),
    _T("include"),
    _T("instance"),
    _T("local"),
    _T("procedure"),
    _T("public"),
    _T("script"),
    _T("string"),
    _T("synonyms"),
    _T("use"),
    _T("version"),
};

bool IsTopLevelKeyword(LangSyntax lang, const std::string &word)
{
    auto &list = GetTopLevelKeywords(lang);
    return binary_search(list.begin(), list.end(), word);
}

const std::vector<std::string> &GetTopLevelKeywords(LangSyntax lang)
{
    switch (lang)
    {
        case LangSyntaxSCI:
            return topLevelKeywordsSCI;
        case LangSyntaxStudio:
            return topLevelKeywordsStudio;
    }
    return emptyList;
}

std::vector<std::string> codeLevelKeywordsSCI =
{
    // Sorted
    _T("&rest"),
    _T("&sizeof"),
    // _T("&tmp"),   // This is special
    _T("and"),
    _T("argc"),
    _T("asm"),
    _T("break"),
    _T("breakif"),
    _T("cond"),
    _T("contif"),
    _T("continue"),
    _T("else"),
    _T("enum"),
    _T("for"),
    _T("if"),
    _T("mod"),
    _T("not"),
    _T("of"),
    _T("or"),
    _T("repeat"),
    _T("return"),
    _T("scriptNumber"),
    _T("self"),
    _T("super"),
    _T("switch"),
    _T("switchto"),
    _T("while"),
};


std::vector<std::string> codeLevelKeywordsStudio =
{ 
    // Sorted
    _T("and"),
    _T("asm"),
	_T("break"),
    _T("case"),
    _T("default"),
    _T("do"),
    _T("else"),
    _T("for"),
    _T("if"),
    _T("neg"),
    _T("not"),
    _T("of"),
    _T("or"),
    _T("rest"),
    _T("return"),
    _T("scriptNumber"),
    _T("self"),
    _T("send"),
    _T("super"),
    _T("switch"),
    _T("var"),
	_T("while"),
    _T("paramTotal")
};

bool IsCodeLevelKeyword(LangSyntax lang, const std::string &word)
{
    auto &list = GetCodeLevelKeywords(lang);
    return binary_search(list.begin(), list.end(), word);
}

// Keep in alphabetical order
std::vector<std::string> valueKeywordsSCI =
{
    "argc",
    "objectFunctionArea",
    "objectInfo",
    "objectLocal",
    "objectName",
    "objectSize",
    "objectSpecies",
    "objectSuperclass",
    "objectTotalProperties",
    "objectType",
    "scriptNumber",
    "self",
};

// Keep in alphabetical order
std::vector<std::string> valueKeywordsStudio =
{
    "paramTotal",
    "scriptNumber",
    "self",
};

bool IsValueKeyword(LangSyntax lang, const std::string &word)
{
    auto &list = GetValueKeywords(lang);
    return binary_search(list.begin(), list.end(), word);
}

std::vector<std::string> classLevelKeywordsStudio = {  "method", "properties" };
std::vector<std::string> classLevelKeywordsSCI = { "method", "properties", "procedure" };
bool IsClassLevelKeyword(LangSyntax lang, const std::string &word)
{
    auto &list = GetClassLevelKeywords(lang);
    return binary_search(list.begin(), list.end(), word);
}

// Sorted:
std::vector<std::string> unimplementedKeywordsSCI =
{
    "class#",
    "classdef",
    "extern",
    "file#",
    "global",
    "methods",
    "selectors",
    "super#",
};

bool IsUnimplementedKeyword(LangSyntax lang, const std::string &word)
{
    if (lang == LangSyntaxSCI)
    {
        return binary_search(unimplementedKeywordsSCI.begin(), unimplementedKeywordsSCI.end(), word);
    }
    return false;
}

bool IsSCIKeyword(LangSyntax lang, const std::string &word)
{
    return (IsValueKeyword(lang, word) || IsCodeLevelKeyword(lang, word) || IsTopLevelKeyword(lang, word) || IsClassLevelKeyword(lang, word) ||
        IsUnimplementedKeyword(lang, word) ||
        ((lang == LangSyntaxSCI) && (word == "&tmp")));


}

const std::vector<std::string> &GetValueKeywords(LangSyntax lang)
{
    switch (lang)
    {
        case LangSyntaxSCI:
            return valueKeywordsSCI;
        case LangSyntaxStudio:
            return valueKeywordsStudio;
    }
    return emptyList;
}

const std::vector<std::string> &GetCodeLevelKeywords(LangSyntax lang)
{
    switch (lang)
    {
        case LangSyntaxSCI:
            return codeLevelKeywordsSCI;
        case LangSyntaxStudio:
            return codeLevelKeywordsStudio;
    }
    return emptyList;
}

const std::vector<std::string> &GetClassLevelKeywords(LangSyntax lang)
{
    switch (lang)
    {
        case LangSyntaxSCI:
            return classLevelKeywordsSCI;
        case LangSyntaxStudio:
            return classLevelKeywordsStudio;
    }
    return emptyList;
}
